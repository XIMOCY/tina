"""TUI 渲染数据层

维护供终端界面渲染的会话块（用户输入、助手文本、推理链、工具卡片、错误），
并把 Agent 流式输出的 `AgentResponse` 分片聚合成可读的渲染块。

注意：`TuiMessageStore` 只管界面显示，**不是送给大模型的上下文**；模型历史
由 `agent.context_manager` 管理。本模块另提供无长度限制的模型上下文管理器
（`UnlimitedContextManager` 等）供 TUI 用户选用。

本模块不依赖 textual，纯数据层，方便界面组件订阅与刷新。
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Iterator

from ...agent.core.context_manager import (
    ContextManager,
    MultimodalContextManager,
    _content_length,
)
from ...core import logger

if TYPE_CHECKING:
    from ...agent import Agent, MultimodalAgent, Tools


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

    def _joined(self, field: str) -> Any:
        """字段值 + 尚未合并的流式片段（保证读取时总是最新）"""
        base = self.get(field)
        if base is None:
            base = ""
        slots = self.get("_pending")
        if slots:
            parts = slots.get(field)
            if parts:
                return base + "".join(parts) if isinstance(base, str) else base
        return base

    @property
    def content(self) -> str:
        """块的文本内容（工具块为截断后的执行结果）"""
        return self._joined("content")

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
        return self._joined("tool_arguments")

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


class TuiMessageStore:
    """TUI 消息渲染仓库

    把流式分片聚合成界面渲染块（`TuiBlock`），只管显示，不是模型上下文。

    用法：
        store = TuiMessageStore()
        store.subscribe(lambda event, block: app.refresh())

        store.add_user("你好")
        for chunk in agent.predict(instruction="你好"):
            store.handle_chunk(chunk)
        store.finish_turn()
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
        # 并发工具调用的归属：按流式 index 与最终 tool_call_id 定位卡片
        self._tool_by_index: dict[int, TuiBlock] = {}
        self._tool_by_id: dict[str, TuiBlock] = {}
        self._by_id: dict[int, TuiBlock] = {}
        # 有流式片段待合并的块编号（片段存在各个块的 _pending 字段里）
        self._pending_ids: set[int] = set()

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
                logger.error(f"TuiMessageStore - 监听器执行失败: {e}")

    # ------------------------------------------------------------------ 查询

    def get_blocks(self) -> list[TuiBlock]:
        """返回渲染块列表（实时引用）"""
        return self.blocks

    def get_block(self, block_id: int) -> TuiBlock | None:
        """按编号返回渲染块"""
        return self._by_id.get(block_id)

    def commit(self) -> None:
        """把缓存的流式文本片段合并进各块字段（渲染前调用）"""
        for block_id in list(self._pending_ids):
            block = self._by_id.get(block_id)
            if block is None:
                self._pending_ids.discard(block_id)
                continue
            self._commit_block(block)

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
        self._by_id = {block["id"]: block for block in self.blocks}
        self._pending_ids = {b["id"] for b in self.blocks if b.get("_pending")}
        self._current_assistant = None
        self._current_reasoning = None
        self._active_tools.clear()
        self._tool_by_index.clear()
        self._tool_by_id.clear()
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
        self._tool_by_index.clear()
        self._tool_by_id.clear()

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
        self._by_id[block["id"]] = block
        self._trim()
        self._notify("add", block)
        return block

    def _append_field(self, block: TuiBlock, field: str, text: str) -> None:
        """缓存一段流式文本：逐 chunk 只做 list.append，避免字符串 O(n²) 拼接"""
        if not text:
            return
        slots = block.setdefault("_pending", {})
        slots.setdefault(field, []).append(text)
        self._pending_ids.add(block["id"])

    def _commit_block(self, block: TuiBlock) -> None:
        """把某个块缓存的片段合并进字段"""
        slots = block.get("_pending")
        if not slots:
            self._pending_ids.discard(block["id"])
            return
        for field, parts in slots.items():
            base = block.get(field)
            block[field] = (base if isinstance(base, str) else "") + "".join(parts)
        block["_pending"] = {}
        self._pending_ids.discard(block["id"])

    def _block_length(self, block: TuiBlock) -> int:
        """块的内容长度（含尚未 commit 的片段）"""
        length = _content_length(block.get("content"))
        for parts in (block.get("_pending") or {}).values():
            length += sum(len(part) for part in parts)
        return length

    def _forget(self, block: TuiBlock) -> None:
        self._by_id.pop(block["id"], None)
        self._pending_ids.discard(block["id"])

    def _handle_content(self, chunk: dict[str, Any]) -> TuiBlock:
        text = chunk.get("content", "") or ""
        usage = chunk.get("usage")

        if self._current_reasoning is not None:
            self._close_reasoning()

        if self._current_assistant is None:
            self._current_assistant = self._new_block("assistant", status="streaming")
        self._current_assistant["status"] = "streaming"
        self._append_field(self._current_assistant, "content", text)
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
        self._append_field(self._current_reasoning, "content", text)
        self._notify("update", self._current_reasoning)
        return self._current_reasoning

    def _handle_tool_chunk(self, chunk: dict[str, Any]) -> TuiBlock:
        name = chunk.get("tool_name")
        arguments = chunk.get("tool_arguments")
        index = chunk.get("tool_index")

        if index is not None:
            # 并发调用：按 index 定位，绝不按名字串到别的调用上
            block = self._tool_by_index.get(index)
            if block is None:
                block = self._start_tool(name or "unknown", index=index)
        else:
            block = self._find_tool(name) if name else None
            if block is None:
                block = self._start_tool(name or "unknown")

        if arguments:
            self._commit_block(block)
            if not isinstance(block["tool_arguments"], str):
                block["tool_arguments"] = str(block["tool_arguments"] or "")
            raw = arguments if isinstance(arguments, str) else str(arguments)
            self._append_field(block, "tool_arguments", raw)
            self._notify("update", block)
        return block

    def _handle_tool_calls(self, chunk: dict[str, Any]) -> TuiBlock | None:
        last: TuiBlock | None = None
        for call in chunk.get("tool_calls") or []:
            name = (call.get("function") or {}).get("name")
            index = call.get("index")
            call_id = call.get("id")

            block = self._tool_by_index.get(index) if index is not None else None
            if block is None and call_id:
                block = self._tool_by_id.get(call_id)
            if block is None and name:
                block = self._find_tool(name)
            if block is None:
                block = self._start_tool(
                    name or "unknown", index=index, tool_id=call_id
                )
            else:
                if index is not None:
                    self._tool_by_index[index] = block
                if call_id:
                    self._tool_by_id[call_id] = block

            block["tool_calls"] = [call]
            block["status"] = "calling"
            self._commit_block(block)
            block["tool_arguments"] = self._parse_arguments(block["tool_arguments"])
            last = block
            self._notify("update", block)
        return last

    def _handle_tool_result(self, chunk: dict[str, Any]) -> TuiBlock:
        name = chunk.get("tool_name")
        result = chunk.get("content", "") or ""
        call_id = chunk.get("tool_call_id")

        block = self._tool_by_id.get(call_id) if call_id else None
        if block is None:
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

    def _start_tool(
        self, name: str, index: int | None = None, tool_id: str | None = None
    ) -> TuiBlock:
        self._close_streaming()
        block = self._new_block("tool", status="building", tool_name=name)
        self._active_tools.setdefault(name, []).append(block)
        if index is not None:
            self._tool_by_index[index] = block
        if tool_id:
            self._tool_by_id[tool_id] = block
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
        total = sum(self._block_length(block) for block in self.blocks)
        active = self._active_blocks()
        i = 0
        while total > self.max_length and i < len(self.blocks) - 1:
            block = self.blocks[i]
            if block["role"] == "system" or id(block) in active:
                i += 1
                continue
            total -= self._block_length(block)
            self.blocks.pop(i)
            self._forget(block)


# ---------------------------------------------------------------- 无限制上下文管理器


class UnlimitedContextManager(ContextManager):
    """不做任何长度限制的上下文管理器

    - 不裁剪历史消息（`limit_messages` 只补齐 content 字段）
    - 不截断工具结果

    适合在 TUI / 本地调试里保留完整对话与工具输出。注意上下文会持续增长，
    需要自己确认模型窗口足够大。
    """

    NO_LIMIT = 2**62

    def __init__(self) -> None:
        super().__init__(max_length=0, max_tool_result_length=self.NO_LIMIT)

    def limit_messages(self) -> None:
        for message in self.messages:
            if message.get("content") is None:
                message["content"] = ""


class UnlimitedMultimodalContextManager(MultimodalContextManager):
    """多模态版的无限制上下文管理器，行为同 `UnlimitedContextManager`"""

    NO_LIMIT = 2**62

    def __init__(self, tools: Tools | None = None) -> None:
        super().__init__(tools, max_length=0, max_tool_result_length=self.NO_LIMIT)

    def limit_messages(self) -> None:
        for message in self.messages:
            if message.get("content") is None:
                message["content"] = ""


def make_unlimited_context_manager(
    agent: Agent | MultimodalAgent,
) -> ContextManager:
    """按 Agent 现有上下文管理器的类型，构造一个无限制版本并接管现有历史"""
    current = agent.context_manager
    if isinstance(current, MultimodalContextManager):
        manager: ContextManager = UnlimitedMultimodalContextManager(current.tools)
    else:
        manager = UnlimitedContextManager()

    manager.set_messages(current.get_messages())
    manager.tool_calls = list(current.tool_calls)
    manager.tool_calls_result = list(current.tool_calls_result)
    return manager
