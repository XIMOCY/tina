"""
编写者：王出日
日期：2024，12，1
版本？
Agent类，创建智能体的类
如何使用
1. 实例化Agent类，传入LLM、tools、prompt、parser、is_tool_call_permission四个参数
2. 如果想精细的操作agent，可以调用agent的各个方法，如predict、remeber、recall、forget等
3. 使用run，agent会启动一个事件训环，通过检测用户注册的事件来推动智能体的行为，并自动在后台运行
4. 实例化Environment类后，通过在Environment类注册agent也可以运行，这时的agent会获得环境的输入并进行相应的回复

！！！注意：如果创建了工作文件夹，在用户之前没有删除数据的情况下，会自动加载之前的记忆信息，可以删除工作文件夹，或者使用forget方法清空记忆信息

"""
import datetime

from typing import Union,Generator
from .core.executor import AgentExecutor
from .RAG.processFiles import FileProcess
from .core.memory import Memory
from .tools.systemTools import *
from typing import Generator, Iterator, Any


class Agent:
    def __init__(self, LLM:type, tools:type, prompt:type,is_tool_call_permission:bool=True):
        self.LLM = LLM
        self.Tools = tools
        self.Prompt = prompt
        self.Memory = Memory()
        self.fileProcess = FileProcess()
        self.messages = [
            {"role":"system","content":self.Prompt.prompt["tina"]},
            {"role":"system","content":f"这次运行的开始数据有：你的最大上下文{self.LLM.context_length},时间为{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        ]
        # 加载记忆信息
        self.messages.extend(
            self.Memory.returnMessages(self.LLM.context_length, memory_percent=0.2, tag=["用户信息","指令信息"], importance=3)
        )
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
                tools = self.Tools.tools,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=stream,
            )
            return self.tag_parser(text_generator=llm_result,tag="<tool_call>")
        else:
            tool_call = False
            while tool_call == False:
                llm_result = self.LLM.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools = self.Tools.tools,
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=stream
                )
                result = AgentExecutor.execute(llm_result["content"],self.Tools,is_permissions=self.is_tool_call_permission)
                if not result[1]:
                    return result[0]
                
                self.messages.append(
                        {"role": "assistant", "content": "工具的执行结果为：\n"+result[0]}
                )
                tool_call = result[1]

    def readFile(self,path):
        """
        读取文件
        """
        file_content = self.fileProcess.read_file(file_path=path)
        if len(file_content) >= int(self.LLM.context_length*0.5):
            self.messages.append(
                {"role": "system", "content": f"文件内容为，文件过大所以只阅读了一半上下文长度的文字,建议用户使用RAG：\n{file_content[0:int(self.LLM.context_length*0.5)]}"}
            )
        else:
            self.messages.append(
                {"role": "system", "content": f"用户上传了文件，路径为：{path}，文件内容为：\n{file_content}"}
            )
        
        
    def remember(self,message:str = None)->None:
        """
        记忆消息
        """
        if message is None:
            for message in self.messages[self.messages_conter:]:
                self.Memory.remember(self.LLM,message)
            self.messages_conter = len(self.messages)
        else:
            self.Memory.remember(self.LLM,message)

    def forget(self,importance:int=None):
        """
        忘记之前的对话信息，与记忆模块的遗忘有区别
        """ 
        if importance is None:
            self.messages = []
        else:
            self.Memory.forget(importance)

    def tag_parser(self, text_generator: Iterator[Any],tag="") -> Generator[str, None, None]:
        """
        解析流式消息
        """
        tool_call = ""
        whole_content = ""
        in_tool_call = False
        close_tag = tag[:1]+"/"+tag[1:]

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
                            yield "错误: 工具调用不完整或消息格式不正确"+str(e)
                            in_tool_call = False
                            break
                    if not in_tool_call:
                        continue
                        # 执行工具调用
                    yield "正在发生工具调用...\n"
                    result = AgentExecutor.execute(tool_call,self.Tools,is_permissions=self.is_tool_call_permission,LLM=self.LLM)
                    if result[1]:  
                        self.messages.extend([{
                            "role": "assistant",
                            "content": f"{tool_call}"
                        },{
                            "role": "system",
                            "content": f"工具调用结果：\n{result[0]}"
                        }])
                    # 生成新的大模型响应
                        yield from self.predict(input_text=whole_content,stream=True)
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