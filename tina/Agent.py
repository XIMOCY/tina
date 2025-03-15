import datetime
import json
import time
from typing import Union, Generator, Iterator, Any
from .core.executor import AgentExecutor
from .RAG.processFiles import FileProcess
from .core.memory import Memory
from .tools.systemTools import *
from .core.parser import tina_parser 


class Agent:
    def __new__(cls, LLM: type, tools: type, prompt: type, is_tool_call_permission: bool = True):
        if LLM._call == "API":
            return object.__new__(Agent_API)
        elif LLM._call == "LOCAL":
            return object.__new__(Agent_LOCAL)
        else:
            raise ValueError("LLM 调用方式错误，如果是API调用，设置LLM._call = 'API'，如果是本地调用，设置LLM._call = 'LOCAL'")

    def __init__(self, LLM: type, tools: type, prompt: type, is_tool_call_permission: bool = True):
        self.LLM = LLM
        self.Tools = tools
        self.Prompt = prompt
        self.Memory = Memory()
        self.fileProcess = FileProcess()
        self.messages = [
            {"role": "system", "content": self.Prompt.prompt["tina"]},
            {"role": "system", "content": f"这次运行的开始数据有：你的最大上下文{self.LLM.context_length},时间为{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        ]
        # 加载记忆信息
        self.messages.extend(
            self.Memory.returnMessages(self.LLM.context_length, memory_percent=0.2, tag=["用户信息", "指令信息"], importance=3)
        )
        self.messages.append({"role": "system", "content": "这条消息之前的内容是你和用户的聊天记忆，他们发生在过去的对话中，用于你了解用户会做什么。"})
        self.messages_conter = len(self.messages)
        self.is_tool_call_permission = is_tool_call_permission

    def predict(self, input_text: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 0,
                min_p: float = 0.0,
                stream: bool = True
                ) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        self.messages.append(
            {"role": "user", "content": input_text}
        )
        if stream:
            llm_result = self.LLM.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.Tools.tools,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=stream,
            )
            return self.tag_parser(text_generator=llm_result, tag="<tool_call>")
        else:
            tool_call = False
            while tool_call == False:
                llm_result = self.LLM.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.Tools.tools,
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=stream
                )
                result = AgentExecutor.execute(llm_result["content"], self.Tools, is_permissions=self.is_tool_call_permission)
                if not result[1]:
                    return result[0]

                self.messages.append(
                    {"role": "assistant", "content": "工具的执行结果为：\n" + result[0]}
                )
                tool_call = result[1]

    def readFile(self, path):
        """
        读取文件
        """
        file_content = self.fileProcess.read_file(file_path=path)
        if len(file_content) >= int(self.LLM.context_length * 0.5):
            self.messages.append(
                {"role": "system", "content": f"文件内容为，文件过大所以只阅读了一半上下文长度的文字,建议用户使用RAG：\n{file_content[0:int(self.LLM.context_length * 0.5)]}"}
            )
        else:
            self.messages.append(
                {"role": "system", "content": f"用户上传了文件，路径为：{path}，文件内容为：\n{file_content}"}
            )

    def remember(self, message: str = None) -> None:
        """
        记忆消息
        """
        if message is None:
            for message in self.messages[self.messages_conter:]:
                self.Memory.remember(self.LLM, message)
            self.messages_conter = len(self.messages)
        else:
            self.Memory.remember(self.LLM, message)

    def forget(self, importance: int = None):
        """
        忘记之前的对话信息，与记忆模块的遗忘有区别
        """
        if importance is None:
            self.messages = []
        else:
            self.Memory.forget(importance)

    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[str, None, None]:
        """
        解析流式消息
        """
        tool_call = ""
        whole_content = ""
        in_tool_call = False
        close_tag = tag[:1] + "/" + tag[1:]

        try:
            for chunk in text_generator:
                # 解析chunk结构
                try:
                    delta = chunk["choices"][0]["delta"]
                except (KeyError, IndexError, TypeError) as e:
                    yield f"错误: 消息格式不正确 - {str(e)}"
                    continue
                # 跳过role字段更新
                if "role" in delta:
                    continue
                # 获取content内容
                content = delta.get("content", "")
                if not content:
                    continue
                # 检测工具调用
                if content.startswith(tag):
                    in_tool_call = True
                    tool_call += content
                    # 收集完整工具调用内容
                    while not tool_call.endswith(close_tag):
                        try:
                            next_chunk = next(text_generator)
                            next_delta = next_chunk["choices"][0]["delta"]
                            next_content = next_delta.get("content", "")
                            tool_call += next_content
                        except Exception as e:
                            yield "错误: 工具调用不完整或消息格式不正确" + str(e)
                            in_tool_call = False
                            break
                    if not in_tool_call:
                        continue
                        # 执行工具调用
                    yield "正在发生工具调用...\n"
                    tool_call = tina_parser(tool_call, self.Tools, self.LLM)
                    result = AgentExecutor.execute(tool_call, self.Tools, is_permissions=self.is_tool_call_permission, LLM=self.LLM)
                    if result[1]:
                        self.messages.extend([{
                            "role": "assistant",
                            "content": f"{tool_call}"
                        }, {
                            "role": "system",
                            "content": f"工具调用结果：\n{result[0]}"
                        }])
                        # 生成新的大模型响应
                        yield from self.predict(input_text=whole_content, stream=True)
                    else:
                        yield "工具调用执行失败"
                    return  # 结束当前生成器
                else:
                    # 普通响应内容
                    whole_content += content
                    yield content
        except Exception as e:
            # yield f"错误: 处理过程中发生异常 - {str(e)}"
            raise e
        # 非工具调用时保存完整响应
        if not in_tool_call:
            self.messages.append({
                "role": "assistant",
                "content": whole_content
            })


class Agent_API(Agent):
    def __init__(self, LLM: type, tools: type, prompt: type, is_tool_call_permission: bool = True):
        super().__init__(LLM, tools, prompt, is_tool_call_permission)
        self.tool_calls:list = []
    def predict(self, input_text: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 0,
                min_p: float = 0.0,
                stream: bool = True
                ) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        if input_text is not None:
            self.messages.append(
                {"role": "user", "content": input_text}
            )
        if stream:
            llm_result = self.LLM.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.Tools.tools,
                top_p=top_p,
                stream=stream,
            )
            return self.parser(llm_result)
        else:
            tool_call = False
            while tool_call == False:
                llm_result = self.LLM.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.Tools.tools,
                    top_p=top_p,
                    stream=stream
                )
                if "tool_calls" in llm_result.keys():
                    tool_call = (llm_result["tool_calls"][0]["function"]["name"],json.loads(llm_result["tool_calls"][0]["function"]["arguments"]),True)
                    result = AgentExecutor.execute(tool_call, self.Tools, is_permissions=self.is_tool_call_permission)
                    if not result[1]:
                        return result[0]

                    self.messages.append(
                        {"role": "assistant", "content": "工具的执行结果为：\n" + result[0]}
                    )
                    tool_call = result[1]

    def parser(self, generator):
        whole_content = ""
        tool_result = ('',False)
        for chunk in generator:
            if chunk["content"] is None:
                chunk["content"] = ""
                self.messages.append(chunk)
                yield chunk["content"]
                whole_content += chunk["content"]
            elif "tool_calls" in chunk and chunk["id"] != '': 
                temp = chunk.copy()  # 使用copy避免修改原始数据
                temp["tool_calls"][0]["id"] = temp["id"]
                temp.pop("id")
                # 解析工具调用参数时要捕获异常
                yield f"\n正在发生工具调用...\n工具名：{temp['tool_calls'][0]['function']['name']}\n"
                try:
                    args = json.loads(chunk["tool_calls"][0]["function"]["arguments"])
                    if args is None:
                        yield "工具参数为空"
                        yield from self.predict(input_text="工具参数为空，请重新输入，你之前输入的内容为：\n"+whole_content,stream=True)
                except json.JSONDecodeError:
                    yield "工具参数解析失败"
                    yield from self.predict(input_text="工具解析失败，请重新输入，你之前输入的内容为：\n"+whole_content,stream=True)
                    
                tool_call = (chunk["tool_calls"][0]["function"]["name"], args, True)
                tool_result = AgentExecutor.execute(tool_call=tool_call,tools=self.Tools)
                self.messages.append(temp)
                
                if tool_result[1]:  # 工具调用成功后
                    # 添加工具结果到消息历史
                    self.messages.append({"role":"tool","content":f"工具调用结果：\n{tool_result[0]}"})
                    # 递归调用并立即返回所有生成内容
                    yield from self.predict(input_text=whole_content,stream=True)
            else:
                yield chunk["content"]

            
     


class Agent_LOCAL(Agent):
    def __init__(self, LLM: type, tools: type, prompt: type, is_tool_call_permission: bool = True):
        super().__init__(LLM, tools, prompt, is_tool_call_permission)

    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[str, None, None]:
        """
        解析流式消息
        """
        tool_call = ""
        whole_content = ""
        in_tool_call = False
        close_tag = tag[:1] + "/" + tag[1:]

        try:
            for chunk in text_generator:
                # 解析chunk结构
                try:
                    delta = chunk["choices"][0]["delta"]
                except (KeyError, IndexError, TypeError) as e:
                    yield f"错误: 消息格式不正确 - {str(e)}"
                    continue
                # 跳过role字段更新
                if "role" in delta:
                    continue
                # 获取content内容
                content = delta.get("content", "")
                if not content:
                    continue
                # 检测工具调用
                if content.startswith(tag):
                    in_tool_call = True
                    tool_call += content
                    # 收集完整工具调用内容
                    while not tool_call.endswith(close_tag):
                        try:
                            next_chunk = next(text_generator)
                            next_delta = next_chunk["choices"][0]["delta"]
                            next_content = next_delta.get("content", "")
                            tool_call += next_content
                        except Exception as e:
                            yield "错误: 工具调用不完整或消息格式不正确" + str(e)
                            in_tool_call = False
                            break
                    if not in_tool_call:
                        continue
                        # 执行工具调用
                    yield "正在发生工具调用...\n"
                    tool_call = tina_parser(tool_call, self.Tools, self.LLM)
                    result = AgentExecutor.execute(tool_call, self.Tools, is_permissions=self.is_tool_call_permission, LLM=self.LLM)
                    if result[1]:
                        self.messages.extend([{
                            "role": "assistant",
                            "content": f"{tool_call}"
                        }, {
                            "role": "system",
                            "content": f"工具调用结果：\n{result[0]}"
                        }])
                        # 生成新的大模型响应
                        yield from self.predict(input_text=whole_content, stream=True)
                    else:
                        yield "工具调用执行失败"
                    return  # 结束当前生成器
                else:
                    # 普通响应内容
                    whole_content += content
                    yield content
        except Exception as e:
            # yield f"错误: 处理过程中发生异常 - {str(e)}"
            raise e
        # 非工具调用时保存完整响应
        if not in_tool_call:
            self.messages.append({
                "role": "assistant",
                "content": whole_content
            })