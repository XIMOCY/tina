"""
编写者：王出日
日期：2024，12，1
版本 0.4.2
功能：Agent类，实现了最简单的工具执行智能体的功能。
包含：
Agent类：
"""

import datetime
import json
from typing import List, Union, Generator, Iterator, Dict,Any
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
    def __new__(cls, LLM: BaseAPI, tools: Tools,sys_prompt:str=None,isExecute:bool=True,MCP=None,context_limit:int=8000):
        if LLM._call == "API":
            return object.__new__(Agent_API)
        elif LLM._call == "LOCAL":
            return object.__new__(Agent_LOCAL)
        else:
            raise ValueError("LLM 调用方式错误，如果是API调用，设置LLM._call = 'API'，如果是本地调用，设置LLM._call = 'LOCAL'")
    def __init__(self, LLM: BaseAPI, tools:Tools,sys_prompt:str=None,isExecute:bool=True,MCP:MCPClient=None,context_limit:int=8000):
        """
        实例化一个Agent对象
        Args:
            LLM:tina.BaseAPI类型，调用的LLM对象
            tools:tina.Tools类型，工具集
            sys_prompt:str 系统提示词
            isExecute:bool 是否执行工具，默认为True，关闭后智能体不在执行工具并返回结果和大模型回复。
            MCP:tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
            context_limit:int 最大上下文长度，超过该长度则删除旧消息，保留最近的消息。

        可用的方法：

            addMessage(role: str=None, content: str=None,messages: list = None) -> None:
                在当前的Agent添加新的消息
            getMessages() -> list:
                获取当前Agent的消息列表
            clearMessages() -> None:
                清理当前Agent的消息列表
            getTools() -> list:
                获取当前Agent的工具列表
            getPrompt() -> str:
                获取当前Agent的提示词
            getToolsCallResult() -> list:
                获取当前Agent的工具调用结果列表
            getToolsCall() -> list:
                获取当前Agent的工具调用列表
            addMCPServer(server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
                添加MCP服务器
            removeServer(server_id: str) -> bool:
                移除MCP服务器
            getMCPServerInfo(server_id: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
                获取MCP服务器信息

            predict(input_text: str = None,
                    temperature: float = 0.5,
                    top_p: float = 0.9,
                    top_k: int = 0,
                    min_p: float = 0.0,
                    stream: bool = True) -> Union[str, Generator[str, None, None]]:
                调用agent进行生成文本回复，默认流式输出
        """
        self.LLM = LLM
        self.Tools = tools
        self.tools_call_result = []
        self.tools_call = []
        self.Prompt = None
        self.isExecute = isExecute
        self.context_limit = context_limit
        self._mcp_serve(MCP)
        if sys_prompt is not None:
            self.Prompt = sys_prompt
            self.messages = [
                {"role": "system", "content": self.Prompt},  # 系统提示词
                {"role": "system", "content": ""},  # 目标设置
                {"role": "system", "content": ""}   # 目标达成情况和下一步
            ]
        else:
            self.Prompt = Prompt("tina")
            self.messages = [
                {"role": "system", "content": self.Prompt.prompt},  # 系统提示词
                {"role": "system", "content": ""},  # 目标设置
                {"role": "system", "content": ""}   # 目标达成情况和下一步
            ]

    def _mcp_serve(self, MCP):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcpclient = MCP
                _tools = self.mcpclient.toTinaTools()
                self.Tools = _tools + self.Tools
                del _tools
        except Exception as e:
            raise e
        
    def disableTool(self, tool_name: str) -> bool:
        """
        禁用工具
        Args:
            tool_name:工具名称
        """
        return self.Tools.disableTool(tool_name)
    
    def enableTool(self, tool_name: str) -> bool:
        """
        启用工具
        Args:
            tool_name:工具名称
        """
        return self.Tools.enableTool(tool_name)
    
    def getMessages(self) -> list:
        """
        获取当前Agent的消息列表
        Agent会在当前运行状态维护一个自己的消息列表，可以通过该方法获取
        """
        return self.messages
    def clearMessages(self) -> None:
        """
        清理当前Agent的消息列表，只保留前三个系统消息
        """
        self.messages = self.messages[:3]
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
    def setGoal(self, goal: str) -> None:
        """
        设置当前Agent的目标（更新第二个系统消息）
        Args:
            goal: 目标描述
        """
        self.messages[1] = {"role": "system", "content": goal}

    def updateGoalStatus(self, status: str) -> None:
        """
        更新目标达成情况和下一步（更新第三个系统消息）
        Args:
            status: 目标达成情况和下一步行动描述
        """
        self.messages[2] = {"role": "system", "content": status}

    def cancelGoal(self) -> None:
        """
        取消当前Agent的目标（清空第二个系统消息）
        """
        self.messages[1] = {"role": "system", "content": ""}
    def add_message(self,role:str,content:str,messages:list=None):
        return self.addMessage(role,content,messages)
    def addMessage(self, role: str=None, content: str=None,messages: list = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            role:消息的角色，可以是"user"，"assistant"，"system"
            content:消息的内容
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]，注意如果传入了messages，则role和content参数将被忽略
        """
        if self.context_limit > 0:
            self._limit_messages()
        if messages is not None:
            self.messages.extend(messages)
            return 
        self.messages.append({"role": role, "content": content})

    def get_tools_call_result(self) ->list:
        return self.getToolsCallResult()

    def getToolsCallResult(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.tools_call_result
    
    def _limit_messages(self):
        """
        限制消息列表总字数不超过self.context_limit
        保留前三个系统消息，优先删除较早的非系统消息
        """
        if self.context_limit < 0:
            return 
        
        if not self.messages:
            return

        # 强制保留前三个系统消息
        preserved = self.messages[:3]
        current_length = sum(len(msg.get('content', '')) for msg in preserved)
        
        # 如果初始长度已超限，只保留前三个
        if current_length >= self.context_limit:
            self.messages = preserved
            return

        # 保留足够多的最新消息
        remaining = self.context_limit - current_length
        new_messages = preserved.copy()
        total = 0
        
        # 从后向前遍历非系统消息
        for msg in reversed(self.messages[3:]) if len(self.messages) > 3 else []:
            content_len = len(msg.get('content', ''))
            if total + content_len <= remaining:
                new_messages.append(msg)
                total += content_len
            else:
                continue
        
        # 恢复消息顺序
        new_messages = preserved + sorted(new_messages[3:], key=lambda x: self.messages.index(x))
        self.messages = new_messages
    
    def get_tools_call(self) ->list:
        return self.getToolsCall()
    
    def getToolsCall(self) -> list:
        """
        获取当前Agent的工具调用列表
        """
        return self.tools_call
    
    def add_mcp_server(self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
        return self.addMCPServer(server_id, config, max_retries, timeout)
    
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
        
    def remove_server(self, server_id: str) -> bool:
        return self.removeServer(server_id)
    
    def removeServer(self, server_id: str) -> bool:
        """
        移除MCP服务器
        Args:
            server_id:服务器ID
        """
        if self.mcpclient is not None:
            return self.mcpclient.removeServer(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")
    
    def getMCPServerInfo(self, server_id: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        获取MCP服务器信息
        Args:
            server_id:服务器ID，如果不传入，则返回所有服务器信息
        """
        if self.mcpclient is not None:
            return self.mcpclient.getServerInfo(server_id)
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
        if stream:
            llm_result = self.LLM.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.Tools.getTools(),
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
    def __init__(self, LLM: type, tools: type, sys_prompt:str=None,isExecute:bool=True,MCP=None,context_limit:int=8000):
        super().__init__(LLM=LLM, tools=tools, sys_prompt=sys_prompt,isExecute=isExecute,MCP=MCP,context_limit=context_limit)

    def predict(self, input_text: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 0,
                min_p: float = 0.0,
                stream: bool = True
                ) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        Args:
            input_text:输入的文本
            temperature:随机度
            stream:流式开关
        Returns:
            返回的格式如下：
            如果是流式的话，结果会是一个生成器，每一次生成器的输出是一个字典，和非流式的一致，但是键里面的值是需要连续获取的

            {
                "role":"角色，可能为assistant和tool，assistant表示是大模型输出的内容，tool表示是工具执行的内容",
                "content":"大模型回复的内容或者工具执行内容",
                "reasoning_content":"如果使用的是推理模型的话，思考内容会在这里显示",
                "tool_name":"工具名称",
                "tool_arguments":"工具参数,
            }
        """
        if input_text is not None:
            self.messages.append(
                {"role": "user", "content": input_text}
            )
        if stream:
            llm_result = self.LLM.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.Tools.getTools(),
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
                    tools=self.Tools.getTools(),
                    top_p=top_p,
                    stream=stream
                )
                if "tool_calls" in llm_result.keys():
                    tool_call = (llm_result["tool_calls"][0]["function"]["name"],json.loads(llm_result["tool_calls"][0]["function"]["arguments"]),True)
                    result = self.__execute(tool_call[0], tool_call[1], tool_call[2])
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
        content_parts = []
        tool_result = ('', False)
        reasoning_buffer = ""  # 缓存推理内容
        
        for chunk in generator:
            # 处理None内容或确保content键存在
            if chunk.get("content") is None:
                chunk["content"] = ""
                
            # 处理工具名称
            if "tool_name" in chunk:
                yield {"role": "assistant", "tool_name": chunk['tool_name'], "content": ""}
                
            # 处理工具调用
            elif "tool_calls" in chunk and chunk["id"] != '':
                # 先添加之前累积的内容
                whole_content = "".join(content_parts)
                if whole_content:
                    self.messages.append({"role": "assistant", "content": whole_content})
                content_parts = []  # 重置内容集合
                reasoning_buffer = ""  # 重置推理缓存
                
                # 预处理工具调用参数
                tool_call = chunk["tool_calls"][0]
                function_args = tool_call["function"]["arguments"]
                
                yield {"role": "assistant", "tool_arguments": function_args, "content": ""}
                
                # 解析工具参数
                try:
                    args = json.loads(function_args)
                    if args is None:
                        error_msg = "工具参数为空"
                        yield {"role": "assistant", "content": error_msg}
                        self._limit_messages()
                        yield from self.predict(input_text=f"{error_msg}，请重新输入，你之前输入的内容为：\n{whole_content}", stream=True)
                        continue
                except json.JSONDecodeError:
                    error_msg = "工具参数解析失败"
                    yield {"role": "assistant", "content": error_msg}
                    yield from self.predict(input_text=f"{error_msg}，请重新输入，你之前输入的内容为：\n{whole_content}", stream=True)
                    continue
                
                # 构建工具调用对象
                tool_call_obj = {
                    "id": chunk["id"],
                    "function": {
                        "name": tool_call["function"]["name"],
                        "arguments": function_args
                    }
                }
                
                self.tools_call.append(tool_call_obj)
                
                # 执行工具调用
                if self.isExecute:
                    tool_result = self.__execute(tool_call["function"]["name"], args, tool_call_obj)
                    yield {"role": "tool", "content": tool_result[0]}
                    
                    # 只在工具调用成功时添加消息
                    if tool_result[1]:
                        # 添加工具调用消息，必须包含有效的role字段
                        self.messages.append({"role": "assistant", "tool_calls": [tool_call_obj]})
                        # 添加工具结果到消息历史
                        self.messages.append({"role": "tool", "content": f"工具调用结果：\n{tool_result[0]}"})
                        # 递归调用并立即返回所有生成内容
                        yield from self.predict(input_text=None, stream=True)
                
            # 处理推理内容
            elif "reasoning_content" in chunk:
                # 获取推理内容
                reasoning_content = chunk.get("reasoning_content", "")
                if reasoning_content:
                    # 累积推理内容
                    reasoning_buffer += reasoning_content
                    yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}
                
            # 处理普通内容
            else:
                content = chunk.get("content", "")
                if content:
                    content_parts.append(content)
                    yield {"role": "assistant", "content": content}
                
        # 处理剩余的内容
        whole_content = "".join(content_parts)
        if whole_content:
            self.messages.append({"role": "assistant", "content": whole_content})

    def __execute(self, tool_name, args, tool_call_obj,max_input = None):
        """执行工具调用并返回结果"""
        tool_call = (tool_name, args, True)
        
        # 根据工具名称选择执行方式
        if tool_name.startswith("mcp_"):
            tool_result = MCPToolExecutor.execute_mcp_tool(tool_name, args, self.mcpclient)
        elif tool_name == "setGoal":
            self.setGoal(args["goal"])
            tool_result = ("目标设置成功", True)
        elif tool_name == "cancelGoal":
            self.cancelGoal()
            tool_result = ("目标已取消", True)
        elif tool_name == "updateGoalStatus":
            self.updateGoalStatus(args["status"])
            tool_result = ("目标状态已更新", True)
        else:
            tool_result = AgentExecutor.execute(tool_call=tool_call, tools=self.Tools)
            
        # 记录工具调用结果
        result_record = {
            "id": tool_call_obj["id"],
            "name": tool_name,
            "arguments": tool_call_obj["function"]["arguments"],
            "result": tool_result[0],
            "success": tool_result[1]
        }
        
        self.tools_call_result.append(result_record)
        return tool_result


            
     


class Agent_LOCAL(Agent):
    def __init__(self, LLM: type, tools: type, sys_prompt:str=None, isExecute:bool=True, MCP=None, context_limit:int=8000):
        super().__init__(LLM, tools, sys_prompt, isExecute, MCP, context_limit)

    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[Dict[str, Any], None, None]:
        """
        解析流式消息，返回标准化的字典格式
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
                    yield {"role": "system", "content": f"错误: 消息格式不正确 - {str(e)}"}
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
                            yield {"role": "system", "content": f"错误: 工具调用不完整或消息格式不正确 {str(e)}"}
                            in_tool_call = False
                            break
                            
                    if not in_tool_call:
                        continue
                        
                    # 执行工具调用
                    yield {"role": "system", "content": "正在发生工具调用..."}
                    tool_call_parsed = tina_parser(tool_call, self.Tools, self.LLM)
                    
                    # 提取工具名称
                    tool_name = tool_call_parsed[0]
                    yield {"role": "system", "tool_name": tool_name, "content": f"正在执行工具：{tool_name}"}
                    
                    result = AgentExecutor.execute(tool_call_parsed, self.Tools, LLM=self.LLM)
                    if result[1]:
                        self.messages.extend([{
                            "role": "assistant",
                            "content": f"{tool_call_parsed}"
                        }, {
                            "role": "tool", 
                            "content": f"工具调用结果：\n{result[0]}"
                        }])
                        # 生成新的大模型响应
                        yield from self.predict(input_text=whole_content, stream=True)
                    else:
                        yield {"role": "system", "content": "工具调用执行失败"}
                    return  # 结束当前生成器
                else:
                    # 普通响应内容
                    whole_content += content
                    yield {"role": "assistant", "content": content}
        except Exception as e:
            raise e
            
        # 非工具调用时保存完整响应
        if not in_tool_call:
            self.messages.append({
                "role": "assistant",
                "content": whole_content
            })