import datetime
import json
from typing import Union, Generator, Iterator, Dict,Any
from .core.tools import Tools
from .core.executor import AgentExecutor
from .core.parser import tina_parser 
from .core.prompt import Prompt
from ..MCP.Client import MCPClient
from ..MCP.MCPToolExecutor import MCPToolExecutor
from ..LLM.api import BaseAPI

class Agent:
    """
    最简单的工具执行智能体，
    """
    def __new__(cls, LLM: BaseAPI, tools: Tools,sys_prompt:str=None,isExecute:bool=True,MCP:MCPClient=None):
        if LLM._call == "API":
            return object.__new__(Agent_API)
        elif LLM._call == "LOCAL":
            return object.__new__(Agent_LOCAL)
        else:
            raise ValueError("LLM 调用方式错误，如果是API调用，设置LLM._call = 'API'，如果是本地调用，设置LLM._call = 'LOCAL'")
    def __del__(self):
        if getattr(self, "mcpclient", None) is not None:
            self.mcpclient.close()
    def __init__(self, LLM: BaseAPI, tools:Tools,sys_prompt:str=None,isExecute:bool=True,MCP:MCPClient=None):
        """
        实例化一个Agent对象
        Args:
            LLM:tina.BaseAPI类型，调用的LLM对象
            tools:tina.Tools类型，工具集
            sys_prompt:系统提示语
            isExecute:是否执行工具，默认为True，关闭后智能体不在执行工具并返回结果和大模型回复。
            MCP:tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
        """
        self.LLM = LLM
        self.Tools = tools
        self.tools_call_result = []
        self.tools_call = []
        self.Prompt = None
        self.isExecute = isExecute
        self._MCP_serve(MCP)
        if sys_prompt is not None:
            self.Prompt = sys_prompt
            self.messages = [
                {"role": "system", "content": self.Prompt},
                {"role": "system", "content": f"这次运行的开始数据有：你的最大上下文{self.LLM.context_length},时间为{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
            ]
        else:
            self.Prompt = Prompt("tina")
            self.messages = [
                {"role": "system", "content": self.Prompt.prompt},
                {"role": "system", "content": f"这次运行的开始数据有：你的最大上下文{self.LLM.context_length},时间为{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
            ]

    def _MCP_serve(self, MCP:MCPClient):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcpclient = MCP
                _tools = self.mcpclient.toTinaTools()
                print(type(_tools))
                self.Tools = _tools + self.Tools
                del _tools
        except Exception as e:
            raise e
    
    def getMessages(self) -> list:
        """
        获取当前Agent的消息列表
        Agent会在当前运行状态维护一个自己的消息列表，可以通过该方法获取
        """
        return self.messages
    
    def getTools(self) -> list:
        """
        获取当前Agent的工具列表
        """
        return self.Tools.tools
    
    def getPrompt(self) -> str:
        """
        获取当前Agent的提示词
        """
        return self.Prompt
    
    def addMessage(self, role: str=None, content: str=None,messages: list = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            role:消息的角色，可以是"user"，"assistant"，"system"
            content:消息的内容
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]，注意如果传入了messages，则role和content参数将被忽略
        """
        if messages is not None:
            self.messages.extend(messages)
            return 
        self.messages.append({"role": role, "content": content})
    
    def getToolsCallResult(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.tools_call_result
    
    def getToolsCall(self) -> list:
        """
        获取当前Agent的工具调用列表
        """
        return self.tools_call
    def addMCPServer(self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
        """
        添加MCP服务器
        Args:
            server_id:服务器ID
            config:服务器配置
            max_retries:最大重试次数
            timeout:超时时间
        """
        if self.mcpclient is not None:
            return self.mcpclient.addServer(server_id, config, max_retries, timeout)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")
    
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
        else:
            pass
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
            while True:
                llm_result = self.LLM.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.Tools.tools,
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=stream
                )
                parser_result = tina_parser(llm_result["content"], self.Tools, self.LLM)
                tool_call = parser_result[2]
                if tool_call == False:
                    self.messages.append(
                        llm_result
                    )
                    return llm_result 
                else:
                    result = AgentExecutor.execute(parser_result, self.Tools)
                    self.messages.append(
                        {"role": "tool", "content": "工具的执行结果为：\n" + result[0]}
                    )
                    continue
    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[str, None, None]:
        pass



class Agent_API(Agent):
    def __init__(self, LLM: type, tools: type, sys_prompt:str=None,isExecute:bool=True,MCP:MCPClient=None):
        super().__init__(LLM=LLM, tools=tools, sys_prompt=sys_prompt,isExecute=isExecute,MCP=MCP)

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
            
            while True:
                tool_call = False
                llm_result = self.LLM.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.Tools.tools,
                    top_p=top_p,
                    stream=stream
                )
                if "tool_calls" in llm_result.keys():
                    tool_call = (llm_result["tool_calls"][0]["function"]["name"],json.loads(llm_result["tool_calls"][0]["function"]["arguments"]),True)
                    result = AgentExecutor.execute(tool_call, self.Tools)
                    if not result[1]:
                        return result[0]

                    self.messages.append(
                        {"role": "system", "content": "工具的执行结果为：\n" + result[0]}
                    )
                    tool_call = result[1]

                if tool_call == False:
                    
                    self.messages.append(
                        llm_result
                    )
                    return llm_result 
                else:
                    continue

    def parser(self, generator):
        whole_content = ""
        tool_result = ('',False)
        for chunk in generator:
            if chunk["content"] is None:
                chunk["content"] = ""
                yield chunk["content"]
            elif "tool_name" in chunk:
                yield f"<|tool_call_name|>{chunk["tool_name"]}<|tool_call_name|>"
            elif "tool_calls" in chunk and chunk["id"] != '': 
                self.messages.append({"role":"assistant","content":whole_content})
                temp = chunk.copy()  # 使用copy避免修改原始数据
                temp["tool_calls"][0]["id"] = temp["id"]
                temp.pop("id")
                # 解析工具调用参数时要捕获异常
                yield f"<|tool_call_arguments|>{temp['tool_calls'][0]['function']['arguments']}<|tool_call_arguments|>"
                try:
                    args = json.loads(chunk["tool_calls"][0]["function"]["arguments"])
                    if args is None:
                        yield "工具参数为空"
                        yield from self.predict(input_text="工具参数为空，请重新输入，你之前输入的内容为：\n"+whole_content,stream=True)
                except json.JSONDecodeError:
                    yield "工具参数解析失败"
                    yield from self.predict(input_text="工具解析失败，请重新输入，你之前输入的内容为：\n"+whole_content,stream=True)

                self.tools_call.append(temp["tool_calls"][0])
                if self.isExecute:
                    tool_result = self.__execute(chunk, temp, args)
                    yield f"<|tool_call_result|>{tool_result[0]}<|tool_call_result|>"

                    self.messages.append(temp)
                
                    if tool_result[1]:  # 工具调用成功后
                        # 添加工具结果到消息历史
                        self.messages.append({"role":"tool","content":f"工具调用结果：\n{tool_result[0]}"})
                        # 递归调用并立即返回所有生成内容
                        yield from self.predict(input_text=None,stream=True)

            elif "reasoning_content" in chunk:
                if chunk["reasoning_content"] is None:
                    chunk["reasoning_content"] = ""
                yield chunk["reasoning_content"]
            else:
                whole_content += chunk["content"]
                yield chunk["content"]
        self.messages.append({"role":"assistant","content":whole_content})

    def __execute(self, chunk, temp, args):
        tool_name = chunk["tool_calls"][0]["function"]["name"]
        tool_call = (tool_name, args, True)
        if tool_name.startswith("mcp_"):
            tool_result = MCPToolExecutor.execute_mcp_tool(tool_name, args, self.mcpclient)
        else:
            tool_result = AgentExecutor.execute(tool_call=tool_call,tools=self.Tools)
        self.tools_call_result.append({"id":temp["tool_calls"][0]["id"],"name":temp["tool_calls"][0]["function"]["name"],"arguments":temp["tool_calls"][0]["function"]["arguments"],"result":tool_result[0],"success":tool_result[1]})
        return tool_result


            
     


class Agent_LOCAL(Agent):
    def __init__(self, LLM: type, tools: type, sys_prompt:str=None):
        super().__init__(LLM, tools, sys_prompt)

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
                    yield "正在发生工具调用..."
                    tool_call = tina_parser(tool_call, self.Tools, self.LLM)
                    yield f"\n正在执行工具：{tool_call[0]}\n"
                    result = AgentExecutor.execute(tool_call, self.Tools, LLM=self.LLM)
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