import asyncio
from typing import TYPE_CHECKING, Callable, Optional

from tina.core import logger
from .message import Message
from .message_bus import MessageBus

if TYPE_CHECKING:
    from tina.agent.agent import Agent


_BUSY_STATES = {"tool_calling", "on_tool_confirm", "error"}


class MultiAgentEnvironment:
    """
    多 Agent 运行环境：管理 Agent 注册与消息通信。

    职责：
    - 管理 Agent 的注册 / 注销；
    - 所有 Agent 就绪后自动注册通信工具（描述中列出可用 Agent）；
    - 通过 MessageBus 分发消息，并给每个 Agent 包装一个收信队列（类似 AgentWorker）；
    - 目标 Agent 空闲时，把消息注入其消息列表并触发推理。

    Agent 的提示词与业务工具由开发者自行设计并注册。
    """

    def __init__(self, name: str = None, bus: Optional[MessageBus] = None):
        """
        Args:
            name: 环境名称，也作为外部指令的发送者名。
            bus: 外部传入的消息总线，缺省时新建一个。
        """
        self.name = name or "environment"
        self.bus = bus if bus is not None else MessageBus()
        self._agents: dict[str, "Agent"] = {}
        self._inboxes: dict[str, asyncio.Queue[Message]] = {}
        # 每个 Agent 正在处理（已被 worker 取出、尚未处理完）的消息
        self._active_messages: dict[str, Message] = {}
        # 队列变化监听器（同步回调，用于 Web 等观测层刷新）
        self._queue_listeners: list[Callable[[], None]] = []
        # 已注册过 before_llm_call 注入处理器的 Agent（避免重启时重复注册）
        self._injection_registered: set[str] = set()
        # 回合失败监听器：listener(agent_name, error, info)；info 见 classify_api_error
        self._error_listeners: list[Callable] = []
        # 后端状态切换监听器：listener(info_or_None)
        self._backend_listeners: list[Callable] = []
        # 最近一次「致命」后端错误（如 402 余额不足 / 401 鉴权）；成功一轮后清空
        self._backend_error: Optional[dict] = None
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._stop_event = asyncio.Event()
        # 打断支持：每个 Agent 当前进行中的推理 task、已流出的部分正文
        self._turns: dict[str, asyncio.Task] = {}
        self._partials: dict[str, str] = {}
        self._interrupted: set[str] = set()

    @property
    def agents(self) -> dict[str, "Agent"]:
        """已注册 Agent 的副本（名称 -> Agent）。"""
        return dict(self._agents)

    @property
    def agent_names(self) -> list[str]:
        """已注册 Agent 的名称列表。"""
        return list(self._agents)

    def add_agent(self, agent: "Agent", name: str = None) -> "Agent":
        """
        注册一个 Agent。

        Args:
            agent: 要注册的 Agent（支持 MultimodalAgent）。
            name: Agent 名称，缺省时使用 agent.name。
        """
        if self._running:
            raise RuntimeError("环境已启动，不能再注册 Agent")
        agent_name = name or getattr(agent, "name", None)
        if not agent_name:
            raise ValueError("注册 Agent 需要提供 name，或先设置 agent.name")
        if agent_name in self._agents:
            raise ValueError(f"Agent 名称已存在: {agent_name}")
        self._agents[agent_name] = agent
        if getattr(agent, "name", None) is None:
            agent.name = agent_name
        return agent

    def remove_agent(self, name: str) -> bool:
        """注销一个 Agent，返回是否成功移除。"""
        if self._running:
            raise RuntimeError("环境运行中，不能注销 Agent")
        return self._agents.pop(name, None) is not None

    def get_agent(self, name: str) -> Optional["Agent"]:
        """按名称获取 Agent，不存在时返回 None。"""
        return self._agents.get(name)

    async def start(self) -> None:
        """注册通信工具，并启动分发循环与每个 Agent 的收信 worker。"""
        if self._running:
            return
        self._running = True
        self._stop_event = asyncio.Event()
        for name, agent in self._agents.items():
            self._inboxes[name] = asyncio.Queue()
            self._register_communication_tool(name, agent)
            self._register_injection_handler(name, agent)
        self._tasks.append(asyncio.create_task(self._dispatch_loop()))
        for name in self._agents:
            self._tasks.append(asyncio.create_task(self._agent_worker(name)))

    async def stop(self) -> None:
        """停止分发循环与所有 Agent worker。"""
        self._running = False
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def run(self) -> None:
        """
        启动环境并持续运行，直到调用 stop() 或任务被取消。

        典型用法：
            asyncio.create_task(env.run())
            env.predict("开始工作")   # 或指定 main_agent
            ...
            await env.stop()
        """
        await self.start()
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()

    def predict(self, instruction: str, main_agent: str = None) -> Message:
        """
        投放一条外部指令（即发即忘）。

        Args:
            instruction: 指令内容。
            main_agent: 目标 Agent 名称；为 None 时广播给所有 Agent。
        """
        if main_agent is not None and main_agent not in self._agents:
            raise ValueError(f"未知的 Agent: {main_agent}")
        message = Message(
            sender=self.name,
            content=instruction,
            recipient=main_agent,
            role="user",
        )
        return self.bus.put(message)

    def history(self, limit: Optional[int] = None) -> list[Message]:
        """获取消息历史。"""
        return self.bus.history(limit=limit)

    def active_message(self, name: str) -> Optional[Message]:
        """该 Agent 正在处理（已出队、尚未处理完）的消息，空闲时为 None。"""
        return self._active_messages.get(name)

    def pending_messages(self, name: str) -> list[Message]:
        """
        该 Agent 当前待处理的消息，按先后顺序：
        正在处理的一条（若有）+ 收信队列中排队的消息。
        """
        result: list[Message] = []
        active = self._active_messages.get(name)
        if active is not None:
            result.append(active)
        inbox = self._inboxes.get(name)
        if inbox is not None:
            # asyncio.Queue 没有公开的窥视接口，_queue 是底层 deque（CPython 稳定）
            result.extend(list(inbox._queue))
        return result

    def pending_queues(self) -> dict[str, list[Message]]:
        """所有 Agent 的待处理消息，{名称: [消息, ...]}。"""
        return {name: self.pending_messages(name) for name in self._agents}

    def add_queue_listener(self, listener: Callable[[], None]) -> None:
        """注册队列变化监听器（同步回调）。"""
        self._queue_listeners.append(listener)

    def remove_queue_listener(self, listener: Callable[[], None]) -> None:
        """移除队列变化监听器。"""
        if listener in self._queue_listeners:
            self._queue_listeners.remove(listener)

    def _notify_queue_change(self) -> None:
        for listener in list(self._queue_listeners):
            try:
                listener()
            except Exception as error:
                logger.error(f"MultiAgentEnvironment - 队列监听回调失败: {error}")

    # --- 回合失败 / 后端状态 ---

    @property
    def backend_error(self) -> Optional[dict]:
        """最近一次「致命」后端错误的分类信息；正常时为 None。"""
        return self._backend_error

    def add_error_listener(self, listener: Callable) -> None:
        """注册回合失败监听器：listener(agent_name, error, info)。"""
        self._error_listeners.append(listener)

    def remove_error_listener(self, listener: Callable) -> None:
        """移除回合失败监听器。"""
        if listener in self._error_listeners:
            self._error_listeners.remove(listener)

    def add_backend_listener(self, listener: Callable) -> None:
        """注册后端状态变化监听器：listener(info_or_None)。

        仅在「进入致命错误」与「恢复」两个**状态切换点**触发，便于告警去重。
        """
        self._backend_listeners.append(listener)

    def remove_backend_listener(self, listener: Callable) -> None:
        """移除后端状态变化监听器。"""
        if listener in self._backend_listeners:
            self._backend_listeners.remove(listener)

    def _notify_backend(self, info: Optional[dict]) -> None:
        for listener in list(self._backend_listeners):
            try:
                listener(info)
            except Exception as cb_error:  # noqa: BLE001
                logger.error(
                    f"MultiAgentEnvironment - 后端状态监听回调失败: {cb_error}"
                )

    def _notify_turn_error(self, name: str, error: BaseException) -> dict:
        """一轮推理失败时调用：分类、更新后端状态、通知监听器。"""
        from tina.core.error import classify_api_error

        info = classify_api_error(error)
        info["agent"] = name
        was_fatal = self._backend_error is not None
        if info.get("fatal"):
            self._backend_error = info
            # 记到 agent 上，便于运行时（如自动压缩）据此跳过无谓的调用
            agent = self._agents.get(name)
            if agent is not None:
                setattr(agent, "_backend_error", info)
        for listener in list(self._error_listeners):
            try:
                listener(name, error, info)
            except Exception as cb_error:  # noqa: BLE001
                logger.error(
                    f"MultiAgentEnvironment - 回合错误监听回调失败: {cb_error}"
                )
        if info.get("fatal") and not was_fatal:
            self._notify_backend(info)
        return info

    def _clear_backend_error(self, name: str) -> None:
        """一轮推理成功时调用：清除后端致命错误状态。"""
        if self._backend_error is None:
            return
        self._backend_error = None
        for agent in self._agents.values():
            if getattr(agent, "_backend_error", None) is not None:
                setattr(agent, "_backend_error", None)
        logger.info("MultiAgentEnvironment - 后端已恢复，清除暂停标志")
        self._notify_backend(None)

    def _register_injection_handler(self, name: str, agent: "Agent") -> None:
        """
        给 Agent 挂上 before_llm_call 处理器：在每轮 LLM 调用前，把收信队列里
        新到的消息注入上下文。这样 Agent 正在输出、又来了消息时，消息会在
        下一个「非忙」边界（工具跑完、下一轮 LLM 之前）进入本次推理，而不必
        等整个回合结束。
        """
        if name in self._injection_registered:
            return
        self._injection_registered.add(name)
        agent.add_before_llm_call_handler(
            lambda: self._inject_pending_messages(name, agent)
        )

    def _inject_pending_messages(self, name: str, agent: "Agent") -> None:
        """把该 Agent 收信队列里此刻排队的消息全部注入上下文（不新起回合）。"""
        # Agent 正在做「上下文压缩」等敏感回合时，挂起注入，避免消息被压缩清掉
        if getattr(agent, "_suspend_inbox_injection", False):
            return
        inbox = self._inboxes.get(name)
        if inbox is None:
            return
        injected = False
        while True:
            try:
                message = inbox.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._inject_message(agent, message)
            injected = True
        if injected:
            self._notify_queue_change()

    @staticmethod
    def _inject_message(agent: "Agent", message: Message) -> None:
        """按来源把一条消息写进 Agent 上下文。"""
        if message.role == "user":
            agent.context_manager.add_user_message(message.content)
            return
        entry = {
            "role": "assistant",
            "name": message.sender,
            "content": message.content,
        }
        # 思考类模型（如 DeepSeek）要求 assistant 消息带 reasoning_content，
        # 注入的同伴消息并非模型生成，补空串兜底（由 enable_deepseek_reasoning_tools 标记）
        if getattr(agent, "_reasoning_required", False):
            entry["reasoning_content"] = ""
        agent.context_manager.add_messages([entry])

    def _register_communication_tool(self, name: str, agent: "Agent") -> None:
        targets = [other for other in self._agents if other != name]
        if targets:
            description = (
                "向其他 Agent 发送消息；不指定 recipient 时广播给所有其他 Agent。"
                "可用的 Agent: " + "、".join(targets)
            )
        else:
            description = (
                "向其他 Agent 发送消息；不指定 recipient 时广播给所有其他 Agent。"
                "当前环境中没有其他 Agent。"
            )

        def send_message(content: str, recipient: str = None) -> str:
            """
            向其他 Agent 发送一条消息；不指定 recipient 时广播
            Args:
                content (str): 消息内容
                recipient (str): 接收方 Agent 名称，不指定则广播给所有其他 Agent
            """
            if recipient is not None and recipient not in self._agents:
                return f"发送失败：不存在名为 {recipient} 的 Agent"
            self.bus.put(
                Message(
                    sender=name,
                    content=content,
                    recipient=recipient,
                    role="assistant",
                )
            )
            if recipient is None:
                return "已广播消息"
            return f"已向 {recipient} 发送消息"

        agent.tools.register_tool(tool=send_message, description=description)

    async def _dispatch_loop(self) -> None:
        while True:
            message = await self.bus.get()
            if message.recipient is not None:
                targets = [message.recipient]
            else:
                targets = [name for name in self._agents if name != message.sender]
            for target in targets:
                inbox = self._inboxes.get(target)
                if inbox is not None:
                    inbox.put_nowait(message)
            if targets:
                self._notify_queue_change()

    def interrupt(self, name: str) -> bool:
        """打断某个 Agent 当前正在进行的输出；返回是否有进行中的输出被取消。"""
        turn = self._turns.get(name)
        if turn is None or turn.done() or name in self._interrupted:
            return False
        self._interrupted.add(name)
        turn.cancel()
        return True

    def interrupt_all(self) -> int:
        """打断所有 Agent 当前正在进行的输出，返回被打断的数量。"""
        return sum(1 for name in list(self._turns) if self.interrupt(name))

    async def _agent_worker(self, name: str) -> None:
        agent = self._agents[name]
        inbox = self._inboxes[name]
        while True:
            message = await inbox.get()
            self._active_messages[name] = message
            self._notify_queue_change()
            try:
                while agent.state in _BUSY_STATES:
                    await asyncio.sleep(0.05)
                self._inject_message(agent, message)
                await self._run_agent_turn(name, agent)
                self._clear_backend_error(name)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # 有些底层异常（如 anyio Closed/BrokenResourceError）str() 为空，
                # 只打印 {error} 会变成「处理消息失败: 」这种看不出原因的日志，
                # 这里补上类型与堆栈。
                import traceback

                logger.error(
                    f"MultiAgentEnvironment - Agent {name} 处理消息失败: "
                    f"{type(error).__name__}: {error!r}\n{traceback.format_exc()}"
                )
                # 分类并通知观测层（Web 面板 / 飞书告警），让失败「看得见」
                self._notify_turn_error(name, error)
            finally:
                self._active_messages.pop(name, None)
                self._notify_queue_change()

    async def _run_agent_turn(self, name: str, agent: "Agent") -> None:
        self._interrupted.discard(name)
        turn = asyncio.create_task(self._consume_prediction(name, agent))
        self._turns[name] = turn
        try:
            await turn
        except asyncio.CancelledError:
            # 环境停止时直接向上传播；用户打断则走收尾流程
            if self._stop_event.is_set():
                raise
            await self._finalize_interrupt(name, agent)
        finally:
            self._turns.pop(name, None)
            self._partials.pop(name, None)
            self._interrupted.discard(name)

    async def _consume_prediction(self, name: str, agent: "Agent") -> None:
        """消费一次推理流，并持续记录「尚未写入上下文」的部分正文。"""
        current: list[str] = []
        async for chunk in agent.apredict(instruction=None):
            role = chunk.get("role")
            if chunk.get("tool_calls") or role == "tool":
                # 工具边界：上一段正文已由 runtime 提交，重新累积
                current = []
            elif role == "assistant" and chunk.get("content"):
                current.append(chunk["content"])
            self._partials[name] = "".join(current)

    async def _finalize_interrupt(self, name: str, agent: "Agent") -> None:
        """打断收尾：补被打断的工具结果、写回部分正文、触发 on_turn_end、状态复位。"""
        try:
            self._mark_interrupted_tool_results(agent.context_manager)
        except Exception:
            pass
        partial = self._partials.get(name, "")
        if partial.strip():
            try:
                agent.context_manager.add_assistant_message(partial)
            except Exception:
                pass
        try:
            await agent.events.atrigger_on_turn_end()
        except Exception:
            pass
        try:
            from tina.agent.core.state import AgentState

            agent.runtime.state = AgentState.IDLE
        except Exception:
            pass

    @staticmethod
    def _mark_interrupted_tool_results(context_manager) -> None:
        """把已发出但还没有结果的 tool_call 补上「该次调用被打断」。"""
        messages = context_manager.get_messages()
        last_index = None
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.get("role") == "assistant" and message.get("tool_calls"):
                last_index = index
                break
        if last_index is None:
            return
        answered = {
            message.get("tool_call_id")
            for message in messages[last_index + 1 :]
            if message.get("role") == "tool"
        }
        for call in messages[last_index].get("tool_calls") or []:
            call_id = call.get("id") or call.get("tool_call_id")
            if not call_id or call_id in answered:
                continue
            context_manager.add_tool_call_result("该次调用被打断", call_id, call)
