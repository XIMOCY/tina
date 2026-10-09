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
import re
import time
from copy import deepcopy
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Iterator

from tina.agent.core.context_manager import (
    ContextManager,
    MultimodalContextManager,
    _content_length,
)
from tina.core import logger

if TYPE_CHECKING:
    from tina.agent import Agent, MultimodalAgent, Tools


# 会话持久化时要保留的渲染块字段（含耗时/timing/usage，恢复后视图与实时一致）
_SNAPSHOT_FIELDS = (
    "role",
    "content",
    "title",
    "status",
    "tool_name",
    "tool_arguments",
    "tool_calls",
    "tool_result",
    "usage",
    "timing",
    "duration",
    "metadata",
)


def _code_fence(text: str, lang: str = "") -> str:
    """用足够长的围栏包裹文本，避免内容里的反引号破坏代码块"""
    runs = [len(match) for match in re.findall(r"`+", text)]
    fence = "`" * max(3, (max(runs) + 1) if runs else 3)
    return f"{fence}{lang}\n{text}\n{fence}"


def _content_text(content: Any) -> str:
    """把消息 content 归一成文本（多模态 content 只取文本部分）"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif item.get("type") == "image_url":
                    parts.append("[图片]")
        return "\n".join(parts)
    return str(content)


def _pretty_arguments(arguments: Any) -> str:
    """把工具参数（dict / JSON 字符串 / 原始字符串）整理成可读文本"""
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if stripped[:1] in ("{", "["):
            try:
                arguments = json.loads(stripped)
            except (ValueError, TypeError):
                return arguments
        else:
            return arguments
    if isinstance(arguments, (dict, list)):
        try:
            return json.dumps(arguments, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(arguments)
    return str(arguments)


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
    def timing(self) -> dict[str, Any] | None:
        """LLM 计时（流式收尾块的 timing）"""
        return self.get("timing")

    @property
    def duration(self) -> float | None:
        """工具执行耗时（秒）"""
        return self.get("duration")

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
        self, max_length: int = 0, max_tool_result_length: int = 6000
    ) -> None:
        # max_length<=0 表示不裁剪（默认）：界面靠「窗口化渲染」控制挂载量，
        # 仓库保留全部块，避免旧消息被静默丢弃（那会同时留下孤儿 widget）。
        self.max_length = max_length
        self.max_tool_result_length = max_tool_result_length
        self.blocks = []
        self._next_id = 0
        self._listeners: list[Callable[[str, TuiBlock | None], None]] = []
        self._current_assistant: TuiBlock | None = None
        self._current_reasoning: TuiBlock | None = None
        # 本轮（一次 LLM 请求）最近一个思考块，用于把收尾 timing 的
        # thinking_duration 归到对应的「思考」块上
        self._round_reasoning: TuiBlock | None = None
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

    # ------------------------------------------------------------------ 导出

    def to_markdown(self, include_system: bool = True) -> str:
        """把整段会话导出为 Markdown 文本（严格按块出现的先后顺序）

        - 用户 / 助手各自成节，带小标题，一眼能分清
        - 思考过程用 <details> 折叠，不喧宾夺主
        - 工具调用含名称、参数、返回
        - 系统提示、错误、命令结果一并保留

        Args:
            include_system: 是否包含系统提示块（默认包含）
        """
        self.commit()
        lines = [
            "# tina 会话导出",
            "",
            f"> 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"> 消息块：{len(self.blocks)}",
        ]
        for block in self.blocks:
            section = self._block_to_markdown(block, include_system=include_system)
            if not section:
                continue
            lines += ["", "---", "", section]
        return "\n".join(lines).rstrip() + "\n"

    def _block_to_markdown(self, block: TuiBlock, include_system: bool = True) -> str:
        role = block.role
        if role == "system":
            return self._text_section("⚙️ 系统提示", block.content) if include_system else ""
        if role == "user":
            return self._text_section("🧑 用户", block.content)
        if role == "assistant":
            return self._assistant_section(block)
        if role == "reasoning":
            return self._reasoning_section(block)
        if role == "tool":
            return self._tool_section(block)
        if role == "error":
            return self._text_section("⚠️ 错误", block.content)
        if role == "result":
            return self._text_section(f"📋 {block.title or '命令结果'}", block.content)
        return self._text_section(role or "未知", block.content)

    @staticmethod
    def _text_section(title: str, content: str) -> str:
        content = (content or "").strip("\n")
        if not content.strip():
            return ""
        return f"## {title}\n\n{content}"

    def _assistant_section(self, block: TuiBlock) -> str:
        content = (block.content or "").strip("\n")
        meta = self._block_meta(block)
        if not content.strip() and not meta:
            return ""
        body = f"## 🤖 助手\n\n{content}".rstrip()
        if meta:
            body += f"\n\n<sub>{meta}</sub>"
        return body

    def _reasoning_section(self, block: TuiBlock) -> str:
        content = (block.content or "").strip("\n")
        if not content.strip():
            return ""
        meta = self._block_meta(block)
        summary = "💭 思考过程" + (f"（{meta}）" if meta else "")
        return (
            "<details>\n"
            f"<summary>{summary}</summary>\n\n"
            f"{content}\n\n"
            "</details>"
        )

    def _tool_section(self, block: TuiBlock) -> str:
        name = block.tool_name or "unknown"
        lines = [f"## 🔧 工具调用：{name}", ""]

        arguments = block.tool_arguments
        if arguments in (None, "", {}, []):
            arguments = block.tool_calls
        if arguments not in (None, "", {}, []):
            pretty = _pretty_arguments(arguments)
            lang = "json" if pretty.lstrip()[:1] in ("{", "[") else ""
            lines += ["**参数**", "", _code_fence(pretty, lang), ""]

        result = block.tool_result if block.tool_result is not None else block.content
        if result:
            lines += ["**返回**", "", _code_fence(str(result)), ""]

        if block.duration is not None:
            lines.append(f"<sub>耗时 {block.duration}s</sub>")

        return "\n".join(lines).rstrip()

    @staticmethod
    def _block_meta(block: TuiBlock) -> str:
        parts: list[str] = []
        timing = block.timing
        if timing:
            if timing.get("duration") is not None:
                parts.append(f"耗时 {timing['duration']}s")
            if timing.get("tokens") is not None:
                parts.append(f"{timing['tokens']} tok")
            if timing.get("tps") is not None:
                parts.append(f"tps {timing['tps']}")
        usage = block.usage
        if isinstance(usage, dict) and usage.get("total_tokens") is not None:
            parts.append(f"共 {usage['total_tokens']} tokens")
        return " · ".join(parts)

    # ------------------------------------------------------------------ 写入

    def add_system(self, content: str, **metadata: Any) -> TuiBlock:
        """追加系统提示块"""
        return self._new_block("system", content=content, metadata=metadata)

    def add_user(self, content: str, queued: bool = False, **metadata: Any) -> TuiBlock:
        """追加用户输入块，并结算上一轮仍在进行的流式块

        ``queued=True``：这条消息只是在排队（当前轮次还在输出），因此**不能**
        结算流式块，否则正在流式的回复会被提前标记为完成、后续 chunk 会另起一块。
        块状态标为 ``queued``，由 UI 显示成「排队中」。
        """
        if not queued:
            self._close_streaming()
        return self._new_block(
            "user",
            status="queued" if queued else "done",
            content=content,
            metadata=metadata,
        )

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

    def load_messages(
        self, messages: list[dict[str, Any]], include_system: bool = False
    ) -> None:
        """用模型消息历史重建渲染块（切换会话时恢复界面）

        与 ``handle_chunk`` 不同，这里按消息的最终形态直接建块，不走流式状态机。
        消息结构同 ``agent.context_manager.get_messages()``。默认跳过 system
        消息（实时渲染时系统提示也不会出现在消息区）。
        """
        self.clear()
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role == "system":
                content = _content_text(message.get("content"))
                if content and include_system:
                    self.add_system(content)
            elif role == "user":
                content = _content_text(message.get("content"))
                if content:
                    self.add_user(content)
            elif role == "assistant":
                reasoning = message.get("reasoning_content")
                if reasoning:
                    self._new_block("reasoning", content=str(reasoning))
                content = _content_text(message.get("content"))
                if content:
                    self._new_block("assistant", content=content)
                for call in message.get("tool_calls") or []:
                    if isinstance(call, dict):
                        self._restore_tool_call(call)
            elif role == "tool":
                self._restore_tool_result(message)

    def _restore_tool_call(self, call: dict[str, Any]) -> TuiBlock:
        """按已完成的 tool_call 建一张工具卡片（等待结果回填）"""
        function = call.get("function") or {}
        name = function.get("name") or call.get("name") or "unknown"
        arguments = function.get("arguments")
        if arguments is None:
            arguments = call.get("arguments")
        block = self._start_tool(name, tool_id=call.get("id"))
        block["tool_calls"] = [call]
        block["status"] = "calling"
        block["tool_arguments"] = self._parse_arguments(arguments)
        self._notify("update", block)
        return block

    def _restore_tool_result(self, message: dict[str, Any]) -> TuiBlock:
        """把 tool 消息回填到对应的工具卡片上"""
        name = message.get("name")
        call_id = message.get("tool_call_id")
        result = _content_text(message.get("content"))
        block = self._tool_by_id.get(call_id) if call_id else None
        if block is None:
            block = self._find_tool(name) if name else None
        if block is None:
            block = self._new_block("tool", status="done", tool_name=name or "unknown")
        block["tool_result"] = result
        block["content"] = self._truncate(result)
        block["status"] = "done"
        self._release_tool(name, block)
        self._notify("update", block)
        return block

    def dump_snapshot(self) -> list[dict[str, Any]]:
        """导出所有渲染块（含耗时/timing/usage），供会话持久化

        与 ``load_messages``（从模型消息重建）不同，dump_snapshot / load_snapshot
        保留实时的界面状态：思考与工具卡的耗时、助手 timing 小字等，恢复后与切走前一致。

        注意：不要和 ``snapshot()`` 混淆 —— 那个是**深拷贝**，供界面安全遍历用；
        这个产出的是可直接 JSON 序列化的扁平字段字典。
        """
        self.commit()
        out: list[dict[str, Any]] = []
        for block in self.blocks:
            out.append({key: block.get(key) for key in _SNAPSHOT_FIELDS})
        return out

    def load_snapshot(self, blocks: list[dict[str, Any]]) -> None:
        """从 ``dump_snapshot()`` 的结果恢复渲染块（原样重放，不经过消息解析）"""
        self.clear()
        for item in blocks or []:
            if not isinstance(item, dict):
                continue
            role = item.get("role") or "assistant"
            fields = {k: v for k, v in item.items() if k not in ("role", "status")}
            block = self._new_block(role, status=item.get("status") or "done", **fields)
            self._notify("update", block)

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
        self._round_reasoning = None
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
        self._round_reasoning = None

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
            timing=None,
            duration=None,
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
        timing = chunk.get("timing")

        if self._current_reasoning is not None:
            self._close_reasoning()

        if self._current_assistant is None:
            self._current_assistant = self._new_block("assistant", status="streaming")
        self._current_assistant["status"] = "streaming"
        self._append_field(self._current_assistant, "content", text)
        if usage is not None:
            self._current_assistant["usage"] = usage
        if timing is not None:
            self._current_assistant["timing"] = timing
            self._attach_thinking_duration(timing)
        self._notify("update", self._current_assistant)
        return self._current_assistant

    def _attach_thinking_duration(self, timing: dict[str, Any]) -> None:
        """把本轮思考耗时归到对应的「思考」块（收尾 timing 里的 thinking_duration）"""
        block = self._round_reasoning
        thinking = timing.get("thinking_duration")
        if block is None or thinking is None:
            return
        block["duration"] = thinking
        self._round_reasoning = None
        self._notify("update", block)

    def _handle_reasoning(self, chunk: dict[str, Any]) -> TuiBlock:
        text = chunk.get("reasoning_content", "") or ""

        if self._current_assistant is not None:
            self._close_assistant()

        if self._current_reasoning is None:
            self._current_reasoning = self._new_block("reasoning", status="streaming")
        self._current_reasoning["status"] = "streaming"
        self._append_field(self._current_reasoning, "content", text)
        # 记录本轮的思考块，收尾 timing 到达时把 thinking_duration 归到它
        self._round_reasoning = self._current_reasoning
        self._notify("update", self._current_reasoning)
        return self._current_reasoning

    def _handle_tool_chunk(self, chunk: dict[str, Any]) -> TuiBlock:
        name = chunk.get("tool_name")
        arguments = chunk.get("tool_arguments")
        index = chunk.get("tool_index")

        if index is not None:
            # 并发调用：按 index 定位，绝不按名字串到别的调用上。
            # 已完成的旧卡片不复用（每次 LLM 响应的 index 都从 0 重新开始）
            block = self._routed_tool_by_index(index)
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

            block = self._routed_tool_by_index(index)
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
        if chunk.get("duration") is not None:
            block["duration"] = chunk["duration"]
        block["status"] = "done"
        self._release_tool(name, block)
        self._notify("update", block)
        return block

    @staticmethod
    def _is_active_tool(block: TuiBlock | None) -> bool:
        """工具卡片是否仍在进行中（可用于承接后续流式片段）"""
        return block is not None and block["status"] in ("building", "calling")

    def _routed_tool_by_index(self, index: int | None) -> TuiBlock | None:
        """按 index 取当前轮次的工具卡片；已完成的不复用，避免跨轮次串卡"""
        if index is None:
            return None
        block = self._tool_by_index.get(index)
        if not self._is_active_tool(block):
            return None
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
        """超过 max_length 时从最旧的块开始裁剪，保留 system、进行中的块与最新块

        `max_length<=0`（默认）表示不裁剪。
        """
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
