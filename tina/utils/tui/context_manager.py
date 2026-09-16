"""TUI 消息 / 渲染上下文

维护供终端界面渲染的会话块（用户输入、助手文本、推理链、工具卡片、错误），
并把 Agent 流式输出的 `AgentResponse` 分片聚合成可读的渲染块。

本模块不依赖 textual，纯数据层，方便界面组件订阅与刷新。
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, AsyncIterator, Callable, Iterator

from ...agent.core.context_manager import _content_length
from ...core import logger


class TuiBlock(dict):
    """TUI 渲染块，继承自 dict，提供只读属性访问"""

    @property
    def id(self) -> int:
        """块的自增编号"""
        return self.get("id")

    @property
    def role(self) -> str:
        """块类型：system / user / assistant / reasoning / tool / error"""
        return self.get("role", "")

    @property
    def content(self) -> str:
        """块的文本内容（工具块为截断后的执行结果）"""
        return self.get("content", "") or ""

    @property
    def title(self) -> str:
        """可折叠结果块的标题"""
        return self.get("title", "") or ""

    @property
    def status(self) -> str:
        """块状态：streaming / building / calling / done / error"""
        return self.get("status", "")

    @property
    def tool_name(self) -> str | None:
        return self.get("tool_name")

    @property
    def tool_arguments(self) -> Any:
        """工具参数：构建中为原始字符串，完整后尽量解析为 dict"""
        return self.get("tool_arguments", "")

    @property
    def tool_calls(self) -> list[dict[str, Any]] | None:
        return self.get("tool_calls")

    @property
    def tool_result(self) -> str | None:
        """工具完整执行结果（不截断）"""
        return self.get("tool_result")

    @property
    def usage(self) -> dict[str, Any] | None:
        return self.get("usage")

    @property
    def metadata(self) -> dict[str, Any]:
        return self.get("metadata", {})

    @property
    def is_streaming(self) -> bool:
        """块是否仍在进行中（需要界面持续刷新）"""
        return self.get("status") in ("streaming", "building", "calling")


class TuiContextManager:
    """TUI 消息 / 渲染上下文管理器

    用法：
        tui = TuiContextManager()
        tui.subscribe(lambda event, block: app.refresh())

        tui.add_user("你好")
        for chunk in agent.predict(instruction="你好"):
            tui.handle_chunk(chunk)
        tui.finish_turn()
    """

    blocks: list[TuiBlock]

    def __init__(
        self, max_length: int = 100000, max_tool_result_length: int = 6000
    ) -> None:
        self.max_length = max_length
        self.max_tool_result_length = max_tool_result_length
        self.blocks = []
        self._next_id = 0
        self._listeners: list[Callable[[str, TuiBlock | None], None]] = []
        self._current_assistant: TuiBlock | None = None
        self._current_reasoning: TuiBlock | None = None
        self._active_tools: dict[str, list[TuiBlock]] = {}

    # ------------------------------------------------------------------ 订阅

    def subscribe(
        self, callback: Callable[[str, TuiBlock | None], None]
    ) -> Callable[[str, TuiBlock | None], None]:
        """注册监听器，回调签名为 (event, block)，event 为 add/update/chunk/clear"""
        self._listeners.append(callback)
        return callback

    def unsubscribe(self, callback: Callable[[str, TuiBlock | None], None]) -> None:
        """移除监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, event: str, block: TuiBlock | None = None) -> None:
        for callback in list(self._listeners):
            try:
                callback(event, block)
            except Exception as e:  # 监听器异常不应中断 Agent 流
                logger.error(f"TuiContextManager - 监听器执行失败: {e}")

    # ------------------------------------------------------------------ 查询

    def get_blocks(self) -> list[TuiBlock]:
        """返回渲染块列表（实时引用）"""
        return self.blocks

    def get_blocks_by_role(self, role: str) -> list[TuiBlock]:
        """按类型筛选渲染块"""
        return [block for block in self.blocks if block["role"] == role]

    def get_last_block(self) -> TuiBlock | None:
        """返回最后一个渲染块"""
        return self.blocks[-1] if self.blocks else None

    def snapshot(self) -> list[dict[str, Any]]:
        """返回渲染块的深拷贝快照，供界面安全遍历"""
        return [deepcopy(block) for block in self.blocks]

    def __len__(self) -> int:
        return len(self.blocks)

    def __iter__(self) -> Iterator[TuiBlock]:
        return iter(self.blocks)

    # ------------------------------------------------------------------ 写入

    def add_system(self, content: str, **metadata: Any) -> TuiBlock:
        """追加系统提示块"""
        return self._new_block("system", content=content, metadata=metadata)

    def add_user(self, content: str, **metadata: Any) -> TuiBlock:
        """追加用户输入块，并结算上一轮仍在进行的流式块"""
        self._close_streaming()
        return self._new_block("user", content=content, metadata=metadata)

    def add_error(self, message: Any, **metadata: Any) -> TuiBlock:
        """追加错误块"""
        self._close_streaming()
        return self._new_block(
            "error", content=str(message), status="error", metadata=metadata
        )

    def add_result(
        self, title: str, content: str, collapsed: bool = False, **metadata: Any
    ) -> TuiBlock:
        """追加可折叠的结果块（用于命令输出）"""
        self._close_streaming()
        meta = dict(metadata)
        meta["collapsed"] = collapsed
        return self._new_block(
            "result", content=content, title=title, metadata=meta
        )

    def clear(self, keep_system: bool = False) -> None:
        """清空渲染上下文，可选保留系统提示块"""
        if keep_system:
            self.blocks = [block for block in self.blocks if block["role"] == "system"]
        else:
            self.blocks = []
        self._current_assistant = None
        self._current_reasoning = None
        self._active_tools.clear()
        self._notify("clear", None)

    # ------------------------------------------------------------------ 流式处理

    def handle_chunk(self, chunk: dict[str, Any]) -> TuiBlock | None:
        """消费一个 AgentResponse 分片，返回受影响（或新建）的渲染块"""
        role = chunk.get("role", "")

        if role == "tool":
            block = self._handle_tool_result(chunk)
        elif "tool_name" in chunk or "tool_arguments" in chunk:
            block = self._handle_tool_chunk(chunk)
        elif chunk.get("tool_calls"):
            block = self._handle_tool_calls(chunk)
        elif "reasoning_content" in chunk:
            block = self._handle_reasoning(chunk)
        else:
            block = self._handle_content(chunk)

        self._notify("chunk", block)
        return block

    def feed(self, chunk: dict[str, Any]) -> TuiBlock | None:
        """handle_chunk 的别名"""
        return self.handle_chunk(chunk)

    def consume(self, chunks: Iterator[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """同步消费分片流：逐个写入上下文并原样产出"""
        for chunk in chunks:
            self.handle_chunk(chunk)
            yield chunk

    async def aconsume(
        self, chunks: AsyncIterator[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        """异步消费分片流：逐个写入上下文并原样产出"""
        async for chunk in chunks:
            self.handle_chunk(chunk)
            yield chunk

    def finish_turn(self) -> None:
        """结束一轮推理：结算未完成的流式块与工具卡片"""
        self._close_streaming()
        for name, blocks in list(self._active_tools.items()):
            for block in blocks:
                if block["status"] != "done":
                    block["status"] = "done"
                    self._notify("update", block)
        self._active_tools.clear()

    # ------------------------------------------------------------------ 内部实现

    def _new_block(
        self, role: str, status: str = "done", **fields: Any
    ) -> TuiBlock:
        block = TuiBlock(
            id=self._next_id,
            role=role,
            content="",
            title="",
            status=status,
            tool_name=None,
            tool_arguments="",
            tool_calls=None,
            tool_result=None,
            usage=None,
            metadata={},
        )
        block.update(fields)
        self._next_id += 1
        self.blocks.append(block)
        self._trim()
        self._notify("add", block)
        return block

    def _handle_content(self, chunk: dict[str, Any]) -> TuiBlock:
        text = chunk.get("content", "") or ""
        usage = chunk.get("usage")

        if self._current_reasoning is not None:
            self._close_reasoning()

        if self._current_assistant is None:
            self._current_assistant = self._new_block("assistant", status="streaming")
        self._current_assistant["status"] = "streaming"
        if text:
            self._current_assistant["content"] += text
        if usage is not None:
            self._current_assistant["usage"] = usage
        self._notify("update", self._current_assistant)
        return self._current_assistant

    def _handle_reasoning(self, chunk: dict[str, Any]) -> TuiBlock:
        text = chunk.get("reasoning_content", "") or ""

        if self._current_assistant is not None:
            self._close_assistant()

        if self._current_reasoning is None:
            self._current_reasoning = self._new_block("reasoning", status="streaming")
        self._current_reasoning["status"] = "streaming"
        self._current_reasoning["content"] += text
        self._notify("update", self._current_reasoning)
        return self._current_reasoning

    def _handle_tool_chunk(self, chunk: dict[str, Any]) -> TuiBlock:
        name = chunk.get("tool_name")
        arguments = chunk.get("tool_arguments")

        block = self._find_tool(name) if name else None
        if block is None:
            block = self._start_tool(name or "unknown")

        if arguments:
            if not isinstance(block["tool_arguments"], str):
                block["tool_arguments"] = str(block["tool_arguments"])
            raw = arguments if isinstance(arguments, str) else str(arguments)
            block["tool_arguments"] += raw
            self._notify("update", block)
        return block

    def _handle_tool_calls(self, chunk: dict[str, Any]) -> TuiBlock | None:
        last: TuiBlock | None = None
        for call in chunk.get("tool_calls") or []:
            name = (call.get("function") or {}).get("name")
            block = self._find_tool(name) if name else None
            if block is None:
                block = self._start_tool(name or "unknown")
            block["tool_calls"] = [call]
            block["status"] = "calling"
            block["tool_arguments"] = self._parse_arguments(block["tool_arguments"])
            last = block
            self._notify("update", block)
        return last

    def _handle_tool_result(self, chunk: dict[str, Any]) -> TuiBlock:
        name = chunk.get("tool_name")
        result = chunk.get("content", "") or ""

        block = self._find_tool(name) if name else None
        if block is None:
            block = self._new_block(
                "tool",
                status="calling",
                tool_name=name,
                tool_calls=chunk.get("tool_calls"),
            )

        block["tool_result"] = result
        block["content"] = self._truncate(result)
        block["status"] = "done"
        self._release_tool(name, block)
        self._notify("update", block)
        return block

    def _start_tool(self, name: str) -> TuiBlock:
        self._close_streaming()
        block = self._new_block("tool", status="building", tool_name=name)
        self._active_tools.setdefault(name, []).append(block)
        return block

    def _find_tool(self, name: str) -> TuiBlock | None:
        for block in self._active_tools.get(name, []):
            if block["status"] in ("building", "calling"):
                return block
        return None

    def _release_tool(self, name: str | None, block: TuiBlock) -> None:
        if not name or name not in self._active_tools:
            return
        active = self._active_tools[name]
        if block in active:
            active.remove(block)
        if not active:
            del self._active_tools[name]

    def _close_assistant(self) -> None:
        if self._current_assistant is not None:
            if self._current_assistant["status"] == "streaming":
                self._current_assistant["status"] = "done"
                self._notify("update", self._current_assistant)
            self._current_assistant = None

    def _close_reasoning(self) -> None:
        if self._current_reasoning is not None:
            if self._current_reasoning["status"] == "streaming":
                self._current_reasoning["status"] = "done"
                self._notify("update", self._current_reasoning)
            self._current_reasoning = None

    def _close_streaming(self) -> None:
        self._close_reasoning()
        self._close_assistant()

    def _parse_arguments(self, arguments: Any) -> Any:
        if not isinstance(arguments, str) or not arguments:
            return arguments
        try:
            return json.loads(arguments)
        except (ValueError, TypeError):
            return arguments

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_tool_result_length:
            return text[: self.max_tool_result_length - 3] + "..."
        return text

    def _active_blocks(self) -> set[int]:
        active = set()
        for block in (self._current_assistant, self._current_reasoning):
            if block is not None:
                active.add(id(block))
        for blocks in self._active_tools.values():
            for block in blocks:
                active.add(id(block))
        return active

    def _trim(self) -> None:
        """超过 max_length 时从最旧的块开始裁剪，保留 system、进行中的块与最新块"""
        if self.max_length <= 0:
            return
        total = sum(_content_length(block.get("content")) for block in self.blocks)
        active = self._active_blocks()
        i = 0
        while total > self.max_length and i < len(self.blocks) - 1:
            block = self.blocks[i]
            if block["role"] == "system" or id(block) in active:
                i += 1
                continue
            total -= _content_length(block.get("content"))
            self.blocks.pop(i)
