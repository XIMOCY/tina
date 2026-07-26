"""
AgentWorker：将 Agent 部署为后台工作器的工具类
支持通过 asyncio.Queue 接收外部指令，在异步循环中持续处理。

用法示例：
    worker = AgentWorker(agent=my_agent, max_queue_size=20)

    # 添加多个流式处理器
    worker.add_stream_chunk_handler(my_handler)

    # 在其他协程中向工作器推送指令
    await worker.put("你好，请帮我做一件事")

    # 启动工作器
    asyncio.create_task(worker.run())
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..agent.agent import Agent


class AgentWorker:
    """
    将 Agent 包装为异步后台工作器，通过 asyncio.Queue 驱动执行。

    Attributes:
        agent: 内部持有的 Agent 实例
        max_queue_size: 消息队列的最大长度
        _message_queue: asyncio.Queue，用于接收外部指令
        _stream_chunk_handlers: 流式 chunk 处理器列表
    """

    def __init__(
        self,
        agent: "Agent",
        max_queue_size: int = 10,
    ):
        """
        初始化 AgentWorker。

        Args:
            agent: Agent 实例
            max_queue_size: 消息队列的最大长度
        """
        self.agent = agent
        self.max_queue_size = max_queue_size
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._stream_chunk_handlers: list[Callable] = []

        # 将 put 注册为 Agent 工具，方便其他 Agent 调用
        self.agent.tools.register_tool(tool=self.put)

    async def put(self, instruction: str) -> None:
        """
        向工作器的消息队列中推送一条指令。

        Args:
            instruction: 文本指令
        """
        await self._message_queue.put(item=instruction)

    async def run(self) -> None:
        """
        启动工作器的主循环。
        持续从队列中获取指令并交给 Agent 处理，遇到错误不会导致整个循环退出。
        """
        while True:
            instruction = await self._message_queue.get()
            try:
                async for _ in self.agent.apredict(instruction=instruction):
                    continue
            except Exception as e:
                print(f"AgentWorker - 执行指令出错: {e}")
            finally:
                self._message_queue.task_done()

    def add_stream_chunk_handler(self, handler: Callable) -> None:
        """
        添加一个流式 chunk 处理器。
        支持多次调用以添加多个处理器。

        Args:
            handler: 可调用对象，接受一个 chunk（dict 或 AgentResponse）参数
        """
        self._stream_chunk_handlers.append(handler)
        self.agent.add_on_stream_chunk_handler(handler)

    def add_stream_chunk_handlers(self, handlers: list[Callable]) -> None:
        """
        批量添加多个流式 chunk 处理器。

        Args:
            handlers: 可调用对象列表
        """
        for handler in handlers:
            self.add_stream_chunk_handler(handler)

    def get_queue_size(self) -> int:
        """
        获取当前队列中待处理的消息数量。

        Returns:
            int: 队列中的消息数量
        """
        return self._message_queue.qsize()

    def clear_queue(self) -> None:
        """
        清空队列中的所有消息。
        """
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
                self._message_queue.task_done()
            except asyncio.QueueEmpty:
                break