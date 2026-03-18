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

from typing import (
    List,
    Literal,
    Union,
    Generator,
    Iterator,
    Dict,
    Any,
    AsyncGenerator,
    overload,
)

from ..llm.base_multimodal_api import BaseMultimodalAPI
from .core.tools import Tools
from ..mcp.client import MCPClient
from .core.prompt import Prompt
from .core.context_manager import MultimodalContextManager
from .core.agent_runtime import BaseAgentRuntime, ToolCallingMutilemodalAgentRuntime
from .core.events import AgentEvents

from .agent import Agent
from .core.agent_response import AgentResponse


class MultimodalAgent(Agent):
    """
    基础智能体类，默认支持API调用方式
    默认实现了ToolCallingAgent
    """

    llm: BaseMultimodalAPI
    tools: Tools

    def __init__(
        self,
        llm: BaseMultimodalAPI,
        tools: Tools | list[Tools],
        system_prompt: str = None,
        mcp: MCPClient = None,
        events: AgentEvents = None,
        context_manager: MultimodalContextManager = None,
        agent_runtime: BaseAgentRuntime = None,
        max_tool_loop: int = 30,
        max_context_length: int = 100000,
        max_tool_result_length: int = 6000,
        name: str = "None",
    ):
        """
        实例化一个Agent对象

        Args:
            LLM: tina.BaseAPI类型，调用的LLM对象
            tools: tina.Tools类型，工具集
            sys_prompt: str 系统提示词
            MCP: tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
            events: tina.AgentEvents类型，事件管理器，用于管理事件，
            context_manager: tina.ContextManager类型，上下文管理器，
            agent_runtime: tina.BaseAgentRuntime类型，运行时，
            max_tool_loop: int 默认30，最多循环次数
            name: str 智能体名字，用于多Agent区分
        """
        # 智能体的名称
        self.name = name

        # 运行需要的实例
        self.llm = llm
        self._init_tools(tools, name)

        self.tools_call_result = []
        self.tools_call = []
        self.mcp_client = mcp
        if context_manager is None:
            self.context_manager = MultimodalContextManager(
                tools=self.tools,
                max_length=max_context_length,
                max_tool_result_length=max_tool_result_length,
            )
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
            self.runtime = ToolCallingMutilemodalAgentRuntime(
                self.llm,
                self.tools,
                self.context_manager,
                self.events,
                max_tool_loop=max_tool_loop,
                mcp_client=mcp,
            )
        else:
            self.runtime = agent_runtime

    @overload
    def predict(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: Literal[True] = True,
    ) -> Generator[AgentResponse, None, None]: ...

    @overload
    def predict(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: Literal[False] = False,
    ) -> AgentResponse: ...
    def predict(
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
    ):
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
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        异步版本的 predict，默认流式输出
        """
        async for chunk in self.runtime.arun_prediction_stream(
            instruction,
            image,
            audio,
            url,
            temperature,
            top_p,
            top_k,
            min_p,
        ):
            yield AgentResponse(**chunk)

    async def apredict_no_stream(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ) -> AgentResponse:
        result = await self.runtime.arun_prediction_no_stream(
            instruction,
            image,
            audio,
            url,
            temperature,
            top_p,
            top_k,
            min_p,
        )
        return AgentResponse(**result)
