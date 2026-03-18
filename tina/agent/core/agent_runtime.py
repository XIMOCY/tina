from ...llm.base_api import BaseAPI
from ...llm.base_multimodal_api import BaseMultimodalAPI
from ...mcp import MCPClient
from .tools import Tools
from .context_manager import BaseContextManager
from typing import Generator
from .state import AgentState
from .events import AgentEvents


class BaseAgentRuntime:
    """
    Agent运行时环境，包含LLM、工具、系统提示等信息
    可以继承并重写对应的方法：
    run_prediction_no_stream(instruction: str = None,...) 同步版本的非流式预测流程
    run_prediction_stream(instruction: str = None,...) 同步版本的流式预测流程
    arun_prediction_no_stream(instruction: str = None,...) 异步版本的非流式预测流程
    arun_prediction_stream(instruction: str = None,...) 异步版本的流式预测流程
    我提供了工具执行的方法，只需要传递tool_calls参数：
    _execute_tool(_tool_calls) 同步版本的工具执行方法
    _aexecute_tool(_tool_calls) 异步版本的工具执行方法
    """

    llm: BaseAPI
    tools: Tools
    context_manager: BaseContextManager
    mcp_client: MCPClient
    state: AgentState

    def __init__(self, llm, tools, context_manager, events=None, mcp_client=None):
        self.llm = llm
        self.tools = tools
        self.context_manager = context_manager
        self.mcp_client = mcp_client
        self.events: AgentEvents = events
        self.state = AgentState.IDLE

    def run_prediction_no_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ):
        """
        非流式的预测
        """
        self._instruction(instruction)

    def run_prediction_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ):
        """
        流式的预测
        """
        self._instruction(instruction)

    async def arun_prediction_no_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ):
        await self._ainstruction(instruction)

    async def arun_prediction_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ):
        await self._ainstruction(instruction)

    def _instruction(self, instruction):
        if instruction is not None:
            instruction = self.events.trigger_before_user_instruction(
                user_message=instruction
            )
            self.context_manager.add_user_message(instruction)

    async def _ainstruction(self, instruction):
        if instruction is not None:
            instruction = await self.events.atrigger_before_user_instruction(
                user_message=instruction
            )
            self.context_manager.add_user_message(instruction)

    def _execute_tool(self, _tool_calls) -> str:
        """执行工具调用并返回结果"""

        # before_tool_calls 事件
        self.events.trigger_before_tool_calls(_tool_calls)

        # 默认工具执行方式
        tool_result = self.tools.execute(
            _tool_calls, self.mcp_client, events=self.events
        )
        self.context_manager.add_tool_calls_result(tool_result)

        # after_tool_calls 事件
        self.events.trigger_after_tool_calls(tool_result)

        return tool_result

    async def _aexecute_tool(self, _tool_calls) -> str:
        """异步执行工具调用并返回结果"""

        await self.events.atrigger_before_tool_calls(_tool_calls)

        tool_result = await self.tools.aexecute(
            _tool_calls, self.mcp_client, events=self.events
        )
        self.context_manager.add_tool_calls_result(tool_result)

        # after_tool_calls 事件
        await self.events.atrigger_after_tool_calls(tool_result)

        return tool_result


class ToolCallingAgentRuntime(BaseAgentRuntime):
    def __init__(
        self,
        llm: BaseAPI,
        tools: Tools,
        context_manager: BaseContextManager,
        events,
        max_tool_loop: int = 30,
        mcp_client: MCPClient = None,
    ):
        super().__init__(llm, tools, context_manager, events, mcp_client)
        self.max_tool_loop = max_tool_loop

    def run_prediction_no_stream(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ) -> dict:
        super().run_prediction_no_stream(instruction, temperature, top_p, top_k, min_p)
        counter = 0
        while counter < self.max_tool_loop:
            self.state = AgentState.THINKING
            llm_response = self.llm.predict_no_stream(
                messages=self.context_manager.get_messages(),
                temperature=temperature,
                tools=self.tools.get_tools_for_llm(),
                top_p=top_p,
            )

            if "tool_calls" in llm_response:
                self.state = AgentState.TOOL_CALLING
                _tool_calls = llm_response["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                self._execute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.state = AgentState.RESPONDING
                _, llm_response["content"] = self.events.trigger_after_user_instruction(
                    user_message=instruction, assistant_message=llm_response["content"]
                )
                self.context_manager.add_assistant_message(llm_response["content"])
                # 用户输入后事件（同步非流式）

                return llm_response
        self.state = AgentState.IDLE
        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    def run_prediction_stream(
        self, instruction=None, temperature=0.5, top_p=0.9, top_k=1, min_p=0
    ) -> Generator[dict, None, None]:
        super().run_prediction_stream(instruction, temperature, top_p, top_k, min_p)
        counter = 0
        while counter < self.max_tool_loop:
            tool_called = False
            llm_response = self.llm.predict_stream(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
            )
            content_parts: list = []
            reasoning_buffer: str = ""

            self.state = AgentState.RESPONDING

            for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    self.state = AgentState.TOOL_CALLING
                    self.events.trigger_on_stream_chunk(chunk)
                    yield chunk
                # id用于检验这次的工具传输有没有断流 如果没有id则说明这次的工具调用是不完整的
                elif "tool_calls" in chunk and chunk["id"] != "":
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []
                    reasoning_buffer = ""

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])
                    self.events.trigger_on_stream_chunk(chunk)
                    yield chunk

                    results = self._execute_tool(chunk["tool_calls"])
                    for result in results:
                        self.events.trigger_on_stream_chunk(result)
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break

                elif "reasoning_content" in chunk:
                    self.state = AgentState.THINKING
                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        reasoning_content_chunk = {
                            "role": "assistant",
                            "reasoning_content": reasoning_content,
                            "content": "",
                        }
                        self.events.trigger_on_stream_chunk(reasoning_content_chunk)
                        yield reasoning_content_chunk
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        content_chunk = {"role": "assistant", "content": content}
                        self.events.trigger_on_stream_chunk(content_chunk)
                        yield content_chunk

            whole_content = "".join(content_parts)
            if whole_content:
                _, whole_content = self.events.trigger_after_user_instruction(
                    user_message=instruction, assistant_message=whole_content
                )
                self.context_manager.add_assistant_message(whole_content)
                # 用户输入后事件（同步流式）

            if tool_called:
                continue
            break
        self.state = AgentState.IDLE

        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    async def arun_prediction_no_stream(
        self, instruction=None, temperature=0.5, top_p=0.9, top_k=1, min_p=0
    ):
        await super().arun_prediction_no_stream(
            instruction, temperature, top_p, top_k, min_p
        )
        counter = 0
        while counter < self.max_tool_loop:
            self.state = AgentState.THINKING
            llm_result = await self.llm.apredict(
                messages=self.context_manager.get_messages(),
                temperature=temperature,
                tools=self.tools.get_tools_for_llm(),
                top_p=top_p,
            )
            if "tool_calls" in llm_result:
                self.state = AgentState.TOOL_CALLING
                _tool_calls = llm_result["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                await self._aexecute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.state = AgentState.RESPONDING
                _, llm_result["content"] = (
                    await self.events.atrigger_after_user_instruction(
                        user_message=instruction,
                        assistant_message=llm_result["content"],
                    )
                )
                self.context_manager.add_assistant_message(llm_result["content"])
                # 用户输入后事件（异步非流式）

                return llm_result
        self.state = AgentState.IDLE
        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    async def arun_prediction_stream(
        self, instruction=None, temperature=0.5, top_p=0.9, top_k=1, min_p=0
    ):
        await super().arun_prediction_stream(
            instruction, temperature, top_p, top_k, min_p
        )
        counter = 0
        while counter < self.max_tool_loop:
            tool_called = False
            llm_response = await self.llm.apredict(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=True,
            )
            content_parts: list = []
            reasoning_buffer: str = ""
            self.state = AgentState.RESPONDING
            async for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    await self.events.atrigger_on_stream_chunk(chunk)
                    self.state = AgentState.TOOL_CALLING
                    yield chunk

                elif "tool_calls" in chunk and chunk["id"] != "":
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []
                    reasoning_buffer = ""

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])
                    await self.events.atrigger_on_stream_chunk(chunk)
                    yield chunk

                    results = await self._aexecute_tool(chunk["tool_calls"])
                    for result in results:
                        await self.events.atrigger_on_stream_chunk(result)
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break

                elif "reasoning_content" in chunk:
                    self.state = AgentState.THINKING
                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        reasoning_content_chunk = {
                            "role": "assistant",
                            "reasoning_content": reasoning_content,
                            "content": "",
                        }
                        await self.events.atrigger_on_stream_chunk(
                            reasoning_content_chunk
                        )
                        yield reasoning_content_chunk
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        content_chunk = {"role": "assistant", "content": content}
                        await self.events.atrigger_on_stream_chunk(content_chunk)
                        yield content_chunk

            whole_content = "".join(content_parts)
            if whole_content:
                _, whole_content = await self.events.atrigger_after_user_instruction(
                    user_message=instruction, assistant_message=whole_content
                )
                self.context_manager.add_assistant_message(whole_content)
                # 用户输入后事件（异步流式）

            if tool_called:
                continue
            break
        self.state = AgentState.IDLE

        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")


class ToolCallingMutilemodalAgentRuntime(BaseAgentRuntime):
    def __init__(
        self,
        llm: BaseMultimodalAPI,
        tools: Tools,
        context_manager: BaseContextManager,
        events,
        max_tool_loop: int = 30,
        mcp_client: MCPClient = None,
    ):
        self.llm = llm
        self.tools = tools
        self.context_manager = context_manager
        self.events = events
        self.mcp_client = mcp_client
        self.max_tool_loop = max_tool_loop

    def run_prediction_no_stream(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
    ) -> dict:
        self.context_manager.add_user_message(
            instruction=instruction, image=image, audio=audio, url=url
        )
        counter = 0
        while counter < self.max_tool_loop:
            self.state = AgentState.THINKING
            llm_response = self.llm.predict_no_stream(
                messages=self.context_manager.get_messages(),
                temperature=temperature,
                tools=self.tools.get_tools_for_llm(),
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
            )

            if "tool_calls" in llm_response:
                self.state = AgentState.TOOL_CALLING
                _tool_calls = llm_response["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                self._execute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.state = AgentState.RESPONDING
                self.context_manager.add_assistant_message(llm_response["content"])
                # 用户输入后事件（同步非流式）
                llm_assistant_message = llm_response["content"]
                _, llm_assistant_message = self.events.trigger_after_user_instruction(
                    user_message=instruction, assistant_message=llm_assistant_message
                )
                return llm_response
        self.state = AgentState.IDLE
        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    def run_prediction_stream(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0,
    ) -> Generator[dict, None, None]:
        self.context_manager.add_user_message(
            instruction=instruction, image=image, audio=audio, url=url
        )
        counter = 0
        while counter < self.max_tool_loop:

            tool_called = False
            llm_response = self.llm.predict_stream(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
            )
            content_parts: list = []
            reasoning_buffer: str = ""

            self.state = AgentState.RESPONDING

            for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    self.events.trigger_on_stream_chunk(chunk)
                    self.state = AgentState.TOOL_CALLING

                    yield chunk

                elif "tool_calls" in chunk and chunk["id"] != "":
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []
                    reasoning_buffer = ""

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])

                    results = self._execute_tool(chunk["tool_calls"])
                    for result in results:
                        self.events.trigger_on_stream_chunk(result)
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break

                elif "reasoning_content" in chunk:

                    self.state = AgentState.THINKING

                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        reasoning_content_chunk = {
                            "role": "assistant",
                            "reasoning_content": reasoning_content,
                            "content": "",
                        }
                        self.events.trigger_on_stream_chunk(reasoning_content_chunk)
                        yield reasoning_content_chunk
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        content_chunk = {"role": "assistant", "content": content}
                        self.events.trigger_on_stream_chunk(content_chunk)
                        yield content_chunk

            whole_content = "".join(content_parts)
            if whole_content:
                # 用户输入后事件（同步流式）
                _, whole_content = self.events.trigger_after_user_instruction(
                    user_message=instruction, assistant_message=whole_content
                )
                self.context_manager.add_assistant_message(whole_content)

            if tool_called:
                continue
            break

        self.state = AgentState.IDLE

        if counter > self.max_tool_loop:

            self.state = AgentState.ERROR

            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    async def arun_prediction_no_stream(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature=0.5,
        top_p=0.9,
        top_k=1,
        min_p=0,
    ):
        self.context_manager.add_user_message(
            instruction=instruction, image=image, audio=audio, url=url
        )
        counter = 0
        while counter < self.max_tool_loop:
            self.state = AgentState.THINKING
            llm_result = await self.llm.apredict(
                messages=self.context_manager.get_messages(),
                temperature=temperature,
                tools=self.tools.get_tools_for_llm(),
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
            )
            if "tool_calls" in llm_result:
                self.state = AgentState.TOOL_CALLING
                _tool_calls = llm_result["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                await self._aexecute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.state = AgentState.RESPONDING
                self.context_manager.add_assistant_message(llm_result["content"])
                # 用户输入后事件（异步非流式）
                _, llm_result["content"] = (
                    await self.events.atrigger_after_user_instruction(
                        user_message=instruction,
                        assistant_message=llm_result["content"],
                    )
                )
                return llm_result
        self.state = AgentState.IDLE
        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")

    async def arun_prediction_stream(
        self,
        instruction: str = None,
        image: str | list[str] = None,
        audio: str | list[str] = None,
        url: str | list[str] = None,
        temperature=0.5,
        top_p=0.9,
        top_k=1,
        min_p=0,
    ):
        self.context_manager.add_user_message(
            instruction=instruction, image=image, audio=audio, url=url
        )
        counter = 0
        while counter < self.max_tool_loop:
            tool_called = False
            llm_response = await self.llm.apredict(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=True,
            )
            content_parts: list = []
            reasoning_buffer: str = ""
            self.state = AgentState.RESPONDING
            async for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    await self.events.atrigger_on_stream_chunk(chunk)
                    self.state = AgentState.TOOL_CALLING
                    yield chunk

                elif "tool_calls" in chunk and chunk["id"] != "":
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []
                    reasoning_buffer = ""

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])

                    results = await self._aexecute_tool(chunk["tool_calls"])
                    for result in results:
                        await self.events.atrigger_on_stream_chunk(result)
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break

                elif "reasoning_content" in chunk:
                    self.state = AgentState.THINKING
                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        reasoning_content_chunk = {
                            "role": "assistant",
                            "reasoning_content": reasoning_content,
                            "content": "",
                        }
                        await self.events.atrigger_on_stream_chunk(
                            reasoning_content_chunk
                        )
                        yield reasoning_content_chunk
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        content_chunk = {"role": "assistant", "content": content}
                        await self.events.atrigger_on_stream_chunk(content_chunk)
                        yield content_chunk

            whole_content = "".join(content_parts)
            if whole_content:
                _, whole_content = await self.events.atrigger_after_user_instruction(
                    user_message=instruction, assistant_message=whole_content
                )

                self.context_manager.add_assistant_message(whole_content)
                # 用户输入后事件（异步流式）

            if tool_called:
                continue
            break
        self.state = AgentState.IDLE

        if counter > self.max_tool_loop:
            self.state = AgentState.ERROR
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")
