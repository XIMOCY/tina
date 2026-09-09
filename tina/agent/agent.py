"""
编写者：王出日
日期：2026，3，13
版本 0.5.0
功能：Agent类，实现了智能体的功能。
包含：
Agent类：基础智能体类，默认支持API调用
"""

from __future__ import annotations

import re
from typing import List, Literal, Union, Generator, Dict, Any, AsyncGenerator, overload

from tina.agent.core.agent_response import AgentResponse, ToolCall
from tina.agent.core.state import AgentState

from ..llm.base_api import BaseAPI
from .core.tools import Tools
from .core.keyword_actions import KeywordActions
from ..mcp.client import MCPClient
from .core.prompt import Prompt
from .core.context_manager import ContextManager
from .core.agent_runtime import ToolCallingAgentRuntime, BaseAgentRuntime
from .core.events import AgentEvents
from ..core.error import TinaError
from ..core import logger


_KEYWORD_ACTION_BLOCK_RE = re.compile(
    r"\n*\s*<keyword_action>.*?</keyword_action>\s*",
    re.DOTALL | re.IGNORECASE,
)


class Agent:
    """
    基础智能体类，默认支持API调用方式
    默认实现了ToolCallingAgent
    """

    llm: BaseAPI
    tools: Tools
    keyword_actions: KeywordActions | None

    def __init__(
        self,
        llm: BaseAPI,
        tools: Tools | list[Tools] = None,
        system_prompt: str = None,
        mcp: MCPClient = None,
        events: AgentEvents = None,
        context_manager: ContextManager = None,
        agent_runtime: BaseAgentRuntime = None,
        max_tool_loop: int = 30,
        max_context_length: int = 100000,
        max_tool_result_length: int = 6000,
        name: str = None,
        keyword_actions: KeywordActions = None,
    ):
        """
        实例化一个Agent对象

        Args:
            LLM: tina.BaseAPI类型，调用的LLM对象
            tools: tina.Tools类型，工具集
            sys_prompt: str 系统提示词
            MCP: tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
            context_length: int 最大上下文长度，超过该长度则删除旧消息，保留最近的消息。
            context_limit: int 上下文限制，使用大模型来总结你的上下文，数字为0时不触发
            max_tool_loop: int 最大工具调用次数，超过该次数则停止调用工具
            name: str 智能体名字，用于多Agent区分
            keyword_actions: KeywordActions，可选关键词动作（不进 tools schema）；
                有绑定时会自动追加到 system prompt 末尾的 <keyword_action> 块
        """
        # 智能体的名称
        self.name = name

        # 运行需要的实例
        self.llm = llm
        self._init_tools(tools, name)
        self.keyword_actions = keyword_actions
        self.mcp_client = mcp
        if context_manager is None:
            self.context_manager = ContextManager(
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
        self._inject_keyword_actions_prompt()

        self.messages = self.context_manager.get_messages()
        if agent_runtime is None:
            self.runtime = ToolCallingAgentRuntime(
                self.llm,
                self.tools,
                self.context_manager,
                self.events,
                max_tool_loop=max_tool_loop,
                mcp_client=mcp,
                keyword_actions=self.keyword_actions,
            )
        else:
            self.runtime = agent_runtime
            if (
                self.keyword_actions is not None
                and getattr(self.runtime, "keyword_actions", None) is None
            ):
                self.runtime.keyword_actions = self.keyword_actions
        self.other_agents = []

    def set_keyword_actions(self, keyword_actions: KeywordActions | None) -> None:
        """挂载或替换 KeywordActions；会同步更新 system prompt 末尾的说明块。"""
        self.keyword_actions = keyword_actions
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.keyword_actions = keyword_actions
        self._inject_keyword_actions_prompt()

    def _strip_keyword_action_block(self, prompt: str) -> str:
        if not prompt:
            return ""
        return _KEYWORD_ACTION_BLOCK_RE.sub("", prompt).rstrip()

    def _inject_keyword_actions_prompt(self) -> None:
        """
        将 KeywordActions 说明块追加到 system prompt 末尾：
        <keyword_action>...</keyword_action>
        """
        prompt = self._strip_keyword_action_block(
            self.context_manager.get_system_message() or ""
        )
        block = ""
        if self.keyword_actions is not None:
            block = self.keyword_actions.build_prompt_block()
        if block:
            wrapped = f"<keyword_action>\n{block}\n</keyword_action>"
            self.context_manager.set_system_message(f"{prompt}\n\n{wrapped}" if prompt else wrapped)
            logger.warn("使用了关键词动作，会影响你的系统提示词")
        else:
            self.context_manager.set_system_message(prompt)

    def filter_visible(self, content: str) -> str:
        """
        Hide 可见过滤（跨 chunk 缓冲）。on_stream_chunk 不可改写 chunk，
        请在消费流式输出时自行调用本方法。
        """
        if self.keyword_actions is None:
            return content or ""
        return self.keyword_actions.filter_visible(content)

    def flush_visible(self) -> str:
        """回合末吐出 Hide 截留缓冲。"""
        if self.keyword_actions is None:
            return ""
        return self.keyword_actions.flush_visible()

    def build_keyword_actions_prompt_block(self) -> str:
        """生成可拼进 system prompt 的关键词动作说明块。"""
        if self.keyword_actions is None:
            return ""
        return self.keyword_actions.build_prompt_block()

    def _init_tools(self, tools, name):
        if tools is None:
            self._create_self_tools(name)
        elif isinstance(tools, list):
            self._create_self_tools(name)
            self.tools.add_tools(tools)
        elif isinstance(tools, Tools):
            self.tools = tools

    def _create_self_tools(self, name):
        self.tools = Tools(
                name="_self",
                metadata={
                    "name": name,
                    "description": "Agent自己的工具包，实例化时指定的工具包会被添加到这个工具包里面",
                },
            )

    @property
    def state(self) -> AgentState:
        """
        获取当前Agent的状态
        """
        return self.runtime.state

    def add_tools(self, tools: Tools | list[Tools]) -> None:
        """
        添加工具包
        """
        self.tools.add_tools(tools)

    # 事件管理
    def add_on_stream_chunk_handler(self, func: callable | list[callable]):
        """
        在大模型处理用户输入时，每处理一个chunk，都会调用此函数
        需要事件处理函数接受下面的参数：
        chunk: dict[str,str] or AgentResponse
        """
        self.events.add_on_stream_chunk_handler(func)

    def add_before_tool_call_handler(self, func: callable | list[callable]):
        """
        在执行工具调用之 前
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,
        """
        self.events.add_before_tool_call_handler(func)

    def add_after_tool_call_handler(self, func: callable | list[callable]):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,tool_result: any
        """
        self.events.add_after_tool_call_handler(func)

    def add_before_tool_calls_handler(self, func: callable | list[callable]):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        self.events.add_before_tool_calls_handler(func)

    def add_after_tool_calls_handler(self, func: callable | list[callable]):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        self.events.add_after_tool_calls_handler(func)

    def add_on_tool_confirmation_handler(self, func: callable):
        """
        如果一个工具被登记为需要验证猜可以运行，请监听此事件
        需要事件处理函数接受下面的参数：
        tool_name: str tool_arguments: dict
        """
        self.events.add_on_tool_confirmation_handler(func)

    def add_before_user_instruction_handler(self, func: callable | list[callable]):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：
        user_message: str
        """
        self.events.add_before_user_instruction_handler(func)

    def add_after_user_instruction_handler(self, func: callable | list[callable]):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：
        user_message: str assistant_message: str
        """
        self.events.add_after_user_instruction_handler(func)

    def before_tool_call(self):
        """
        在执行工具调用之 前
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,
        """
        return self.events.before_tool_call()

    def after_tool_call(self):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,tool_result: any
        """
        return self.events.after_tool_call()

    def before_tool_calls(self):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        return self.events.before_tool_calls()

    def after_tool_calls(self):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        return self.events.after_tool_calls()

    def before_user_instruction(self):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：
        user_message: str
        """
        return self.events.before_user_instruction()

    def after_user_instruction(self):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：
        user_message: str assistant_message: str
        """
        return self.events.after_user_instruction()

    def on_tool_confirmation(self):
        """
        如果一个工具被登记为需要验证才可以运行，请监听此事件
        需要事件处理函数接受下面的参数：
        tool_name: str tool_arguments: dict
        """
        return self.events.on_tool_confirmation()

    def on_stream_chunk(self):
        """
        当大模型生成一个结果时，会触发此事件
        需要事件处理函数接受下面的参数：
        chunk: dict 或者 AgentResponse
        """
        return self.events.on_stream_chunk()

    def on_turn_end(self):
        """
        在每次推理完结后执行，不需要参数
        """
        return self.events.on_turn_end()

    def add_on_turn_end_handler(self, func: callable | list[callable]):
        """
        在每次推理完结后执行，不需要参数
        """
        self.events.add_on_turn_end_handler(func)

    def _mcp_to_tools(self, MCP):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcp_client = MCP
                _tools = self.mcp_client.to_tina_tools()
                self.tools.add_tools(_tools)
        except Exception as e:
            raise e

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

    def get_system_prompt(self) -> str:
        """
        获取当前Agent的提示词
        """
        return self.context_manager.get_system_message()

    def set_system_prompt(self, prompt: str) -> None:
        """
        设置系统提示词
        Args:
            prompt: 系统提示词
        """
        self.context_manager.set_system_message(prompt)
        self._inject_keyword_actions_prompt()

    def get_last_tool_call(self) -> ToolCall | None:
        """
        获取最近一次工具调用信息
        Returns:
            ToolCall | None: 最近一次工具调用，如果没有则返回 None
        """
        calls = self.context_manager.get_tool_calls()
        if not calls:
            return None
        return ToolCall(calls[-1])

    def get_last_tool_result(self) -> dict | None:
        """
        获取最近一次工具调用的结果
        Returns:
            dict | None: 最近一次工具调用结果，如果没有则返回 None
        """
        results = self.context_manager.get_tools_result()
        return results[-1] if results else None

    def connect_agent(self, agent: "Agent" | list["Agent"]):
        """
        与另一个Agent共享消息列表
        Args:
            agent:Agent对象
        """
        if type(agent) == list:
            for _agent in agent:
                self.other_agents.append(_agent)
        else:
            self.other_agents.append(agent)

    def disconnect_agent(self, agent: "Agent" | list["Agent"]):
        """
        与另一个Agent断开连接
        Args:
            agent:Agent对象
        """
        if type(agent) == list:
            for _agent in agent:
                self.other_agents.remove(_agent)
        else:
            self.other_agents.remove(agent)

    def add_message(
        self, role: str = None, content: str = None, name: str = None
    ) -> None:
        """
        添加消息
        """
        if role is None or content is None:
            raise TinaError("role和content参数不能为空")
        if role == "user":
            self.context_manager.add_user_message(content)
            return
        elif role == "assistant":
            self.context_manager.add_assistant_message(content, name)
            return

    def add_messages(self, messages: list[dict[str, str]] = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]
        """
        self.messages = self.context_manager.add_messages(messages)

    def get_tools_call_result(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.context_manager.get_tools_result()

    def get_tools_call(self) -> list:
        return self.context_manager.get_tool_calls()

    def add_mcp_server(
        self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90
    ) -> bool:
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

    def remove_mcp_server(self, server_id: str) -> bool:
        """
        移除MCP服务器
        Args:
            server_id:服务器ID
        """
        if self.mcp_client is not None:
            return self.mcp_client.remove_server(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")

    def get_mcp_server_info(
        self, server_id: str = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        获取MCP服务器信息
        Args:
            server_id:服务器ID，如果不传入，则返回所有服务器信息
        """
        if self.mcp_client is not None:
            return self.mcp_client.get_server_info(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")

    @overload
    def predict(
        self,
        instruction: str = None,
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
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: Literal[False] = False,
    ) -> AgentResponse: ...

    def predict(
        self,
        instruction: str = None,
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

            def gen():
                for chunk in self.runtime.run_prediction_stream(
                    instruction,
                    temperature,
                    top_p,
                    top_k,
                    min_p,
                ):
                    yield AgentResponse(**chunk)

            return gen()
        else:
            result = self.runtime.run_prediction_no_stream(
                instruction,
                temperature,
                top_p,
                top_k,
                min_p,
            )
            return AgentResponse(**result)

    async def apredict(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        异步版本的 predict，流式输出,如果需要非流式的输出，请使用 apredict_no_stream
        """
        async for chunk in self.runtime.arun_prediction_stream(
            instruction,
            temperature,
            top_p,
            top_k,
            min_p,
        ):
            yield AgentResponse(**chunk)

    async def apredict_no_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ) -> AgentResponse:
        """
        异步版本的 predict，非流式输出,如果需要流式的输出，请使用 apredict
        """
        result = await self.runtime.arun_prediction_no_stream(
            instruction,
            temperature,
            top_p,
            top_k,
            min_p,
        )
        return AgentResponse(**result)
