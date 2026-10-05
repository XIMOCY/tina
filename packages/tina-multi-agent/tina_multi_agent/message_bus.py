from __future__ import annotations

import asyncio
from typing import Callable, Optional

from .message import Message


class MessageBus:
    """
    消息总线：一个队列，负责分发与记录。

    所有进入总线的消息都会写入历史池（history），
    同时按入队顺序等待被环境的分发循环取出。
    可通过 add_listener 注册同步监听器，在消息入队的瞬间被回调。
    """

    def __init__(self):
        self._queue: "asyncio.Queue[Message]" = asyncio.Queue()
        self._history: list[Message] = []
        self._listeners: list[Callable[[Message], None]] = []

    def put(self, message: Message) -> Message:
        """记录、投递并通知监听器，返回该消息。"""
        self._history.append(message)
        self._queue.put_nowait(message)
        for listener in list(self._listeners):
            listener(message)
        return message

    async def get(self) -> Message:
        """取出下一条待分发的消息。"""
        return await self._queue.get()

    def add_listener(self, listener: Callable[[Message], None]) -> None:
        """注册一个消息入队监听器（同步回调）。"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Message], None]) -> None:
        """移除一个消息入队监听器。"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def history(self, limit: Optional[int] = None) -> list[Message]:
        """获取历史消息，limit 指定时只返回最近的若干条。"""
        if limit is None:
            return list(self._history)
        return list(self._history[-limit:])

    def clear_history(self) -> None:
        """清空历史池。"""
        self._history.clear()

    def load_history(self, messages: list[Message]) -> None:
        """恢复历史记录：仅替换历史池，不入队、不通知监听器。"""
        self._history = list(messages)
