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
from typing import List, Union, Generator, Iterator, Dict, Any, AsyncGenerator

from ..llm.BaseAPI import BaseAPI
from .core.tools import Tools
from ..mcp.Client import MCPClient
from .core.prompt import Prompt
from ..mcp.MCPToolExecutor import MCPToolExecutor
from .core.context_manager import ContextManager

from ..core.error import TinaError
from .core.parser import local_model_llama_cpp_parser 

from ..utils.timer import timer, async_stream_timer, stream_timer


class Agent:
    """
    基础智能体类，默认支持API调用方式
    兼容原有tina框架的所有方法和返回值格式
    """
    llm: BaseAPI
    tools: Tools  
    def __init__(self, llm: BaseAPI, tools: Tools, system_prompt: str = None, execute_tool: bool = True, mcp: MCPClient = None,context_manager:ContextManager=None,max_tool_loop:int = 30,name:str="None"):
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
            max_tool_loop: int 最大工具调用次数，超过该次数则停止调用工具
            name: str 智能体名字，用于多Agent区分
        """
        # 智能体的名称
        self.name =name

        # 运行需要的实例
        self.llm = llm
        self.tools = tools
        self.tools_call_result = []
        self.tools_call = []
        self.is_execute = execute_tool
        self.max_tool_loop = max_tool_loop
        self.mcp_client = mcp
        if context_manager is None:
            self.context_manager = ContextManager()
        else:
            self.context_manager = context_manager
        # 初始化MCP
        self._mcp_to_tools(mcp)
        
        if system_prompt is not None:
            self.context_manager.set_system_message(system_prompt)
        else:
            self.context_manager.set_system_message(Prompt("tina").prompt)
        # 初始化消息，可以直接使用context_manager来修改messages
        self.messages = self.context_manager.return_messages()


    def _mcp_to_tools(self, MCP):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcp_client = MCP
                _tools = self.mcp_client.toTinaTools()
                self.tools = _tools + self.tools
                del _tools
        except Exception as e:
            raise e

    def disable_tool(self, tool_name: str) -> bool:
        """
        禁用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.disableTool(tool_name)
    
    def enable_tool(self, tool_name: str) -> bool:
        """
        启用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.enableTool(tool_name)
    
    def get_messages(self) -> list:
        """
        获取当前Agent的消息列表
        Agent会在当前运行状态维护一个自己的消息列表，可以通过该方法获取
        """
        return self.messages
    def clear_messages(self) -> None:
        """
        清理当前Agent的消息列表，只保留前三个系统消息
        """
        self.context_manager.clear_messages()
    
    def get_tools(self) -> list:
        """
        获取当前Agent的工具列表
        """
        return self.tools.get_tools()
    
    def get_prompt(self) -> str:
        """
        获取当前Agent的提示词
        """
        return self.context_manager.get_system_message()
    
    def add_message(self, role: str = None, content: str = None) -> None:
        """
        """
        if role is None or content is None:
            raise TinaError("role和content参数不能为空")
        if role == "user":
            self.context_manager.add_user_message(content)
            return
        elif role == "assistant":
            self.context_manager.add_assistant_message(content)
            return
        
    def add_messages(self,messages: list[dict[str,str]] = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            role:消息的角色，可以是"user"，"assistant"，"system"
            content:消息的内容
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]，注意如果传入了messages，则role和content参数将被忽略
        """
        self.messages = self.context_manager.add_messages(messages)


    def get_tools_call_result(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.context_manager.get_tools_result()
    
    def get_tools_call(self) -> list:
        return self.context_manager.get_tool_calls()
    
    def add_mcp_server(self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
        """
        添加MCP服务器
        Args:
            server_id:服务器ID
            config:服务器配置
            max_retries:最大重试次数
            timeout:超时时间
        """
        if self.mcp_client is not None:
            return self.mcp_client.add_server(server_id, config, max_retries, timeout)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")
        
    def remove_server(self, server_id: str) -> bool:
        """
        移除MCP服务器
        Args:
            server_id:服务器ID
        """
        if self.mcp_client is not None:
            return self.mcp_client.remove_server(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")

    def get_mcp_server_info(self, server_id: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        获取MCP服务器信息
        Args:
            server_id:服务器ID，如果不传入，则返回所有服务器信息
        """
        if self.mcp_client is not None:
            return self.mcp_client.get_server_info(server_id)
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
        # 定义计数器
        counter = 0
        if input_text is not None:
            self.messages = self.context_manager.add_user_message(input_text)
            
        if stream:
  
            llm_result = self.llm.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.tools.get_tools(),
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=stream,
                )
                
            return self.stream_parser(llm_result)
        else:
            
            return self.predict_no_stream(temperature, top_p, stream)
    
        
    @timer
    def predict_no_stream(self, temperature, top_p, stream):
        while True:
            tool_call = False
                
            llm_result = self.llm.predict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.tools.get_tools(),
                    top_p=top_p,
                    stream=stream
                )
            if "tool_calls" in llm_result.keys():
                tool_call = True
                result = self._execute_tool(
                        llm_result["tool_calls"]["function"]["name"],
                        json.loads(llm_result["tool_calls"]["function"]["arguments"]),
                    )
                print(llm_result)
                self.context_manager.add_tool_calls(
                        llm_result["tool_calls"]["id"],
                        llm_result["tool_calls"]["function"],
                    )
                    # self.context_manager.add_tool_call_result(result)
                tool_call = result[1]
            if tool_call == False:
                self.messages.append(
                        llm_result
                    )
                return llm_result 
            else:
                continue

    @stream_timer
    def stream_parser(self, generator):
        content_parts:list = []
        reasoning_buffer:str 
        
        for chunk in generator:
            if chunk.get("content") is None:
                chunk["content"] = ""

            if "tool_name" in chunk or "tool_arguments" in chunk:
                yield chunk

            elif "tool_calls" in chunk and chunk["id"] != '':
                whole_content = "".join(content_parts)

                if whole_content:
                    self.context_manager.add_assistant_message(whole_content)

                content_parts = []  
                reasoning_buffer = "" 

                
                self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])
    
                if self.is_execute:
                    results = self._execute_tool(chunk["tool_calls"])
                    for result in results:
                        yield result
                      
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
    
    @timer
    def _execute_tool(self, _tool_calls)-> str:
        """执行工具调用并返回结果"""
        

         # 默认工具执行方式
        tool_result = self.tools.execute(_tool_calls,self.tools,self.mcp_client)
        self.context_manager.add_tool_calls_result(tool_result)
            
        return tool_result

    def tag_parser(self, text_generator: Iterator[Any], tag="") -> Generator[str, None, None]:
        pass


    async def _aexecute_tool(self, _tool_calls) -> str:
        """异步执行工具调用并返回结果"""
        tool_result = await self.tools.aexecute(_tool_calls, self.tools,self.mcp_client)
        self.context_manager.add_tool_calls_result(tool_result)
        return tool_result

    async def aparser(self, generator) -> AsyncGenerator[Dict[str, Any], None]:
        """
        异步版本的 parser，用于处理流式异步输出
        """
        content_parts: list[str] = []
        reasoning_buffer: str = ""

        async for chunk in generator:
            if chunk.get("content") is None:
                chunk["content"] = ""

            if "tool_name" in chunk or "tool_arguments" in chunk:
                # 直接透传工具消息
                yield chunk

            elif "tool_calls" in chunk and chunk["id"] != "":
                # 先把已经生成的普通内容写入上下文
                whole_content = "".join(content_parts)
                if whole_content:
                    self.context_manager.add_assistant_message(whole_content)

                content_parts = []
                reasoning_buffer = ""

                # 记录工具调用
                self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])

                # 执行工具
                if self.is_execute:
                    result = await self._aexecute_tool(chunk["tool_calls"])
                    # 把工具执行结果也往外推一把，结构与同步 execute 保持一致
                    for result_chunk in result:yield result_chunk
                    # 工具执行后，继续让大模型回答
                    async for msg in await self.apredict(input_text=None, stream=True):
                        yield msg

            elif "reasoning_content" in chunk:
                reasoning_content = chunk.get("reasoning_content", "")
                if reasoning_content:
                    reasoning_buffer += reasoning_content
                    yield {
                        "role": "assistant",
                        "reasoning_content": reasoning_content,
                        "content": "",
                    }
            else:
                content = chunk.get("content", "")
                if content:
                    content_parts.append(content)
                    yield {"role": "assistant", "content": content}

        # 生成结束后，把累计内容写入消息
        whole_content = "".join(content_parts)
        if whole_content:
            self.messages.append({"role": "assistant", "content": whole_content})

    async def apredict(
        self,
        input_text: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: bool = True,
    ) -> Union[str, AsyncGenerator[Dict[str, Any], None]]:
        """
        异步版本的 predict，默认流式输出
        """
        if input_text is not None:
            self.messages = self.context_manager.add_user_message(input_text)

        if stream:
            # 异步获取流式输出（假设 llm.apredict 返回异步生成器）
            llm_result = await self.llm.apredict(
                messages=self.messages,
                temperature=temperature,
                tools=self.tools.get_tools(),
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=True,
            )
            return self.aparser(llm_result)
        else:
            # 非流式异步：每轮调用一次模型，遇到工具调用则先执行工具再继续
            while True:
                tool_call_happened = False

                llm_result = await self.llm.apredict(
                    messages=self.messages,
                    temperature=temperature,
                    tools=self.tools.get_tools(),
                    top_p=top_p,
                    top_k=top_k,
                    min_p=min_p,
                    stream=False,
                )

                if "tool_calls" in llm_result:
                    tool_call_happened = True
                    # 记录工具调用
                    self.context_manager.add_tool_calls(
                        tool_calls=llm_result["tool_calls"]
                    )
                    # 异步执行工具
                    await self._aexecute_tool(llm_result["tool_calls"])
                    # 执行完工具后，继续下一轮循环，请求模型
                    continue

                if not tool_call_happened:
                    self.messages.append(llm_result)
                    return llm_result


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
                tools=self.tools.get_tools(),
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
                    tools=self.tools.tools_schemas,
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
                    result = self.tools.execute(parser_result, self.tools)
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
                    
                    result = self.tools.execute(tool_call_parsed, self.tools, LLM=self.llm)
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
