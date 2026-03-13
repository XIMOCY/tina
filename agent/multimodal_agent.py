"""
编写者：王出日
日期：2026，3，13
版本 0.5.0
功能：Agent类，实现了智能体的功能。
包含：
Agent类：基础智能体类，默认支持API调用
AgentByLocalModel类：本地模型智能体类，继承自Agent
"""
from __future__ import annotations

from typing import List, Union, Generator, Iterator, Dict, Any, AsyncGenerator

from ..llm.base_api import BaseMultimodalAPI
from .core.tools import Tools
from ..mcp.client import MCPClient
from .core.prompt import Prompt
from .core.context_manager import MultimodalContextManager
from .core.agent_runtime import BaseAgentRuntime,ToolCallingMutilemodalAgentRuntime
from .core.events import AgentEvents

from .agent import Agent


class MultimodalAgent(Agent):
    """
    基础智能体类，默认支持API调用方式
    默认实现了ToolCallingAgent
    """
    llm: BaseMultimodalAPI
    tools: Tools  
    def __init__(self,
                  llm: BaseMultimodalAPI, 
                  tools: Tools, 
                  system_prompt: str = None, 
                  execute_tool: bool = True, 
                  mcp: MCPClient = None,
                  events: AgentEvents = None,
                  context_manager:MultimodalContextManager=None,
                  agent_runtime: BaseAgentRuntime = None,
                  max_tool_loop:int = 30,
                  max_context_length:int = 100000,
                  max_tool_result_length:int = 6000,
                  name:str="None"):
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
        self.mcp_client = mcp
        if context_manager is None:
            self.context_manager = MultimodalContextManager(tools=self.tools,max_length=max_context_length,max_tool_result_length=max_tool_result_length)
        else:
            self.context_manager = context_manager
        # 初始化MCP
        self._mcp_to_tools(mcp)
        self.events = AgentEvents() if events is None else events
        if system_prompt is not None:
            self.context_manager.set_system_message(system_prompt)
        else:
            self.context_manager.set_system_message(Prompt("tina").prompt)
        # 初始化消息，可以直接使用context_manager来修改messages
        self.messages = self.context_manager.get_messages()

        if agent_runtime is None:
            self.runtime = ToolCallingMutilemodalAgentRuntime(self.llm, self.tools, self.context_manager,self.events,max_tool_loop=max_tool_loop,mcp_client=mcp)
        else:
            self.runtime = agent_runtime
 
    def predict(self, 
                instruction: str = None,
                image: str|list[str] = None,
                audio: str|list[str] = None,
                url: str|list[str] = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                stream: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        if stream:
            return self.runtime.run_prediction_stream(
                instruction,
                image,
                audio,
                url,
                temperature,
                top_p,
                top_k,
                min_p,
            )
        else:
            
            return self.runtime.run_prediction_no_stream(
                instruction,
                image,
                audio,
                url,
                temperature,
                top_p,
                top_k,
                min_p,
            )


    async def apredict(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: bool = True,
    ) -> Union[str, AsyncGenerator[Dict[str, Any], None]]:
        """
        异步版本的 predict，默认流式输出
        """
        if stream:
            return self.runtime.arun_prediction_stream(
                instruction,
                image,
                audio,
                url,
                temperature,
                top_p,
                top_k,
                min_p,
            )
        else:
            return await self.runtime.arun_prediction_no_stream(
                instruction,
                image,
                audio,
                url,
                temperature,
                top_p,
                top_k,
                min_p,
            )
        
