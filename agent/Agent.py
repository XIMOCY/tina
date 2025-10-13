"""
编写者：王出日
日期：2024，12，1
版本 0.5.0
功能：Agent类，实现了智能体的功能。
包含：
Agent类：基础智能体类，默认支持API调用
AgentByLocalModel类：本地模型智能体类，继承自Agent
"""
from __future__ import annotations

import json
from typing import List, Union, Generator, Iterator, Dict, Any

from .core.tools import Tools
from .core.executor import AgentExecutor
from .core.prompt import Prompt
from ..mcp.Client import MCPClient
from ..mcp.MCPToolExecutor import MCPToolExecutor
from ..llm.BaseAPI import BaseAPI
from ..core.error import TinaError

from .core.parser import local_model_llama_cpp_parser 


class Agent:
    """
    基础智能体类，默认支持API调用方式
    兼容原有tina框架的所有方法和返回值格式
    """
    
    def __init__(self, llm: BaseAPI, tools: Tools, sys_prompt: str = None, execute_tool: bool = True, mcp: MCPClient = None, context_length: int = 10000,tools_result_length:int = 4000,name:str="None"):
        """
        实例化一个Agent对象
        
        Args:
            LLM: tina.BaseAPI类型，调用的LLM对象
            tools: tina.Tools类型，工具集
            sys_prompt: str 系统提示词
            isExecute: bool 是否执行工具，默认为True，关闭后智能体不在执行工具并返回结果和大模型回复。
            MCP: tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
            context_length: int 最大上下文长度，超过该长度则删除旧消息，保留最近的消息。
            context_limit: int 上下文限制，使用大模型来总结你的上下文，数字为0时不触发
        """
        # 智能体的名称
        self.name =name

        # 运行需要的实例
        self.llm = llm
        self.tools = tools
        self.tools_call_result = []
        self.tools_call = []
        self.isExecute = execute_tool
        self.context_length = context_length
        self._max_tools_output_length = tools_result_length
        self.mcpclient = None

        # 连接的智能体
        self.connected_agents = []
        
        # 初始化MCP
        self._mcp_serve(mcp)
        
        # 初始化提示词和消息
        if sys_prompt is not None:
            self.Prompt = sys_prompt
            self.messages = [
                {"role": "system", "content": self.Prompt},  # 系统提示词
            ]
        else:
            self.Prompt = Prompt("tina")
            self.messages = [
                {"role": "system", "content": self.Prompt.prompt},  
            ]


    def _mcp_serve(self, MCP):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcpclient = MCP
                _tools = self.mcpclient.toTinaTools()
                self.tools = _tools + self.tools
                del _tools
        except Exception as e:
            raise e

    def disableTool(self, tool_name: str) -> bool:
        """
        禁用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.disableTool(tool_name)
    
    def connect(self,agent:Agent):
        """
        连接到另一个Agent
        Args:
            agent: 另一个Agent对象
        """
        if isinstance(agent, Agent):
            if agent not in self.connected_agents:
                agent.addMessage(role="system", content=f"你已连接到{self.name}智能体")
                self.addMessage(role="system", content=f"你已连接到{agent.name}智能体")
            else:
                raise TinaError("该Agent已经连接过了")
        self.connected_agents.append(agent)
    
    def enableTool(self, tool_name: str) -> bool:
        """
        启用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.enableTool(tool_name)
    
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
        return self.tools.tools
    
    def getPrompt(self) -> str:
        """
        获取当前Agent的提示词
        """
        return self.Prompt
    
    def add_message(self, role: str, content: str, messages: list = None):
        return self.addMessage(role, content, messages)
    
    def addMessage(self, role: str = None, content: str = None, messages: list = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            role:消息的角色，可以是"user"，"assistant"，"system"
            content:消息的内容
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]，注意如果传入了messages，则role和content参数将被忽略
        """
        if self.context_length > 0:
            self.__limit_messages()
        if messages is not None:
            self.messages.extend(messages)
            return 
        self.messages.append({"role": role, "content": content})

    def get_tools_call_result(self) -> list:
        return self.getToolsCallResult()

    def getToolsCallResult(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.tools_call_result
    
    def __limit_messages(self):
        """
        限制消息列表总字数不超过self.context_length
        保留前三个系统消息，优先删除较早的非系统消息
        """
        if self.context_length < 0:
            return 
        
        if not self.messages:
            return

        # 强制保留前三个系统消息
        preserved, current_length = self.__get_system_messages_length()
        
        # 如果初始长度已超限，只保留前三个
        if current_length >= self.context_length:
            self.messages = preserved
            return

        remaining = self.context_length - current_length
        new_messages = preserved.copy()
        total = 0
        
        for msg in reversed(self.messages[1:]) if len(self.messages) > 1 else []:
            content_len = len(msg.get('content', ''))
            if total + content_len <= remaining:
                new_messages.append(msg)
                total += content_len
            else:
                continue
        
        new_messages = preserved + sorted(new_messages[1:], key=lambda x: self.messages.index(x))
        self.messages = new_messages

    def __get_system_messages_length(self):
        preserved = self.messages[:1]
        current_length = sum(len(msg.get('content', '')) for msg in preserved)
        return preserved,current_length
    def getMessagesLength(self) -> int:
        """
        获取当前Agent的消息列表总字数
        """
        return sum(len(msg.get('content', '')) for msg in self.messages)
    def get_tools_call(self) -> list:
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
                top_k: int = 1,
                min_p: float = 0.0,
                stream: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        if input_text is not None:
            self.messages.append(
            {"role": "user", "content": input_text}
            )
        if stream:
            llm_result = self.llm.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.tools.getTools(),
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=stream,
            )
            return self.parser(llm_result)
        else:
            
            while True:
                tool_call = False
                
                llm_result = self.llm.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.tools.getTools(),
                    top_p=top_p,
                    stream=stream
                )
                if "tool_calls" in llm_result.keys():
                    tool_call = (llm_result["tool_calls"]["function"]["name"],json.loads(llm_result["tool_calls"]["function"]["arguments"]),True)
                    result = self.__execute_tool(tool_call[0], tool_call[1], tool_call[2])
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
                    self.__sent_message(llm_result)
                    return llm_result 
                else:
                    continue

    def __sent_message(self, llm_result):
        if self.connected_agents:
            for agent in self.connected_agents:
                agent.addMessage(role="assistant", content=llm_result["content"])

    def parser(self, generator):
        content_parts = []
        tool_result = ('', False)
        reasoning_buffer = "" 
        
        for chunk in generator:
            if chunk.get("content") is None:
                chunk["content"] = ""
            if "tool_name" in chunk:
                yield chunk
            elif "tool_calls" in chunk and chunk["id"] != '':
                whole_content = "".join(content_parts)
                if whole_content:
                    self.messages.append({"role": "assistant", "content": whole_content})
                content_parts = []  
                reasoning_buffer = "" 
                tool_call = chunk["tool_calls"][0]
                function_args = tool_call["function"]["arguments"]
                
                yield {"role": "assistant", "tool_arguments": function_args, "content": ""}
                
                try:
                    args = json.loads(function_args)
                    if args is None:
                        error_msg = "工具参数为空"
                        yield {"role": "assistant", "content": error_msg}
                        self.__limit_messages()
                        
                        yield from self.predict(input_text=f"{error_msg}，请重新输入，你之前输入的内容为：\n{whole_content}", stream=True)
                        continue
                except json.JSONDecodeError as e:
                    error_msg = f"工具参数解析失败:{e}"
                    yield {"role": "tool", "content": error_msg}
                    
                    yield from self.predict(input_text=f"{error_msg}，请重新输入，你之前输入的内容为：\n{whole_content}", stream=True)
                    continue
                
                tool_call_obj = {
                    "tool_call_id": chunk["id"],
                    "function": {
                        "name": tool_call["function"]["name"],
                        "arguments": function_args
                    }
                }
                
                self.tools_call.append(tool_call_obj)
                
                if self.isExecute:
                    tool_result = self.__execute_tool(tool_call["function"]["name"], args, tool_call_obj)
                    yield {"role": "tool", "content": tool_result[0]}
                    
                    if tool_result[1]:
                        self.messages.append({"role": "assistant", "tool_calls": [tool_call_obj]})
                        self.messages.append({"role": "tool", "content": f"工具调用结果：\n{tool_result[0]}"})
                        
                        yield from self.predict(input_text=None, stream=True)
                
            elif "reasoning_content" in chunk:
                reasoning_content = chunk.get("reasoning_content", "")
                if reasoning_content:
                    reasoning_buffer += reasoning_content
                    yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}                
            else:
                content = chunk.get("content", "")
                if content:
                    content_parts.append(content)
                    yield {"role": "assistant", "content": content}                
        whole_content = "".join(content_parts)
        if whole_content:
            self.messages.append({"role": "assistant", "content": whole_content})
            self.__sent_message({"role": "assistant", "content": whole_content})

    def __execute_tool(self, tool_name, args, tool_call_obj, max_input=None)-> tuple[str, bool]:
        """执行工具调用并返回结果"""
        tool_call = (tool_name, args, True)
        
        # 根据工具名称选择执行方式
        if tool_name.startswith("mcp_"):
            tool_result = MCPToolExecutor.execute_mcp_tool(tool_name, args, tools = self.tools,mcp_client=self.mcpclient)

                
        else:
            tool_result = (self.tools.execute(tool_name, **args), True)
            
            
            
        # 记录工具调用结果
        result_record = {
            "id": tool_call_obj["tool_call_id"],
            "name": tool_name,
            "arguments": tool_call_obj["function"]["arguments"],
            "result": tool_result[0],
            "success": tool_result[1]
        }
        
        self.tools_call_result.append(result_record)
        if len(str(tool_result[0])) > self._max_tools_output_length:
            tool_result = (str(tool_result[0])[:self._max_tools_output_length-3] + "...", tool_result[1])
        return tool_result

    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[str, None, None]:
        pass


class AgentUsingLocalModel(Agent):
    """
    本地模型智能体类，继承自Agent
    主要区别在于解析方式和消息处理
    """
    
    def __init__(self, LLM: BaseAPI, tools: Tools, sys_prompt: str = None, isExecute: bool = True, MCP: MCPClient = None, context_limit: int = 8000):
        super().__init__(LLM, tools, sys_prompt, isExecute, MCP, context_limit)

    def predict(self, input_text: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 0,
                min_p: float = 0.0,
                stream: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        if input_text is not None:
            self.messages.append(
            {"role": "user", "content": input_text}
            )
        if stream:
            llm_result = self.llm.predict(
                messages=self.messages,
                temperature=temperature,
                tools=self.tools.getTools(),
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=stream,
            )
            return self.tag_parser(text_generator=llm_result, tag="<tool_call>")
        else:
            tool_call = False
            while True:
                llm_result = self.llm.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.tools.tools,
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=stream
                )
                parser_result = local_model_llama_cpp_parser(llm_result["content"], self.tools, self.llm)
                tool_call = parser_result[2]
                if tool_call == False:
                    self.messages.append(
                        llm_result
                    )
                    return llm_result 
                else:
                    result = AgentExecutor.execute(parser_result, self.tools)
                    self.messages.append(
                        {"role": "tool", "content": "工具的执行结果为：\n" + result[0]}
                    )
                    continue

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
                    tool_call_parsed = local_model_llama_cpp_parser(tool_call, self.tools, self.llm)
                    
                    # 提取工具名称
                    tool_name = tool_call_parsed[0]
                    yield {"role": "system", "tool_name": tool_name, "content": f"正在执行工具：{tool_name}"}
                    
                    result = AgentExecutor.execute(tool_call_parsed, self.tools, LLM=self.llm)
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


Agent_API = Agent
Agent_LOCAL = AgentUsingLocalModel
