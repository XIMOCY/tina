"""tina 终端界面（基于 Textual）

风格参考 opencode：深色、简洁、消息流式渲染。

特性：
- 助手正文流式渲染，推理内容与工具内容均可折叠
- 消费与渲染解耦（定时渲染泵），快速输出也不掉帧
- 自动为 Agent 注册工具确认事件（require_confirmation 工具弹出确认框）
- 上下文 token 占用与上限进度展示，超限变红警告
- 运行中动画，Escape 可打断本轮回复
- 快捷键在消息之间跳转

只依赖 `TuiMessageStore`（列表）与 `TokenCounter`（计数），界面本身不计算 token。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from bisect import bisect_right
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (
    Collapsible,
    Header,
    Label,
    LoadingIndicator,
    Markdown,
    OptionList,
    ProgressBar,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from tina.agent.core.state import AgentState
from tina.core import logger
from tina.utils.session_store import SessionStore, clean_title
from .context_manager import (
    TuiBlock,
    TuiMessageStore,
    _content_text,
    make_unlimited_context_manager,
)
from .token import TokenCounter

if TYPE_CHECKING:
    from tina.agent import Agent, BaseContextManager, MultimodalAgent


TINA_THEME = Theme(
    name="tina",
    primary="#e0a45e",
    secondary="#7aa2f7",
    accent="#e0a45e",
    foreground="#cbd3df",
    background="#0d0f13",
    surface="#14171d",
    panel="#1a1e26",
    boost="#232935",
    success="#9ece6a",
    warning="#e0af68",
    error="#f07178",
    dark=True,
)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _one_line(text: Any) -> str:
    """把多行文本压成一行，合并多余空白"""
    return " ".join(str(text or "").split())


def _shorten(text: str, limit: int = 160) -> str:
    """过长文本截断并加省略号"""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _visual_lines(text: str, width: int) -> int:
    """按显示宽度折行后算文本占多少行（显式换行也算）

    只用于估算未挂载块的高度，所以「大致接近」即可，但**不能有系统性偏差**：
    一直偏大或一直偏小会让估算高度和真实高度越差越多，窗口位置随之错位、
    视口露出空白。宽字符（中文等）按 2 列计就是为了不系统性低估。
    """
    if not text:
        return 1
    width = max(1, width)
    total = 0
    for line in text.split("\n"):
        wide = sum(1 for char in line if ord(char) > 0x2E7F)
        columns = len(line) + wide
        total += max(1, (columns + width - 1) // width)
    return max(1, total)


_TITLE_TRIM_CHARS = "「」『』\"'“”‘’#*·-—:： 　"


def _clean_generated_title(raw: Any) -> str:
    """清洗模型生成的会话标题：去引号/前缀/换行并截断"""
    text = clean_title(raw).strip(_TITLE_TRIM_CHARS)
    for prefix in ("标题：", "标题:", "title:", "title："):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):]
            break
    return text.strip(_TITLE_TRIM_CHARS)


def _format_timing(timing: dict[str, Any] | None) -> str:
    """把流式计时字典格式化成一行小字：耗时 / tokens / tps"""
    if not timing:
        return ""
    parts: list[str] = []

    if timing.get("duration") is not None:
        parts.append(f"耗时 {timing['duration']}s")
    if timing.get("tokens") is not None:
        parts.append(f"{timing['tokens']} tok")
    if timing.get("tps") is not None:
        parts.append(f"tps {timing['tps']}")

    return " · ".join(parts)


def _format_meta(metadata: Any) -> str:
    """把工具包的 metadata 字典压成一行 k=v；空则返回空串"""
    if not metadata or not isinstance(metadata, dict):
        return ""
    return "  ".join(f"{key}={value}" for key, value in metadata.items())


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _grab_clipboard_image() -> str | None:
    """尝试从系统剪贴板取一张图片，存成临时 PNG 并返回路径；取不到返回 None

    依赖可选的 Pillow（`pip install pillow`）；剪贴板里是图片文件路径时直接返回该路径。
    """
    try:
        from PIL import ImageGrab  # 可选依赖
    except Exception:  # noqa: BLE001 没装 Pillow 就当作不支持
        return None
    try:
        data = ImageGrab.grabclipboard()
    except Exception:  # noqa: BLE001
        return None
    if data is None:
        return None
    try:
        if isinstance(data, list):
            for item in data:
                if str(item).lower().endswith(_IMAGE_EXTS):
                    return str(item)
            return None
        path = os.path.join(
            tempfile.gettempdir(), f"tina_paste_{int(time.time() * 1000)}.png"
        )
        data.save(path, "PNG")
        return path
    except Exception:  # noqa: BLE001
        return None


def _escape_markup(text: Any) -> str:
    """彻底转义文本中的方括号，供 Rich/Textual markup 安全显示。

    `textual.markup.escape` 只转义以小写字母 / `#` / `/` / `@` 开头的方括号，
    `[MCP:pixellab]` 这类大写开头的会被当成标签，导致 markup 失衡甚至抛
    MarkupError。这里先把反斜杠翻倍，再转义所有 `[`，可安全包裹任意文本。
    """
    return str(text).replace("\\", "\\\\").replace("[", "\\[")


def _param_type(info: Any) -> str:
    """从 JSON Schema 参数定义里取出可读的类型"""
    if not isinstance(info, dict):
        return "any"
    param_type = info.get("type")
    if param_type:
        return str(param_type)
    for key in ("anyOf", "oneOf", "allOf"):
        options = info.get(key)
        if isinstance(options, list) and options:
            types: list[str] = []
            for option in options:
                option_type = _param_type(option)
                if option_type not in types:
                    types.append(option_type)
            return " | ".join(types)
    return "any"


class UserMessage(Static):
    """用户消息块"""

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(f"[bold #e0a45e]❯[/] {_escape_markup(content)}", **kwargs)
        self.add_class("user-message")


class ErrorMessage(Static):
    """错误消息块"""

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(f"[bold red]✗[/] {_escape_markup(content)}", markup=True, **kwargs)
        self.add_class("error-message")


class SystemMessage(Static):
    """系统 / 提示消息块"""

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(_escape_markup(content), markup=True, **kwargs)
        self.add_class("system-message")


class StickyHeader(Static):
    """吸顶的折叠块标题

    当某个已展开的折叠块（思考/工具/结果）内容很长、标题被滚出视口上方时，
    由它在消息区顶部显示该块标题，点击即可折叠/展开，免去滚回顶部。
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", markup=True, **kwargs)
        self.add_class("sticky-header")

    def on_click(self) -> None:
        try:
            handler = getattr(self.app, "_toggle_sticky_header", None)
        except Exception:
            return
        if handler is not None:
            handler()


class Spacer(Static):
    """窗口化渲染的占位块

    ``BLANK = True`` 让 Textual 只把它渲染成空白条、不渲染子节点，
    大高度占位的渲染成本几乎为零。
    """

    BLANK = True


class ChatInput(TextArea):
    """多行输入框

    - Enter 发送，Shift+Enter / Alt+Enter 换行
    - Tab 补全 # 命令
    - 支持粘贴包含换行的多行文本
    """

    class Submitted(Message):
        """用户提交输入"""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    async def _on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            return
        if event.key in ("shift+enter", "alt+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            complete = getattr(self.app, "complete_command", None)
            if complete is not None:
                complete(self)
            return
        if event.key == "ctrl+v":
            # 剪贴板里有图片就附加为待发送图片；否则退回普通文本粘贴
            attach = getattr(self.app, "attach_clipboard_image", None)
            if attach is not None and attach():
                event.stop()
                event.prevent_default()
                return
        await super()._on_key(event)


class ReasoningBlock(Collapsible):
    """推理内容块，可折叠"""

    def __init__(self, collapsed: bool = True, **kwargs: Any) -> None:
        self._text = Static("", classes="reasoning-text", markup=False)
        super().__init__(self._text, title="思考", collapsed=collapsed, **kwargs)
        self.add_class("reasoning-block")

    def set_block(self, block: TuiBlock) -> None:
        self._text.update(block.content)
        if block.is_streaming:
            self.title = "思考中…"
        elif block.duration is not None:
            self.title = f"思考过程 · {block.duration}s"
        else:
            self.title = "思考过程"


class MessageScroll(VerticalScroll):
    """消息滚动区：把滚动位置变化通知 App，用于粘性到底判断与吸顶标题"""

    def compose(self) -> ComposeResult:
        # 吸顶标题固定在消息区顶部，不随内容滚动（Textual 用 dock 实现）
        yield StickyHeader(id="sticky-header")
        # 窗口化渲染的上下占位（撑起未挂载块的高度）
        yield Spacer(id="spacer-top")
        yield Spacer(id="spacer-bottom")

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        try:
            app = self.app
        except Exception:
            return
        updater = getattr(app, "_update_stick", None)
        if updater is not None:
            updater(self)
        sticky = getattr(app, "_request_sticky_update", None)
        if sticky is not None:
            sticky()


class ResultBlock(Collapsible):
    """命令结果块，可折叠

    `markup=True` 时内容按 Rich 标记解析（用于 `#tools` 这类由我们生成、已转义的文本）；
    默认 `False`，避免命令输出里的 `[...]` 被当成标记。
    """

    def __init__(
        self, collapsed: bool = False, markup: bool = False, **kwargs: Any
    ) -> None:
        self._text = Static("", classes="result-text", markup=markup)
        super().__init__(self._text, title="结果", collapsed=collapsed, **kwargs)
        self.add_class("result-block")

    def set_block(self, block: TuiBlock) -> None:
        if block.title:
            self.title = block.title
        self._text.update(block.content)


class ToolBlock(Collapsible):
    """工具调用卡片，可折叠，展示参数与结果"""

    STATUS_LABELS = {
        "building": "构建中",
        "calling": "调用中",
        "done": "完成",
        "error": "出错",
    }

    def __init__(self, collapsed: bool = True, **kwargs: Any) -> None:
        self._args = Static("", classes="tool-args", markup=False)
        self._result = Static("", classes="tool-result", markup=False)
        super().__init__(
            self._args, self._result, title="工具", collapsed=collapsed, **kwargs
        )
        self.add_class("tool-block")

    def set_block(self, block: TuiBlock) -> None:
        name = block.tool_name or "unknown"
        status = self.STATUS_LABELS.get(block.status, block.status)
        title = f"{name} · {status}"
        if block.duration is not None:
            title += f" · {block.duration}s"
        self.title = title

        args = _stringify(block.tool_arguments).strip()
        self._args.update(f"参数：{args}" if args else "参数：-")

        result = _stringify(block.tool_result).strip()
        self._result.update(f"结果：\n{result}" if result else "结果：等待中…")


class AssistantBlock(Vertical):
    """助手正文块"""

    def __init__(self, **kwargs: Any) -> None:
        self.markdown = Markdown(classes="assistant-message")
        super().__init__(self.markdown, **kwargs)
        self.add_class("assistant-block")


class ToolArgsScreen(ModalScreen[None]):
    """查看完整工具参数的小窗口（确认时按 Ctrl+O 打开）"""

    BINDINGS = [
        Binding("escape", "close_screen", "关闭", show=False),
        Binding("q", "close_screen", "关闭", show=False),
        Binding("enter", "close_screen", "关闭", show=False),
    ]

    def __init__(self, tool_name: str, arguments: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._arguments = arguments

    def compose(self) -> ComposeResult:
        with Vertical(id="args-dialog"):
            yield Static(f"工具参数 · {_escape_markup(self._tool_name)}", id="args-title")
            with VerticalScroll(id="args-scroll"):
                yield Static(self._arguments, id="args-body", markup=False)

    def action_close_screen(self) -> None:
        self.dismiss()


class TinaTUI(App):
    """tina 终端聊天界面"""

    CSS = """
    Screen {
        background: $background;
        color: $foreground;
    }
    Header {
        background: $panel;
        color: $accent;
        text-style: bold;
    }
    Footer {
        background: $panel;
        color: $text-muted;
    }

    #messages {
        padding: 1 2 0 2;
        scrollbar-size-vertical: 1;
        scrollbar-background: $background;
        scrollbar-color: $panel;
        scrollbar-color-hover: $boost;
    }
    #welcome {
        padding: 1 1 1 1;
        margin-bottom: 1;
        background: $surface;
        border-left: thick $accent;
    }
    .sticky-header {
        dock: top;
        display: none;
        height: 1;
        padding: 0 1;
        color: $accent;
        background: $panel;
        text-style: bold;
    }

    #status {
        height: 1;
        padding: 0 2;
        background: $panel;
    }
    #status-text {
        width: 1fr;
        color: $text-muted;
    }
    #token-text {
        color: $text-muted;
        margin-right: 1;
    }
    #token-text.exceeded {
        color: $error;
        text-style: bold;
    }
    #token-text.warning {
        color: $warning;
    }
    #token-bar {
        width: 24;
    }
    #loading {
        width: 2;
        height: 1;
        color: $accent;
    }

    #command-hint {
        height: auto;
        max-height: 8;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
        border-top: solid $panel;
    }
    #prompt {
        height: 4;
        border: round $panel;
        background: $surface;
        padding: 0 1;
    }
    #prompt:focus {
        border: round $accent;
    }

    UserMessage {
        width: 100%;
        margin-bottom: 1;
        padding: 0 1;
        color: $foreground;
        background: $boost;
        border-left: thick $accent;
    }
    Markdown.assistant-message {
        margin: 0 0 1 2;
        padding: 0 1;
    }
    AssistantBlock {
        height: auto;
        margin: 0;
        padding: 0;
    }
    #bottom-bar {
        height: 1;
        padding: 0 2;
        background: $panel;
    }
    #last-stats {
        width: 1fr;
        color: $text-disabled;
        text-style: dim;
    }
    #session-status {
        color: $text-muted;
        margin-left: 1;
    }

    ReasoningBlock {
        margin: 0 0 1 2;
        padding: 0;
        border: none;
        border-left: thick $panel;
        background: $surface;
    }
    .reasoning-text {
        color: $text-muted;
        text-style: italic;
    }

    ToolBlock {
        margin: 0 0 1 2;
        padding: 0;
        border: none;
        border-left: thick $secondary;
        background: $surface;
    }
    .tool-args {
        color: $text-muted;
    }
    .tool-result {
        color: $foreground;
    }

    ResultBlock {
        margin: 0 0 1 0;
        padding: 0;
        border: none;
        border-left: thick $accent;
        background: $surface;
    }
    .result-text {
        color: $foreground;
    }

    .error-message {
        margin: 0 0 1 2;
        padding: 0 1;
        color: $error;
    }
    .system-message {
        margin-bottom: 1;
        padding: 0 1;
        color: $text-muted;
    }
    .jump-highlight {
        background: $boost;
    }

    #confirm-bar {
        height: auto;
        max-height: 15;
        padding: 0 2;
        background: $surface;
        border-top: thick $accent;
    }
    #confirm-question {
        color: $foreground;
        padding-top: 1;
        max-height: 10;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
    }
    #confirm-options {
        height: auto;
        max-height: 5;
        margin: 1 0;
    }

    ToolArgsScreen {
        align: center middle;
    }
    #args-dialog {
        width: 80%;
        max-width: 110;
        height: auto;
        max-height: 80%;
        padding: 0 1;
        background: $surface;
        border: round $accent;
    }
    #args-title {
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }
    #args-scroll {
        height: auto;
        max-height: 24;
        background: $panel;
    }
    #args-body {
        padding: 0 1;
        color: $foreground;
    }
    """

    BINDINGS = [
        Binding("ctrl+down", "jump_next", "下一条消息", priority=True),
        Binding("ctrl+up", "jump_prev", "上一条消息", priority=True),
        Binding("ctrl+end", "jump_last", "最后一条", priority=True, show=False),
        Binding("ctrl+home", "jump_first", "第一条", priority=True, show=False),
        Binding("ctrl+r", "toggle_reasoning", "折叠思考", priority=True),
        Binding("ctrl+t", "toggle_tools", "折叠工具/结果", priority=True),
        Binding("ctrl+l", "clear_view", "清空界面", priority=True, show=False),
        Binding("ctrl+o", "show_tool_args", "查看工具参数", priority=True, show=False),
        Binding("escape", "escape", "打断", priority=True),
    ]

    # 注意：不要叫 COMMANDS，那是 Textual 命令面板的注册表（值是 provider）
    TUI_COMMANDS = {
        "#help": "查看可用命令",
        "#tools": "查看工具包；#tools 包名 看某包工具",
        "#context": "查看当前上下文",
        "#model": "查看当前模型信息",
        "#tokens": "查看 token 统计",
        "#compact": "压缩上下文（总结并写入 system）",
        "#export": "导出本次会话为 Markdown 文件",
        "#sessions": "列出已保存的会话（可跟关键字过滤）",
        "#switch": "切换会话，如 #switch 登录重构",
        "#new": "新建会话（当前会话自动保存）",
        "#rename": "重命名当前会话，如 #rename 登录重构",
        "#delete": "删除会话，如 #delete 登录重构",
        "#clear": "清空上下文与界面",
        "#exit": "退出",
    }

    # 支持「会话名」作为参数并参与 Tab 补全的命令
    SESSION_ARG_COMMANDS = ("#switch", "#delete", "#sessions")
    # 命令提示栏里最多列出几个会话候选
    SESSION_HINT_LIMIT = 5
    # 右下角「当前对话」指示最多显示多少个字
    SESSION_LABEL_MAX = 32

    # 窗口化渲染：只把视口附近的块挂成 widget，其余用占位 spacer 撑高度。
    #
    # 实测（headless 基准 little_toy/bench_tui_window.py）：Textual 的整屏重排开销随
    # 挂载 widget 数线性增长，300 条消息约 1200 个 widget 时一帧要 30ms，窗口化后
    # DOM 降到几十个、重排降到 ~1ms。
    #
    # 但**默认关闭**：真实终端里代价的大头是「重绘」而不是「布局」，窗口化是靠不断
    # 挂载/卸载 widget 换取少排几个块，DOM 增删会让 Textual 标记更大区域重绘；而
    # agent 会话的常态是持续流式追加（每次追加都可能触发窗口移动 → churn），真正
    # 擅长的「长历史里滚动」反而是少数时刻。实测在 Windows Terminal 下开启后比关闭
    # 更卡，故默认 False，保留为可选。
    WINDOWED = False
    WIN_BUFFER = 8    # 视口上下各多挂几个块（滚动缓冲，避免频繁重挂）
    WIN_MIN = 16      # 窗口至少挂多少个块（小视口时的下限）
    WIN_MAX = 120     # 窗口最多挂多少个块
    # 除 TUI_COMMANDS 外，这些别名也按命令处理（在 _handle_command 里分发）
    COMMAND_ALIASES = (
        "#exit",
        "#quit",
        "#help",
        "#?",
        "#h",
        "#save",
        "#compress",
        "#summary",
    )

    COMPACT_INSTRUCTION = (
        "请你根据你过去的历史，总结你接下来需要用的信息，"
        "我们将会使用这个信息作为新的开始。"
    )

    # 关闭 Textual 自带的命令面板（默认 ctrl+p），tina 用自己的 # 命令
    ENABLE_COMMAND_PALETTE = False

    # 渲染泵间隔：界面更新与滚动统一在这里做，与 chunk 速率解耦
    PUMP_INTERVAL = 0.1
    # 流式块重渲染的最小间隔（秒）。采用增量 append 后，开销与新增内容成正比，
    # 因此只需轻微随长度放宽，长文本也能保持较顺滑的刷新。
    RENDER_INTERVAL = 0.06
    RENDER_INTERVAL_MAX = 0.2

    # 确认框内联显示参数的上限，超过则只显示提示（按 Ctrl+O 查看完整参数）
    CONFIRM_INLINE_ARGS = 200
    CONFIRM_INLINE_LINES = 4

    def __init__(
        self,
        agent: Agent | MultimodalAgent,
        max_tokens: int | None = None,
        *,
        reasoning_collapsed: bool = True,
        auto_confirm: bool = True,
        unlimited_context: bool = False,
        session_root: str | None = None,
    ) -> None:
        super().__init__()
        self.agent: Agent | MultimodalAgent = agent
        self.context = TuiMessageStore()
        self.counter = TokenCounter(max_tokens=max_tokens)
        self.reasoning_collapsed = reasoning_collapsed
        self.auto_confirm = auto_confirm
        if unlimited_context:
            self.install_context_manager(make_unlimited_context_manager(agent))

        # 会话持久化：<session_root>/.tina/chat_sessions/ 下按会话归档聊天
        self._session_root = session_root
        self._session_store: SessionStore | None = None
        self._session_id: str | None = None
        self._title_scheduled = False

        self._widgets: dict[int, Any] = {}
        self._message_widgets: list[Any] = []
        # 窗口化渲染状态：_win_ids 为当前挂载的块 id（窗口，按顺序）
        self._win_ids: list[int] = []
        self._win_heights: dict[int, int] = {}
        # 未实测块的高度估算缓存：block_id -> ((内容长度, 宽度), 高度)
        self._est_cache: dict[int, tuple[tuple[int, int], int]] = {}
        # 高度前缀和缓存：(ids, tops)，块列表或任一高度变化时失效
        self._tops_cache: tuple[list[int], list[int]] | None = None
        self._spacer_top: Static | None = None
        self._spacer_bottom: Static | None = None
        self._in_window_update = False
        self._jump_index = -1
        self._busy = False
        self._confirm_future: asyncio.Future | None = None
        self._confirm_lock: asyncio.Lock | None = None
        self._pending_confirms = 0
        self._pending_tool: str | None = None
        self._pending_tool_args: str | None = None
        self._always_allow: set[str] = set()
        # 已粘贴、待随下一条消息发送的图片路径
        self._pending_images: list[str] = []
        self._completion_matches: list[str] = []
        self._completion_index = 0
        self._last_render: dict[int, float] = {}
        self._stick = True

        # 渲染泵状态
        self._dirty: dict[int, TuiBlock] = {}
        self._turn_refs: dict[int, TuiBlock] = {}
        self._scroll_pending = False
        self._last_status: str | None = None

        # 吸顶标题状态
        self._sticky_pending = False
        self._sticky_target: Any = None

        # 打断 / 运行状态
        self._interrupted = False
        self._turn_worker: Any = None
        self._active_assistant: TuiBlock | None = None

        # 启动时缓存的组件引用
        self._messages: MessageScroll | None = None
        self._status_text: Label | None = None
        self._token_label: Label | None = None
        self._token_bar: ProgressBar | None = None
        self._loading: LoadingIndicator | None = None
        self._sticky: StickyHeader | None = None
        self._last_stats: Label | None = None
        # 底部「最近一条消息」的耗时文案（切换会话时要恢复）
        self._last_stats_text = ""
        self._session_status: Label | None = None

        if auto_confirm:
            self._register_tool_confirmation()

    # ------------------------------------------------------------------ 生命周期

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield MessageScroll(id="messages")
        with Horizontal(id="status"):
            yield Label("就绪", id="status-text")
            yield LoadingIndicator(id="loading")
            yield Label("", id="token-text")
            yield ProgressBar(
                total=100, show_percentage=False, show_eta=False, id="token-bar"
            )
        with Vertical(id="confirm-bar"):
            yield Static("", id="confirm-question")
            yield OptionList(id="confirm-options")
        yield Static("", id="command-hint")
        yield ChatInput(
            placeholder="输入消息，Enter 发送，Shift+Enter 换行；#help / Tab 补全，Ctrl+V 粘贴图片",
            id="prompt",
        )
        with Horizontal(id="bottom-bar"):
            yield Label("", id="last-stats")
            yield Label("", id="session-status")

    def on_mount(self) -> None:
        self._log_runtime_info()
        self._apply_theme()
        self.title = "tina"
        self.sub_title = getattr(self.agent, "name", "") or ""
        self._messages = self.query_one("#messages", MessageScroll)
        self._status_text = self.query_one("#status-text", Label)
        self._token_label = self.query_one("#token-text", Label)
        self._token_bar = self.query_one("#token-bar", ProgressBar)
        self._loading = self.query_one("#loading", LoadingIndicator)
        self._loading.display = False
        self._last_stats = self.query_one("#last-stats", Label)
        self._sticky = self.query_one("#sticky-header", StickyHeader)
        self._sticky.display = False
        self._spacer_top = self.query_one("#spacer-top", Static)
        self._spacer_bottom = self.query_one("#spacer-bottom", Static)
        self._session_status = self.query_one("#session-status", Label)
        self._render_welcome()
        self._refresh_tokens()
        self._refresh_session_status()
        self.query_one("#command-hint", Static).display = False
        self.query_one("#confirm-bar", Vertical).display = False
        self.query_one("#prompt", ChatInput).focus()
        self.set_interval(self.PUMP_INTERVAL, self._render_pump)

    def _log_runtime_info(self) -> None:
        """启动时记一行：本进程加载的是哪一版 tui.py、窗口化开没开

        Python 不会热重载——改了源码但没重启进程，跑的还是老代码。之前就是吃了
        这个亏（拿一个没重启的旧进程和新进程比性能），所以留一条可追溯的记录。
        """
        try:
            mtime = Path(__file__).stat().st_mtime
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            logger.info(
                f"TUI 已加载：tui.py mtime={stamp} "
                f"WINDOWED={self.WINDOWED} pid={os.getpid()}"
            )
        except Exception:  # noqa: BLE001 只是日志，失败不影响运行
            pass

    def _apply_theme(self) -> None:
        try:
            self.register_theme(TINA_THEME)
            self.theme = TINA_THEME.name
        except Exception:
            pass

    def install_context_manager(self, context_manager: BaseContextManager) -> None:
        """替换 Agent 的上下文管理器，委托 `agent.set_context_manager`。

        注意：替换不会立即生效，但只有传入的实例里已有的消息会被使用。想保留
        当前历史，用 `tina_tui.make_unlimited_context_manager(agent)`。
        """
        self.agent.set_context_manager(context_manager)

    def _render_welcome(self) -> None:
        model = _escape_markup(getattr(getattr(self.agent, "llm", None), "model", "") or "")
        name = _escape_markup(getattr(self.agent, "name", "") or "tina")
        lines = [
            f"[bold #e0a45e]tina[/] [#7aa2f7]terminal[/]  [dim]{name}[/]",
        ]
        if model:
            lines.append(f"[dim]model  {model}[/]")
        # 欢迎信息放在吸顶标题之下、占位之前（有消息后会隐藏）
        self._messages_widget().mount(
            Static("\n".join(lines), id="welcome"), after=self._sticky
        )

    def _messages_widget(self) -> "MessageScroll":
        if self._messages is None:
            self._messages = self.query_one("#messages", MessageScroll)
        return self._messages

    # ------------------------------------------------------------------ 工具确认

    def _register_tool_confirmation(self) -> None:
        events = getattr(self.agent, "events", None)
        if events is None:
            return
        if events.get_tool_confirmation_handler() is not None:
            return

        @self.agent.on_tool_confirmation()
        async def _confirm(tool_name: str, tool_arguments: dict):
            allowed = await self._ask_tool_confirmation(tool_name, tool_arguments)
            if not allowed:
                block = self.context.add_error(
                    f"工具「{tool_name}」被用户拒绝使用"
                )
                self._sync_block(block)
                return (False, f"用户拒绝使用工具「{tool_name}」")
            return (True, "用户允许")

    async def _ask_tool_confirmation(self, tool_name: str, tool_arguments: Any) -> bool:
        if not self.is_running:
            return True
        # 多个工具（尤其并发同名工具）会同时请求确认，必须串行化，
        # 否则后来的确认会覆盖 _confirm_future，导致前面的调用永远等下去。
        if self._confirm_lock is None:
            self._confirm_lock = asyncio.Lock()
        self._pending_confirms += 1
        try:
            async with self._confirm_lock:
                if tool_name in self._always_allow:
                    return True

                loop = asyncio.get_running_loop()
                self._confirm_future = loop.create_future()
                self._pending_tool = tool_name
                self._show_confirm_bar(tool_name, tool_arguments)
                try:
                    return await self._confirm_future
                finally:
                    self._confirm_future = None
                    self._pending_tool = None
                    self._hide_confirm_bar()
                    self.query_one("#prompt", ChatInput).focus()
        finally:
            self._pending_confirms -= 1

    def _show_confirm_bar(self, tool_name: str, tool_arguments: Any) -> None:
        bar = self.query_one("#confirm-bar", Vertical)
        question = self.query_one("#confirm-question", Static)
        args = _stringify(tool_arguments).strip()
        self._pending_tool_args = args or None

        header = f"允许执行工具 [b]{_escape_markup(tool_name)}[/] 吗？"
        if not args:
            text = header
        elif (
            len(args) <= self.CONFIRM_INLINE_ARGS
            and args.count("\n") < self.CONFIRM_INLINE_LINES
        ):
            text = f"{header}\n[dim]{_escape_markup(args)}[/]"
        else:
            # 参数过长时不内联显示，避免把下面的选项挤出可见区
            text = f"{header}\n[dim]参数较长，按 Ctrl+O 查看完整参数[/]"

        queued = self._pending_confirms - 1
        if queued > 0:
            text += f"\n[dim]还有 {queued} 个工具调用等待确认[/]"
        question.update(text)

        options = self.query_one("#confirm-options", OptionList)
        options.clear_options()
        options.add_options(
            [
                Option("允许一次", id="allow"),
                Option("始终允许此工具", id="always"),
                Option("拒绝", id="deny"),
            ]
        )
        options.highlighted = 0
        bar.display = True
        options.focus()

    def _hide_confirm_bar(self) -> None:
        self._pending_tool_args = None
        self.query_one("#confirm-bar", Vertical).display = False

    @on(OptionList.OptionSelected, "#confirm-options")
    def _on_confirm_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        option_id = event.option_id
        if option_id == "always" and self._pending_tool:
            self._always_allow.add(self._pending_tool)
        future = self._confirm_future
        if future is not None and not future.done():
            future.set_result(option_id != "deny")

    def action_show_tool_args(self) -> None:
        """查看当前待确认工具的完整参数（小窗口）"""
        if not self._pending_tool_args or isinstance(self.screen, ToolArgsScreen):
            return
        self.push_screen(
            ToolArgsScreen(self._pending_tool or "工具", self._pending_tool_args)
        )

    def action_escape(self) -> None:
        """Escape：参数窗/确认框在则关闭，否则打断本轮回复"""
        if isinstance(self.screen, ToolArgsScreen):
            self.screen.dismiss()
            return
        future = self._confirm_future
        if future is not None and not future.done():
            future.set_result(False)
            return
        if self._busy and not self._interrupted:
            self._interrupt_turn()

    def _interrupt_turn(self) -> None:
        self._interrupted = True
        self._set_status("正在打断…")
        worker = self._turn_worker
        if worker is not None:
            worker.cancel()

    # ------------------------------------------------------------------ 输入与命令

    @on(TextArea.Changed, "#prompt")
    def _on_input_changed(self, event: TextArea.Changed) -> None:
        self._update_command_hint(event.text_area.text)

    @on(ChatInput.Submitted)
    async def _on_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#prompt", ChatInput).clear()
        self._hide_command_hint()
        if not text:
            return
        # 用户主动发送/执行命令时，重新贴回底部跟随输出
        self._stick = True
        if text.startswith("#") and self._looks_like_command(text):
            await self._handle_command(text)
            return
        if self._busy:
            self.notify("正在回复中，Esc 可打断，请稍候。", severity="warning")
            return
        images = self._pending_images
        self._pending_images = []
        self._turn_worker = self._run_turn(text, images)

    def _looks_like_command(self, text: str) -> bool:
        """首个 token 是已知命令/别名才算命令，否则当普通消息。

        这样 Markdown 标题（``# 标题``）、``## xxx`` 或拼错的 ``#foo`` 不会被吞掉。
        """
        parts = text.split(maxsplit=1)
        if not parts:
            return False
        head = parts[0].lower()
        return head in self.TUI_COMMANDS or head in self.COMMAND_ALIASES

    def attach_clipboard_image(self) -> bool:
        """把系统剪贴板里的图片附加到下一条消息；成功返回 True"""
        path = _grab_clipboard_image()
        if not path:
            self.notify("剪贴板里没有图片（或未安装 Pillow）", severity="warning")
            return False
        self._pending_images.append(path)
        self.notify(
            f"已附加图片：{os.path.basename(path)}"
            f"（待发送 {len(self._pending_images)} 张）"
        )
        return True

    def _agent_stream(self, instruction: str, images: list[str] | None):
        """按是否带图片选择预测入口：多模态 Agent 用 image=，普通 Agent 忽略"""
        if images:
            try:
                return self.agent.apredict(instruction=instruction, image=images)
            except TypeError:
                self.notify("当前 Agent 不支持图片输入，已忽略图片", severity="warning")
        return self.agent.apredict(instruction=instruction)

    async def _handle_command(self, command: str) -> None:
        text = command.strip()
        cmd = text.lower()
        parts = text.split(maxsplit=1)
        head = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if head in ("#export", "#save"):
            self._export_session(arg)
        elif cmd in ("#exit", "#quit"):
            self.exit()
        elif cmd in ("#help", "#?", "#h"):
            self._show_help()
        elif head == "#tools":
            self._show_tools(arg)
        elif cmd == "#model":
            self._show_model()
        elif cmd == "#tokens":
            self._show_tokens()
        elif cmd == "#clear":
            await self.action_clear_view()
            self._result("提示", "已清空上下文与界面")
        elif cmd == "#context":
            self._show_context()
        elif head == "#sessions":
            self._show_sessions(arg)
        elif head == "#switch":
            await self._switch_session(arg)
        elif head == "#new":
            await self._new_session(arg)
        elif head == "#rename":
            self._rename_session(arg)
        elif head == "#delete":
            await self._delete_session(arg)
        elif cmd in ("#compact", "#compress", "#summary"):
            if self._busy:
                self.notify("正在回复中，Esc 可打断，请稍候。", severity="warning")
            else:
                self._turn_worker = self._compact_context()
        else:
            self._result("提示", f"未知命令：{command}\n输入 #help 查看可用命令")

    def _result(
        self,
        title: str,
        content: str,
        collapsed: bool = False,
        markup: bool = False,
    ) -> None:
        block = self.context.add_result(
            title, content, collapsed=collapsed, markup=markup
        )
        self._sync_block(block)

    def _notice(self, text: str) -> None:
        self._result("提示", text)

    def _show_help(self) -> None:
        lines = [
            "[bold]可用命令[/]   [dim]Enter 发送 · Tab 补全 · Ctrl+V 粘贴图片[/]",
            "",
        ]
        for name, desc in self.TUI_COMMANDS.items():
            lines.append(f"[bold cyan]{name:<10}[/] [dim]{desc}[/]")
        lines += [
            "",
            "[bold]快捷键[/]",
            "[dim]Ctrl+↑/↓ 跳转消息 · Ctrl+R 折叠思考 · Ctrl+T 折叠工具/结果 · "
            "Ctrl+O 查看工具参数 · Ctrl+L 清屏 · Esc 打断[/]",
        ]
        self._result("帮助", "\n".join(lines), markup=True)

    def _show_context(self) -> None:
        self.context.commit()
        blocks = self.context.get_blocks()
        lines = [f"{b.role}: {len(b.content)} 字" for b in blocks] or ["（空）"]
        self._result("当前上下文", "\n".join(lines))

    # ------------------------------------------------------------------ 会话管理

    @property
    def session_store(self) -> SessionStore:
        """当前项目的会话仓库（惰性创建，指向 ``.tina/chat_sessions``）"""
        if self._session_store is None:
            self._session_store = SessionStore(root=self._session_root_path())
        return self._session_store

    def _session_root_path(self) -> str:
        """会话文件放在哪里：显式指定 > Agent 上下文管理器的 root > 当前目录"""
        if self._session_root:
            return self._session_root
        root = getattr(getattr(self.agent, "context_manager", None), "root", None)
        return root or os.getcwd()

    def _agent_messages(self) -> list[dict[str, Any]]:
        """Agent 当前的模型消息（落盘与恢复都用它）"""
        context_manager = getattr(self.agent, "context_manager", None)
        if context_manager is None:
            return []
        try:
            return [m for m in context_manager.get_messages() if isinstance(m, dict)]
        except Exception:  # noqa: BLE001 读取失败不该让界面崩溃
            return []

    def _ensure_session(self) -> str:
        """返回当前会话 id；没有就新建一个

        不读取任何磁盘「当前会话」指针：每次打开都是全新对话，会话只在真正开始
        对话时才落盘（见 ``_persist_session``）。
        """
        store = self.session_store
        if self._session_id and store.exists(self._session_id):
            return self._session_id
        self._session_id = store.create(messages=self._agent_messages())
        return self._session_id

    def _has_conversation(self) -> bool:
        """Agent 上下文里是否已有真正的对话（user/assistant/tool）"""
        return any(
            message.get("role") in ("user", "assistant", "tool")
            for message in self._agent_messages()
        )

    def _persist_session(self) -> None:
        """把 Agent 当前消息写回会话文件；只有真正开始对话才落盘

        还没有会话、也还没有对话内容时直接跳过——这样刚打开或 ``#switch`` /
        ``#new`` 不会凭空多出一个空会话。
        """
        if self._session_id is None and not self._has_conversation():
            return
        try:
            session_id = self._ensure_session()
            # 同时保存渲染块快照：恢复后保留思考/工具耗时与助手 timing
            self.session_store.save(
                session_id,
                self._agent_messages(),
                blocks=self.context.snapshot(),
            )
            self._refresh_session_status()
        except (OSError, ValueError) as error:
            self._notice(f"会话保存失败：{error}")

    def _session_label_text(self) -> str:
        """右下角「当前对话」文字：无 / 标题 / id"""
        if not self._session_id:
            return "无"
        meta = self.session_store.get_meta(self._session_id)
        if meta is None or not meta.title:
            return self._session_id
        return meta.title

    def _refresh_session_status(self) -> None:
        """刷新右下角的当前对话指示"""
        label = self._session_status
        if label is None:
            return
        text = _shorten(self._session_label_text(), self.SESSION_LABEL_MAX)
        label.update(_escape_markup(text))

    def _load_messages_into_agent(self, messages: list[dict[str, Any]]) -> None:
        """把消息写进 Agent 的上下文管理器"""
        context_manager = getattr(self.agent, "context_manager", None)
        if context_manager is None:
            return
        try:
            context_manager.set_messages(list(messages))
            # Agent 缓存了初始化时的 messages 引用，这里同步，否则 get_messages()
            # 会返回上一个会话（运行时用 context_manager，故聊天本身不受影响）
            if hasattr(self.agent, "messages"):
                self.agent.messages = context_manager.get_messages()
        except Exception as error:  # noqa: BLE001
            self._notice(f"加载会话失败：{error}")

    def _reset_agent_messages(self) -> None:
        """清空对话消息但保留系统提示（新建 / 删除当前会话后调用）"""
        system: list[dict[str, Any]] = []
        for message in self._agent_messages():
            if message.get("role") == "system":
                system.append(message)
        self._load_messages_into_agent(system)

    async def _restore_view(self, blocks: list | None = None) -> None:
        """重建界面（切换 / 新建会话后调用）

        有渲染块快照时按快照原样恢复（保留耗时/timing）；否则从模型消息重建。
        """
        if blocks:
            self.context.load_snapshot(blocks)
        else:
            self.context.load_messages(self._agent_messages())
        # 历史请求的 usage 属于上一个会话，重建后先归零
        self.counter.reset()
        self._widgets.clear()
        self._message_widgets.clear()
        self._win_heights.clear()
        self._est_cache.clear()
        self._tops_cache = None
        self._last_render.clear()
        self._dirty.clear()
        self._turn_refs.clear()
        self._jump_index = -1
        self._active_assistant = None
        # 切换 / 新建后默认跟随底部（否则首拍窗口会按 scroll_y=0 算成「开头」，
        # 表现为先跳到顶部、再被拉回底部，中间还闪过一段空白）
        self._stick = True
        await self._clear_messages()
        self.context.commit()
        # 窗口化时只挂载能盖住视口的尾部若干块（其余靠占位撑高度，滚上去再按需挂载）；
        # 关掉窗口化时退回老做法：全部挂载（否则切换会话只会看到最后几条）
        blocks = self.context.get_blocks()
        if self.WINDOWED:
            vh = max(1, self._messages_widget().size.height)
            initial = self._window_size(len(blocks), vh)
            mounted = blocks[-initial:] if len(blocks) > initial else blocks
        else:
            mounted = blocks
        for block in mounted:
            await self._sync_block_async(block)
        self._window_update()
        # 此刻布局还没算完，max_scroll_y 还是旧值；等刷新后再确认一次到底
        self._scroll_pending = False
        self._request_scroll()
        # 底部 token 占用 / 整轮统计恢复成该会话最后的状态（快照里存着）
        self._restore_bottom_stats()
        self._refresh_tokens()

    def _restore_bottom_stats(self) -> None:
        """把底部的 token 占用与整轮统计恢复成该会话最后的状态

        这两项都随渲染块快照一起存了（`usage` / `timing`），切换会话后不该是空的。
        注意 `timing` 是单次 LLM 请求的计时，而实时运行时底部显示的是「整轮」统计，
        所以恢复出来的数字可能和切走前略有出入——但比空白好，也更贴近这条消息本身。
        """
        self.counter.reset()
        self._set_last_stats("")
        for block in reversed(self.context.get_blocks()):
            if self.counter.calls == 0:
                usage = block.get("usage")
                if usage:
                    self.counter.add_usage(usage)
            if not self._last_stats_text:
                timing = block.get("timing")
                if timing:
                    self._set_last_stats(_format_timing(timing))
            if self.counter.calls and self._last_stats_text:
                break

    def _show_sessions(self, keyword: str = "") -> None:
        metas = self.session_store.find(keyword)
        if not metas:
            text = f"没有匹配「{keyword}」的会话" if keyword else "还没有任何会话"
            self._result("会话", text)
            return
        current = self._session_id
        lines = []
        for index, meta in enumerate(metas, 1):
            mark = "●" if meta.id == current else " "
            lines.append(f"{mark} {index}. {meta.id}  {meta.display_title}")
        self._result("会话", "\n".join(lines))

    async def _switch_session(self, query: str) -> None:
        store = self.session_store
        if not query:
            self._show_sessions()
            return
        meta = store.resolve(query)
        if meta is None:
            self._result("会话", f"没有找到匹配「{query}」的会话（用 #sessions 查看列表）")
            return
        if meta.id == self._session_id:
            self._result("会话", f"已经在会话「{meta.display_title}」中")
            return

        self._persist_session()
        self._load_messages_into_agent(store.get_messages(meta.id))
        self._session_id = meta.id
        # 老会话只在还没有名字时补一个自动标题
        self._title_scheduled = bool(meta.title)
        await self._restore_view(store.get_blocks(meta.id))
        self._set_status("就绪")
        self._refresh_session_status()
        self._result("会话", f"已切换到「{meta.display_title}」({meta.id})")

    async def _new_session(self, title: str = "") -> None:
        self._persist_session()
        store = self.session_store
        session_id = store.create(messages=[], title=title)
        self._session_id = session_id
        self._title_scheduled = bool(title)
        self._reset_agent_messages()
        await self._restore_view()
        self._set_status("就绪")
        self._refresh_session_status()
        self._result("会话", f"已新建会话「{clean_title(title) or '（未命名）'}」({session_id})")

    def _rename_session(self, title: str) -> None:
        title = title.strip()
        if not title:
            self._result("会话", "用法：#rename 新的会话名")
            return
        if self._session_id is None:
            self._result("会话", "还没有会话，先发一条消息再重命名")
            return
        self._persist_session()
        meta = self.session_store.rename(self._session_id, title)
        if meta is None:
            self._result("会话", "当前会话不存在，无法重命名")
            return
        self._refresh_session_status()
        self._result("会话", f"已重命名为「{meta.display_title}」")

    async def _delete_session(self, query: str) -> None:
        store = self.session_store
        if not query:
            self._result("会话", "用法：#delete <会话名或 id>（用 #sessions 查看列表）")
            return
        matches = store.find(query)
        if not matches:
            self._result("会话", f"没有找到匹配「{query}」的会话")
            return
        if len(matches) > 1:
            lines = [f"{m.id}  {m.display_title}" for m in matches[:10]]
            self._result(
                "会话",
                f"「{query}」匹配到多个会话，请用更精确的 id：\n" + "\n".join(lines),
            )
            return

        meta = matches[0]
        if not store.delete(meta.id):
            self._result("会话", f"删除失败：{meta.id}")
            return
        if meta.id == self._session_id:
            # 删掉的是当前会话：清空上下文与界面，下次聊天会自动新建
            self._session_id = None
            self._title_scheduled = False
            self._reset_agent_messages()
            await self._restore_view()
            self._set_status("就绪")
        self._refresh_session_status()
        self._result("会话", f"已删除会话「{meta.display_title}」({meta.id})")

    def _schedule_session_title(self) -> None:
        """首轮对话结束后让模型给会话起个名字（每个会话只做一次）"""
        if self._title_scheduled:
            return
        session_id = self._session_id
        if not session_id:
            return
        self._title_scheduled = True
        meta = self.session_store.get_meta(session_id)
        if meta is not None and meta.is_custom_title:
            return  # 用户自己命名过，不覆盖
        self._generate_session_title(session_id)

    @work(exclusive=False, group="session-title")
    async def _generate_session_title(self, session_id: str) -> None:
        """后台用模型生成标题；失败或会话已切走就静默放弃"""
        llm = getattr(self.agent, "llm", None)
        prompt = self._title_prompt()
        if llm is None or not prompt:
            return
        try:
            reply = await llm.apredict(
                input_text=prompt, stream=False, temperature=0.3, max_tokens=32
            )
        except Exception:  # noqa: BLE001 起名失败不影响聊天
            return
        raw = reply.get("content") if isinstance(reply, dict) else reply
        title = _clean_generated_title(raw)
        if not title:
            return
        store = self.session_store
        if self._session_id == session_id and store.exists(session_id):
            store.set_auto_title(session_id, title)
            self._refresh_session_status()

    def _title_prompt(self) -> str:
        """用首条用户输入与首个助手回复拼起名提示"""
        user_text = ""
        assistant_text = ""
        for message in self._agent_messages():
            text = _content_text(message.get("content")).strip()
            if not text:
                continue
            role = message.get("role")
            if role == "user" and not user_text:
                user_text = text
            elif role == "assistant" and user_text and not assistant_text:
                assistant_text = text
                break
        if not user_text:
            return ""
        snippet = f"用户：{user_text[:400]}"
        if assistant_text:
            snippet += f"\n助手：{assistant_text[:400]}"
        return (
            "根据下面的对话内容，给这段对话起一个简短的中文标题。"
            "要求：不超过 12 个字，不要引号、不要标点、不要解释，只输出标题本身。\n\n"
            + snippet
        )

    def _show_tools(self, pack: str = "") -> None:
        """两段式：#tools 先列工具包（名称/metadata/工具数），#tools 包名 再看包内工具"""
        tools = getattr(self.agent, "tools", None)
        if tools is None:
            self._result("工具", "当前 Agent 没有工具")
            return

        bundles = self._all_bundles()
        direct = list(getattr(tools, "_direct_tools", []) or [])

        if pack:
            target = self._find_tool_bundle(pack)
            if target is None:
                self._result(
                    "工具", f"没有找到工具包「{pack}」（用 #tools 查看列表）"
                )
                return
            self._show_bundle_tools(target)
            return

        if not bundles:
            # 没有子包：直接列出全部工具
            self._show_bundle_tools(tools)
            return

        lines: list[str] = []
        if direct:
            lines.append(f"[bold]· 直属工具[/]  [dim]{len(direct)} 个[/]")
        for bundle in bundles:
            name = bundle.instance_name or "（未命名）"
            meta = _format_meta(bundle.metadata)
            line = (
                f"[bold #7aa2f7]{_escape_markup(name)}[/]  "
                f"[dim]{len(bundle.tools)} 个工具[/]"
            )
            if meta:
                line += f"  [dim]{_escape_markup(meta)}[/]"
            lines.append(line)
        lines.append("")
        lines.append("[dim]· #tools <包名> 查看某个包的工具（Tab 可补全包名）[/]")
        self._result(f"工具包（{len(bundles)}）", "\n".join(lines), markup=True)

    def _all_bundles(self) -> list:
        """顶层子工具包；MCP 未合并或合并的是空包时，从客户端实时补一份，保证能显示"""
        tools = getattr(self.agent, "tools", None)
        bundles = list(getattr(tools, "_sub_bundles", []) or []) if tools else []
        mcp = getattr(self.agent, "mcp_client", None)
        if mcp is not None:
            merged = [b for b in bundles if (b.instance_name or "") == "mcp"]
            if not merged or not merged[0].tools:
                try:
                    live = mcp.to_tina_tools()
                    if live.tools:
                        bundles = [
                            b for b in bundles if (b.instance_name or "") != "mcp"
                        ]
                        bundles.append(live)
                except Exception:  # noqa: BLE001 拿不到就算了
                    pass
        return bundles

    def _find_tool_bundle(self, name: str):
        """按名字找子工具包：精确 > 前缀 > 模糊"""
        bundles = self._all_bundles()
        key = name.strip().lower()
        for bundle in bundles:
            if (bundle.instance_name or "").lower() == key:
                return bundle
        for bundle in bundles:
            if (bundle.instance_name or "").lower().startswith(key):
                return bundle
        for bundle in bundles:
            if key and key in (bundle.instance_name or "").lower():
                return bundle
        return None

    def _tool_bundle_names(self) -> list[str]:
        return [
            bundle.instance_name
            for bundle in self._all_bundles()
            if bundle.instance_name
        ]

    def _show_bundle_tools(self, bundle) -> None:
        try:
            schemas = bundle.get_tools_for_llm()
        except Exception as error:  # noqa: BLE001
            self._result("工具", f"读取工具失败：{error}")
            return
        if not schemas:
            self._result("工具", "（无工具）")
            return
        blocks = self._render_tool_schemas(schemas)
        title = getattr(bundle, "instance_name", None) or "工具"
        self._result(
            f"{title}（{len(schemas)}）", "\n".join(blocks).rstrip(), markup=True
        )

    def _render_tool_schemas(self, schemas: list) -> list[str]:
        """把工具 schema 渲染成带参数的可读文本（name + 描述 + 参数）"""
        blocks: list[str] = []
        for index, schema in enumerate(schemas, 1):
            function = schema.get("function", {})
            name = function.get("name", "?")
            description = _one_line(function.get("description"))
            params = function.get("parameters", {}) or {}
            properties = params.get("properties", {}) or {}
            required = set(params.get("required", []) or [])

            blocks.append(f"{index}. [bold #7aa2f7]{_escape_markup(name)}[/]")
            if description:
                blocks.append(f"   [dim]{_escape_markup(_shorten(description))}[/]")

            if not properties:
                blocks.append("   [dim]参数：（无）[/]")
            else:
                name_width = max(len(str(p_name)) for p_name in properties)
                type_width = max(
                    len(_param_type(p_info)) for p_info in properties.values()
                )
                blocks.append("   [dim]参数：[/]")
                for p_name, p_info in properties.items():
                    param_type = _param_type(p_info)
                    flag = (
                        "[#e0af68]必填[/]"
                        if p_name in required
                        else "[dim]可选[/]"
                    )
                    p_desc = _one_line(
                        p_info.get("description") if isinstance(p_info, dict) else ""
                    )
                    line = (
                        f"     [#7dcfff]{_escape_markup(str(p_name)):<{name_width}}[/]  "
                        f"[dim]{_escape_markup(param_type):<{type_width}}[/]  {flag}"
                    )
                    if p_desc:
                        line += f"  {_escape_markup(_shorten(p_desc, 80))}"
                    blocks.append(line.rstrip())
            blocks.append("")
        return blocks

    def _show_model(self) -> None:
        llm = getattr(self.agent, "llm", None)
        if llm is None:
            self._result("模型", "当前 Agent 没有 llm")
            return
        lines = [
            f"model    {getattr(llm, 'model', '?')}",
            f"base_url {getattr(llm, 'base_url', '?')}",
        ]
        name = getattr(self.agent, "name", None)
        if name:
            lines.insert(0, f"agent    {name}")
        self._result("模型", "\n".join(lines))

    def _show_tokens(self) -> None:
        counter = self.counter
        limit = counter.max_tokens if counter.max_tokens is not None else "未设置"
        lines = [
            f"上下文 total    {counter.total_tokens}",
            f"prompt           {counter.prompt_tokens}",
            f"completion       {counter.completion_tokens}",
            f"请求次数         {counter.calls}",
            f"上限 max_tokens  {limit}",
        ]
        if counter.remaining is not None:
            lines.append(f"剩余             {counter.remaining}")
            lines.append(f"占用比例         {counter.ratio:.1%}")
        rate = counter.cache_hit_rate
        if rate is not None:
            lines.append(
                f"缓存命中         {counter.cache_hit_tokens} "
                f"/ {counter.cache_hit_tokens + counter.cache_miss_tokens} "
                f"({rate:.2%})"
            )
        self._result("Token 统计", "\n".join(lines))

    def _export_session(self, target: str = "") -> None:
        """把当前会话导出为 Markdown 文件"""
        path = self._resolve_export_path(target)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            markdown = self.context.to_markdown()
            path.write_text(markdown, encoding="utf-8")
        except OSError as error:
            self._result("导出失败", f"{path}\n{error}")
            return
        self._result("导出", f"已导出会话到 {path}")
        self.notify(f"已导出：{path}", severity="information")

    @staticmethod
    def _resolve_export_path(target: str) -> Path:
        """决定导出路径：默认当前目录 tina_session.md，可自定义"""
        raw = (target or "").strip().strip('"').strip("'")
        if not raw:
            return Path.cwd() / "tina_session.md"
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if raw.endswith(("/", "\\")) or path.is_dir():
            path = path / "tina_session.md"
        return path

    def _update_command_hint(self, value: str) -> None:
        found = self.query("#command-hint")
        if len(found) == 0:
            return  # 组件尚未挂载 / 正在卸载
        hint = found.first()
        text = value.strip()
        if not text.startswith("#"):
            hint.display = False
            return

        head, _, arg = text.partition(" ")
        if head.lower() in self.SESSION_ARG_COMMANDS:
            lines = self._session_hint(head, arg)
            if not lines:
                hint.display = False
                return
            hint.update("\n".join(lines))
            hint.display = True
            return

        if head.lower() == "#tools" and (arg or value.endswith(" ")):
            names = [
                n
                for n in self._tool_bundle_names()
                if not arg or n.lower().startswith(arg.lower())
            ]
            if not names:
                hint.display = False
                return
            lines = ["[dim]#tools：Tab 补全包名[/]"]
            lines += [
                f"[bold #7aa2f7]{_escape_markup(n)}[/]"
                for n in names[: self.SESSION_HINT_LIMIT]
            ]
            rest = len(names) - self.SESSION_HINT_LIMIT
            if rest > 0:
                lines.append(f"[dim]…还有 {rest} 个[/]")
            hint.update("\n".join(lines))
            hint.display = True
            return

        matches = [c for c in self.TUI_COMMANDS if c.startswith(text.lower())]
        if not matches:
            hint.display = False
            return
        if len(text) <= 1:
            # 只输入了 #：只铺命令名，别把每条说明也刷出来
            hint.update("[bold]" + "   ".join(matches) + "[/]")
        else:
            # 具体前缀：一行一条，命令名 + 说明
            hint.update(
                "\n".join(
                    f"[bold]{c}[/] [dim]{self.TUI_COMMANDS[c]}[/]" for c in matches
                )
            )
        hint.display = True

    def _session_hint(self, head: str, arg: str) -> list[str]:
        """会话类命令的参数提示：列出匹配的会话（id · 标题）"""
        metas = self.session_store.find(arg)
        if not metas:
            return []
        current = self._session_id
        lines = [f"[dim]{head}：Tab 补全会话 id[/]"]
        for meta in metas[: self.SESSION_HINT_LIMIT]:
            mark = "●" if meta.id == current else " "
            lines.append(f"{mark} {meta.id} · {_escape_markup(meta.display_title)}")
        rest = len(metas) - self.SESSION_HINT_LIMIT
        if rest > 0:
                lines.append(f"[dim]…还有 {rest} 个[/]")
        return lines

    def _hide_command_hint(self) -> None:
        found = self.query("#command-hint")
        if len(found):
            found.first().display = False

    def complete_command(self, input_widget: ChatInput) -> None:
        """Tab 补全：命令本身，或会话类命令后面的会话 id"""
        raw = input_widget.text
        text = raw.strip()
        if not text.startswith("#"):
            self._completion_matches = []
            return

        head, _, arg = text.partition(" ")
        if arg or raw.endswith(" "):
            # 参数补全：#switch / #delete / #sessions 后面补会话 id，#tools 后面补包名
            if head.lower() in self.SESSION_ARG_COMMANDS:
                candidates = [meta.id for meta in self.session_store.find(arg)]
            elif head.lower() == "#tools":
                candidates = [
                    n
                    for n in self._tool_bundle_names()
                    if n.lower().startswith(arg.lower())
                ]
            else:
                self._completion_matches = []
                return
            prefix = f"{head} "
            probe = arg
        else:
            candidates = [c for c in self.TUI_COMMANDS if c.startswith(text.lower())]
            prefix = ""
            probe = text.lower()

        if self._completion_matches and probe in self._completion_matches:
            # 同一批候选里继续循环
            self._completion_index = (self._completion_index + 1) % len(
                self._completion_matches
            )
            values = self._completion_matches
        else:
            if not candidates:
                self._completion_matches = []
                return
            self._completion_matches = candidates
            self._completion_index = 0
            values = candidates

        value = prefix + values[self._completion_index]
        input_widget.text = value
        input_widget.move_cursor((0, len(value)))
        self._update_command_hint(value)

    # ------------------------------------------------------------------ 推理

    @work(exclusive=True)
    async def _run_turn(
        self, instruction: str, images: list[str] | None = None
    ) -> None:
        self._busy = True
        self._interrupted = False
        self._active_assistant = None
        self._turn_refs.clear()
        self._dirty.clear()
        # 整轮（turn）统计：耗时 + 跨多次 LLM 请求累加的生成 token / 生成时长
        turn_started = time.perf_counter()
        turn_tokens = 0
        turn_gen = 0.0
        has_tokens = False
        self._start_loading()
        self._set_status("思考中…")

        user_block = self.context.add_user(instruction)
        self._mark_dirty(user_block, turn=True)

        try:
            async for chunk in self._agent_stream(instruction, images):
                timing = chunk.get("timing")
                if timing:
                    if timing.get("tokens") is not None:
                        turn_tokens += timing["tokens"]
                        has_tokens = True
                    if timing.get("gen_duration"):
                        turn_gen += timing["gen_duration"]
                block = self.context.handle_chunk(chunk)
                if chunk.get("usage") is not None:
                    self.counter.add_from_chunk(chunk)
                    self._refresh_tokens()
                self._refresh_status()
                if block is not None:
                    if block.role == "assistant" and block.get("status") == "streaming":
                        self._active_assistant = block
                    self._mark_dirty(block, turn=True)
                # 让出事件循环，保证渲染泵与重绘能插入（应对极快输出）
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 界面上要显示任何异常
            self._mark_dirty(self.context.add_error(error), turn=True)
        finally:
            # 本轮墙钟耗时（含工具执行，不含收尾渲染）
            turn_duration = time.perf_counter() - turn_started
            partial = self._partial_assistant_text()
            self.context.finish_turn()
            self.context.commit()
            # 只渲染本轮涉及到的块，避免每轮重解析全部历史（越用越卡）
            for block in list(self._turn_refs.values()):
                await self._sync_block_async(block)
            if self._interrupted:
                await self._finalize_interrupted_turn(partial)
            self._dirty.clear()
            self._turn_refs.clear()
            self._active_assistant = None
            self._turn_worker = None
            self._stop_loading()
            self._refresh_tokens()
            self._busy = False
            self._set_status("已打断" if self._interrupted else "就绪")
            # 底部统计：整轮（turn）耗时 / 生成量，而非最后一次 LLM 请求
            self._set_last_stats(
                self._format_turn_stats(
                    turn_duration, turn_tokens, turn_gen, has_tokens
                )
            )
            # 每轮结束落盘一次，避免退出时丢历史
            self._persist_session()
            self._schedule_session_title()

    def _partial_assistant_text(self) -> str:
        """本轮仍在流式的助手正文（尚未写入 Agent 上下文）"""
        block = self._active_assistant
        if block is None or block.get("status") != "streaming":
            return ""
        self.context.commit()
        return block.content

    async def _finalize_interrupted_turn(self, partial: str) -> None:
        """打断收尾：补齐被打断的工具结果、写回部分正文并复位 Agent 状态"""
        agent = self.agent
        try:
            self._mark_interrupted_tool_results(agent.context_manager)
        except Exception:  # noqa: BLE001
            pass
        if partial.strip():
            try:
                agent.context_manager.add_assistant_message(partial)
            except Exception:  # noqa: BLE001
                pass
        try:
            await agent.events.atrigger_on_turn_end()
        except Exception:  # noqa: BLE001
            pass
        try:
            agent.runtime.state = AgentState.IDLE
        except Exception:  # noqa: BLE001
            pass

        self._notice("已打断本轮回复")

    def _mark_interrupted_tool_results(
        self, context_manager: BaseContextManager
    ) -> None:
        """把已发出但还没有结果的 tool_call 补上「该次调用被打断」"""
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

    # ------------------------------------------------------------------ 上下文压缩

    @work(exclusive=True)
    async def _compact_context(self) -> None:
        """让 Agent 自我总结，把总结并入 system，并清空其余消息"""
        self._busy = True
        self._interrupted = False
        self._start_loading()
        self._set_status("压缩上下文中…")
        try:
            messages = self.agent.context_manager.get_messages()
            if not any(m.get("role") != "system" for m in messages):
                self._notice("没有可压缩的对话")
                return

            # 把这条指令当成一次普通用户输入，让 Agent 基于历史自我总结
            parts: list[str] = []
            async for chunk in self.agent.apredict(
                instruction=self.COMPACT_INSTRUCTION
            ):
                if chunk.get("role") == "tool" or chunk.get("tool_calls"):
                    # 换到新的 assistant 消息，只保留最后一段正文
                    parts.clear()
                elif chunk.get("role") == "assistant" and chunk.get("content"):
                    parts.append(chunk["content"])
            summary = "".join(parts).strip()
            if not summary:
                self._notice("压缩失败：模型未返回总结")
                return

            system = self.agent.get_system_prompt() or ""
            new_system = system.rstrip()
            if new_system:
                new_system += "\n\n"
            new_system += "[此前对话摘要]\n" + summary

            # 清空消息，再把总结写回 system
            self.agent.clear_messages()
            self.agent.set_system_prompt(new_system)

            await self._reset_view()
            self._notice(
                f"已压缩上下文（总结 {len(summary)} 字已并入 system）\n\n" + summary
            )
        except Exception as error:  # noqa: BLE001 界面上要显示任何异常
            block = self.context.add_error(error)
            self._sync_block(block)
        finally:
            self._busy = False
            self._turn_worker = None
            self._stop_loading()
            self._refresh_tokens()
            self._set_status("就绪")
            self._persist_session()

    async def _clear_messages(self) -> None:
        """清空消息区，并重建吸顶标题 / 占位 / 欢迎信息"""
        self._sticky_target = None
        self._win_ids = []
        self._win_heights.clear()
        await self._messages_widget().remove_children()
        self._sticky = StickyHeader(id="sticky-header")
        self._sticky.display = False
        self._spacer_top = Spacer(id="spacer-top")
        self._spacer_bottom = Spacer(id="spacer-bottom")
        # 占位默认 0 高；关掉窗口化时不会有人再调 _set_spacers，避免留下空白行
        self._spacer_top.styles.height = 0
        self._spacer_bottom.styles.height = 0
        # 等占位真正挂载好，避免窗口更新时拿到没有父节点的旧占位
        await self._messages_widget().mount(self._sticky)
        await self._messages_widget().mount(self._spacer_top)
        await self._messages_widget().mount(self._spacer_bottom)
        self._render_welcome()

    async def _reset_view(self) -> None:
        self.context.clear()
        self._widgets.clear()
        self._message_widgets.clear()
        self._win_heights.clear()
        self._est_cache.clear()
        self._tops_cache = None
        self._last_render.clear()
        self._dirty.clear()
        self._turn_refs.clear()
        self._jump_index = -1
        await self._clear_messages()

    # ------------------------------------------------------------------ 渲染同步

    def _create_widget(self, block: TuiBlock) -> Any:
        role = block.role
        if role == "user":
            return UserMessage(block.content)
        if role == "reasoning":
            return ReasoningBlock(collapsed=self.reasoning_collapsed)
        if role == "tool":
            return ToolBlock(collapsed=self.reasoning_collapsed)
        if role == "error":
            return ErrorMessage(block.content)
        if role == "system":
            return SystemMessage(block.content)
        if role == "result":
            return ResultBlock(
                collapsed=bool(block.metadata.get("collapsed", False)),
                markup=bool(block.metadata.get("markup", False)),
            )
        return AssistantBlock()

    def _ensure_widget(self, block: TuiBlock) -> Any:
        widget = self._widgets.get(block.id)
        if widget is None:
            widget = self._create_widget(block)
            self._widgets[block.id] = widget
            # 新块总是最新的：插到底部占位之前（即窗口末尾）
            self._messages_widget().mount(widget, before=self._spacer_bottom)
            self._win_ids.append(block.id)
            self._message_widgets.append(widget)
        return widget

    # ------------------------------------------------------------------ 窗口化渲染

    def _welcome_widget(self) -> Any:
        try:
            return self.query_one("#welcome", Static)
        except Exception:  # noqa: BLE001 还没挂上
            return None

    def _request_window_update(self) -> None:
        """立即重算窗口（用缓存高度 + 当前滚动位置，可同步执行）"""
        self._window_update()

    def _block_height(self, block_id: int) -> int:
        height = self._win_heights.get(block_id)
        if height is not None:
            return height
        return self._estimate_height(block_id)

    def _estimate_height(self, block_id: int) -> int:
        """未实测高度时的粗略估计（只影响占位高度，很快会被实测值替换）

        只求「够接近」：估得偏大会让窗口算小、视口下方留白；估得偏小只会多挂
        几个块，更安全。折叠的思考 / 工具 / 结果块实际只占 1 行（标题），必须
        按 1 行算，否则历史一长就会严重高估。
        """
        block = self.context.get_block(block_id)
        if block is None:
            return 1
        content = block.get("content") or ""
        if not isinstance(content, str):
            content = _stringify(content)
        width = max(20, self._messages_widget().size.width or 80)
        collapsed = self._is_collapsed(block)
        key = (len(content), width, collapsed)
        cached = self._est_cache.get(block_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        lines = _visual_lines(content, width)
        if block.get("role") in ("reasoning", "tool", "result"):
            # Collapsible：折叠时只有标题一行；展开时标题 + 内容
            height = 1 if collapsed else 1 + lines
        else:
            height = lines
        self._est_cache[block_id] = (key, height)
        self._tops_cache = None  # 估算高度变了，前缀和缓存失效
        return height

    def _is_collapsed(self, block: Any) -> bool:
        """该块当前是否折叠（折叠的 Collapsible 只占一行）"""
        widget = self._widgets.get(block.get("id"))
        if widget is not None and hasattr(widget, "collapsed"):
            return bool(widget.collapsed)
        role = block.get("role")
        if role == "result":
            return bool(block.get("metadata", {}).get("collapsed", False))
        if role in ("reasoning", "tool"):
            return self.reasoning_collapsed
        return False

    def _record_win_heights(self) -> None:
        """记录窗口里各 widget 的实测高度（缓存后不再变化，保证占位高度稳定）"""
        for block_id in self._win_ids:
            widget = self._widgets.get(block_id)
            if widget is None or not widget.is_mounted:
                continue
            height = widget.outer_size.height
            if height > 0 and self._win_heights.get(block_id) != height:
                self._win_heights[block_id] = height
                self._tops_cache = None  # 高度变了，前缀和缓存失效

    def _window_update(self) -> None:
        """只保留视口附近的块挂载，其余卸载并用 spacer 占位（滚回去会重新挂载）

        稳定性关键：窗口增删会改变内容总高度，若直接恢复原来的 `scroll_offset`，
        视口里的内容会整体位移（跳动）。这里改为「锚定视口顶部所在的块 + 块内偏移」：
        窗口变化后把该锚点重新对齐回视口顶部，于是高度变化不会引起跳动。
        另外不再用 `call_after_refresh` 兜底恢复滚动位置——那会在用户已经滚动之后
        才执行，反过来把滚动位置拽回去（偶发跳动 / 抢滚动的根源）。
        """
        if not self.WINDOWED or self._in_window_update:
            return
        self._in_window_update = True
        stick = self._stick
        try:
            self._window_update_inner()
        except Exception as error:  # noqa: BLE001 窗口化失败不应中断界面
            try:
                self.log.error(f"窗口更新失败: {error}")
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._in_window_update = False
            # 窗口变化会改动内容高度、可能触发 watch_scroll_y；不应被当成用户滚动
            self._stick = stick

    def _spacers_ready(self) -> bool:
        """上下占位是否都已挂载（会话切换重建期间可能短暂不可用）"""
        top, bottom = self._spacer_top, self._spacer_bottom
        return (
            top is not None
            and bottom is not None
            and top.is_mounted
            and bottom.is_mounted
        )

    def _window_update_inner(self) -> None:
        if not self._spacers_ready():
            return  # 占位还没挂好，跳过这次窗口维护（等下一拍）
        ids = [block["id"] for block in self.context.get_blocks()]
        welcome = self._welcome_widget()
        if welcome is not None:
            welcome.display = not ids
        if not ids:
            self._set_spacers(0, 0)
            if self._win_ids:
                self._unmount_ids(list(self._win_ids))
                self._win_ids = []
                self._message_widgets = []
            return

        self._record_win_heights()
        scroll = self._messages_widget()
        vh = max(1, scroll.size.height)
        count = len(ids)
        size = self._window_size(count, vh)

        if self._stick:
            # 跟随底部：窗口直接锚定在末尾。不按滚动位置推算——高度估算不准时
            # 推算结果会来回摆动，表现为「不停滚动 / 闪烁」。
            first = max(0, count - size)
            last = count - 1
            anchor_id = None
            anchor_off = 0
        else:
            tops = self._prefix_tops(ids)
            vy = scroll.scroll_offset.y
            first_vis = max(0, min(bisect_right(tops, vy) - 1, count - 1))
            anchor_id = ids[first_vis]
            anchor_off = vy - tops[first_vis]
            first = max(0, first_vis - self.WIN_BUFFER)
            last = min(count - 1, first + size - 1)

        desired = ids[first : last + 1]
        if desired != self._win_ids:
            self._mount_window(desired)
            self._record_win_heights()  # 新挂载的块量到真实高度

        tops = self._prefix_tops(ids)
        self._set_spacers(tops[first], tops[-1] - tops[last + 1])
        if self._stick:
            # 同步设置 scroll_y。不能用 scroll_end()——它会 call_after_refresh
            # 一个延迟的「滚到底」，可能在用户已经滚动之后才执行，把视口拽回去。
            self._scroll_to_bottom(scroll)
            return
        index_of = {block_id: i for i, block_id in enumerate(ids)}
        target = tops[index_of[anchor_id]] + anchor_off
        if abs(scroll.scroll_offset.y - target) >= 0.5:
            scroll.scroll_to(y=target, animate=False)

    def _window_size(self, count: int, vh: int) -> int:
        """窗口要挂多少块

        下限用「视口行数」兜底：每个块至少占 1 行，所以挂够 `vh` 个块一定能
        盖住视口。高度估算偏大时 `last_vis` 会偏小，只靠它算窗口会在视口下方
        留出未挂载的空白——这一条就是防那个的。
        """
        return max(1, min(count, self.WIN_MAX, max(self.WIN_MIN, vh + self.WIN_BUFFER)))

    @staticmethod
    def _scroll_to_bottom(scroll: Any) -> None:
        """同步滚到底部（不走 scroll_end 的延迟回调）"""
        try:
            end = scroll.max_scroll_y
            if abs(scroll.scroll_offset.y - end) >= 0.5:
                scroll.scroll_y = end
        except Exception:  # noqa: BLE001 未挂载/未布局时忽略
            pass

    def _prefix_tops(self, ids: list[int]) -> list[int]:
        """累计高度前缀和，`tops[i]` 为第 i 个块顶部的 y 坐标（长度 len(ids)+1）

        超长会话下每次窗口维护都要重算，故缓存；块列表或任一高度变化时失效。
        """
        cache = self._tops_cache
        if cache is not None and cache[0] == ids:
            return cache[1]
        tops = [0]
        for block_id in ids:
            tops.append(tops[-1] + self._block_height(block_id))
        self._tops_cache = (ids, tops)
        return tops

    def _set_spacers(self, top: int, bottom: int) -> None:
        if self._spacer_top is not None and self._spacer_top.is_mounted:
            self._spacer_top.styles.height = max(0, top)
        if self._spacer_bottom is not None and self._spacer_bottom.is_mounted:
            self._spacer_bottom.styles.height = max(0, bottom)

    def _unmount_ids(self, block_ids: list[int]) -> None:
        for block_id in block_ids:
            widget = self._widgets.pop(block_id, None)
            if widget is None:
                continue
            widget.remove()
            if widget in self._message_widgets:
                self._message_widgets.remove(widget)

    def _mount_window(self, desired: list[int]) -> None:
        """把窗口调整成 desired：卸载窗口外的，挂载窗口内的（保持顺序）"""
        want = set(desired)
        self._unmount_ids([i for i in self._win_ids if i not in want])
        prev = self._spacer_top if self._spacers_ready() else None
        for block_id in desired:
            widget = self._widgets.get(block_id)
            if widget is None:
                block = self.context.get_block(block_id)
                if block is None:
                    continue
                widget = self._create_widget(block)
                self._widgets[block_id] = widget
                self._mount_widget(widget, prev)
                # 挂载是异步的，内容交给渲染泵补（挂载完成后再写，避免 Markdown 未挂载就更新）
                self._dirty[block_id] = block
            elif not widget.is_mounted:
                self._mount_widget(widget, prev)
                block = self.context.get_block(block_id)
                if block is not None:
                    self._dirty[block_id] = block
            prev = widget
        self._win_ids = list(desired)
        self._message_widgets = [
            self._widgets[i] for i in self._win_ids if i in self._widgets
        ]

    def _mount_widget(self, widget: Any, prev: Any) -> None:
        """把 widget 挂到消息区：prev 还在 DOM 里就插其后，否则直接追加

        注意**不能**用 ``prev.is_mounted`` 判断：``mount()`` 虽然同步插入 DOM，
        但 ``is_mounted`` 要等挂载事件处理完才为 True。刚挂上的块这一拍
        ``is_mounted`` 仍是 False，于是后面的块全部退化成「追加到末尾」（跑到
        spacer_bottom 之后），顺序彻底错乱——表现就是滚动时出现大块空白。
        """
        messages = self._messages_widget()
        if prev is not None and prev in messages.children:
            messages.mount(widget, after=prev)
        else:
            messages.mount(widget)

    def _render_markdown(self, widget: Markdown, content: str) -> Any:
        """增量渲染助手 Markdown：只解析新增片段，避免整篇重解析。

        `Markdown.update()` 每次都会整篇重解析并重建所有子块，流式输出时呈
        O(n²) 开销，正文越长越卡。挂载完成后改用 `append()`，只解析新增片段，
        开销与新增内容成正比。

        注意：`_initial_markdown` 要始终保持为最新内容，供 `Markdown._on_mount`
        首次渲染使用，避免挂载时用空串覆盖已写入的内容。
        """
        widget._initial_markdown = content
        current = widget.source
        if content == current:
            return None  # 内容未变化，跳过昂贵的 Markdown 解析
        if not widget.is_mounted:
            # 还没挂载：_initial_markdown 已更新，挂载时由 _on_mount 首次渲染
            return None
        if content.startswith(current):
            # 纯追加：append() 只解析新增部分
            return widget.append(content[len(current):])
        # 内容被替换/回退：整篇刷新一次
        return widget.update(content)

    def _apply_block(self, block: TuiBlock) -> Any:
        """把块更新到组件；Markdown 为异步渲染，返回可等待对象"""
        widget = self._ensure_widget(block)
        if isinstance(widget, AssistantBlock):
            awaitable = self._render_markdown(widget.markdown, block.content)
            # 单次请求的耗时/tok/tps：只在轮次进行中实时显示；
            # 轮次结束后由 _run_turn 用整轮统计覆盖（避免被单次请求盖回去）
            if block.timing and self._busy:
                self._set_last_stats(_format_timing(block.timing))
            return awaitable
        if isinstance(widget, Markdown):
            return self._render_markdown(widget, block.content)
        if isinstance(widget, (ReasoningBlock, ToolBlock, ResultBlock)):
            widget.set_block(block)
        elif block.role in ("user", "error", "system"):
            pass
        else:
            widget.update(block.content)
        return None

    def _set_last_stats(self, text: str) -> None:
        """更新底部「最近一条消息」的耗时/tok/tps"""
        self._last_stats_text = text
        label = self._last_stats
        if label is None:
            return
        label.update(text)

    def _format_turn_stats(
        self, duration: float, tokens: int, gen: float, has_tokens: bool
    ) -> str:
        """整轮（turn）统计：耗时 + 跨多次 LLM 请求累加的生成 token 与 tps

        `duration` 是整轮墙钟耗时（含工具执行）；`tokens`/`gen` 是本轮所有 LLM
        请求的 completion token 与生成窗口之和，故 tps 是「本轮平均生成速度」。
        """
        return _format_timing(
            {
                "duration": round(duration, 2),
                "tokens": tokens if has_tokens else None,
                "tps": (
                    round(tokens / gen, 2) if has_tokens and gen > 0 else None
                ),
            }
        )

    def _should_render(self, block_id: int, length: int = 0) -> bool:
        """流式节流：增量 append 足够便宜，仅轻微随长度放宽间隔"""
        now = time.monotonic()
        interval = min(
            self.RENDER_INTERVAL_MAX, self.RENDER_INTERVAL + length / 100000
        )
        last = self._last_render.get(block_id, 0.0)
        if now - last >= interval:
            self._last_render[block_id] = now
            return True
        return False

    def _mark_dirty(self, block: TuiBlock | None, turn: bool = False) -> None:
        if block is None:
            return
        self._dirty[block.id] = block
        if turn:
            self._turn_refs[block.id] = block

    async def _render_pump(self) -> None:
        """定时渲染：界面工作量只与时间有关，与 chunk 速率无关"""
        # 窗口维护（量高度 + 按视口重算窗口）放在泵里做，避免额外的刷新回调
        self._record_win_heights()
        self._window_update()
        if self._stick and self._messages is not None:
            # 跟随底部时每拍确认一次：内容刚变过时 max_scroll_y 还是旧值，等布局
            # 算完这一拍会把它补上（同步设置，不产生会在用户滚动后才执行的延迟回调）
            self._scroll_to_bottom(self._messages)
        if not self._dirty:
            return
        self.context.commit()
        rendered = False
        for block in list(self._dirty.values()):
            if block.is_streaming and not self._should_render(
                block.id, len(block.content)
            ):
                continue  # 仍在节流窗口内，保留脏标记，下个 tick 再试
            pending = self._apply_block(block)
            if pending is not None:
                await pending
            self._dirty.pop(block.id, None)
            rendered = True
        if rendered:
            self._request_scroll()
            self._request_sticky_update()
            self._request_window_update()

    def _request_scroll(self) -> None:
        """合并滚动请求：同一时刻最多挂一个回调"""
        if not self._stick or self._scroll_pending:
            return
        self._scroll_pending = True
        self.call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        self._scroll_pending = False
        # 同步设置 scroll_y，避免 scroll_end 的延迟回调在用户滚动之后才执行
        if self._stick and self._messages is not None:
            self._scroll_to_bottom(self._messages)

    def _request_sticky_update(self) -> None:
        """合并吸顶标题更新请求：布局刷新后统一计算一次"""
        if self._sticky_pending:
            return
        self._sticky_pending = True
        self.call_after_refresh(self._do_sticky_update)

    def _do_sticky_update(self) -> None:
        """找出跨越消息区顶部边缘的折叠块并吸顶显示其标题"""
        self._sticky_pending = False
        sticky = self._sticky
        if sticky is None:
            return
        try:
            top = self._messages_widget().content_region.y
        except Exception:
            return

        target = None
        for widget in self._message_widgets:
            if not isinstance(widget, (ReasoningBlock, ToolBlock, ResultBlock)):
                continue
            if not widget.display:
                continue
            region = widget.region
            if region.height <= 0 or region.y + region.height <= top:
                continue  # 完全在视口上方
            if region.y < top and not widget.collapsed:
                target = widget  # 该块的标题已被滚出视口
            break  # 后续块都在更下方，无需再看

        if target is self._sticky_target:
            if target is None:
                sticky.display = False
            elif sticky.display is False:
                sticky.display = True
            return

        self._sticky_target = target
        if target is None:
            sticky.display = False
            return
        title = _one_line(target.title) or "内容"
        sticky.update(f"▼ {_escape_markup(title)}  [dim]点击折叠[/]")
        sticky.display = True

    def _toggle_sticky_header(self) -> None:
        target = self._sticky_target
        if target is None:
            return
        target.collapsed = not target.collapsed
        self._sticky_target = None
        self._request_sticky_update()

    def _sync_block(self, block: TuiBlock) -> None:
        """同步更新（命令结果等 Static/Collapsible 块）"""
        self._apply_block(block)
        self._dirty.pop(block.id, None)
        self._request_scroll()
        self._request_sticky_update()

    async def _sync_block_async(self, block: TuiBlock) -> None:
        """异步更新（助手 Markdown 流式），渲染完成后再跟随滚动"""
        pending = self._apply_block(block)
        if pending is not None:
            await pending
        self._dirty.pop(block.id, None)
        self._request_scroll()
        self._request_sticky_update()

    def _update_stick(self, scroll: "MessageScroll") -> None:
        """根据滚动位置更新粘性：在底部则跟随输出，否则保持用户浏览位置"""
        self._stick = scroll.is_vertical_scroll_end

    def _is_at_bottom(self) -> bool:
        messages = self._messages_widget()
        try:
            return messages.is_vertical_scroll_end
        except Exception:
            return messages.scroll_offset.y >= messages.max_scroll_y - 1

    def _start_loading(self) -> None:
        if self._loading is not None:
            self._loading.display = True

    def _stop_loading(self) -> None:
        if self._loading is not None:
            self._loading.display = False

    def _refresh_status(self) -> None:
        state = getattr(self.agent, "state", None)
        name = getattr(state, "name", None) or str(state)
        mapping = {
            "IDLE": "就绪",
            "THINKING": "思考中…",
            "RESPONDING": "回复中…",
            "TOOL_CALLING": "调用工具中…",
            "ON_TOOL_CONFIRM": "等待工具确认…",
            "ERROR": "出错",
        }
        self._set_status(mapping.get(name, name))

    def _set_status(self, text: str) -> None:
        if text == self._last_status:
            return
        self._last_status = text
        if self._status_text is not None:
            self._status_text.update(text)

    def _refresh_tokens(self) -> None:
        counter = self.counter
        bar = self._token_bar
        label = self._token_label
        if bar is None or label is None:
            return

        if counter.max_tokens:
            bar.display = True
            bar.update(total=counter.max_tokens, progress=counter.total_tokens)
            text = f"{counter.total_tokens}/{counter.max_tokens} ({counter.ratio:.1%})"
        else:
            bar.display = False
            text = f"{counter.total_tokens} tokens"

        # 上下文越长、命中率越高（前缀被服务端缓存），直接决定实际费用。
        # 用两位小数：99.97% 若只保留一位会显示成 100.0%，容易误导
        rate = counter.cache_hit_rate
        if rate is not None:
            text += f" · 缓存 {rate:.2%}"
        label.update(text)

        if counter.is_exceeded:
            bar.add_class("exceeded")
            label.add_class("exceeded")
            label.remove_class("warning")
        elif counter.ratio >= 0.8:
            bar.remove_class("exceeded")
            label.remove_class("exceeded")
            label.add_class("warning")
        else:
            bar.remove_class("exceeded")
            label.remove_class("exceeded")
            label.remove_class("warning")

    # ------------------------------------------------------------------ 快捷键动作

    def action_jump_next(self) -> None:
        self._jump(1)

    def action_jump_prev(self) -> None:
        self._jump(-1)

    def action_jump_first(self) -> None:
        if self._message_widgets:
            self._jump_index = 0
            self._highlight_current()

    def action_jump_last(self) -> None:
        if self._message_widgets:
            self._jump_index = len(self._message_widgets) - 1
            self._highlight_current()

    def _jump(self, step: int) -> None:
        if not self._message_widgets:
            return
        if self._jump_index < 0:
            self._jump_index = len(self._message_widgets) - 1 if step < 0 else 0
        else:
            self._jump_index = max(
                0, min(self._jump_index + step, len(self._message_widgets) - 1)
            )
        self._highlight_current()

    def _highlight_current(self) -> None:
        for widget in self._message_widgets:
            widget.remove_class("jump-highlight")
        widget = self._message_widgets[self._jump_index]
        widget.add_class("jump-highlight")
        widget.scroll_visible(animate=True)
        self.set_timer(1.2, lambda: widget.remove_class("jump-highlight"))

    def action_toggle_reasoning(self) -> None:
        self._toggle_collapsibles(ReasoningBlock)

    def action_toggle_tools(self) -> None:
        self._toggle_collapsibles((ToolBlock, ResultBlock))

    def _toggle_collapsibles(self, widget_types: type | tuple) -> None:
        if not isinstance(widget_types, tuple):
            widget_types = (widget_types,)
        collapsibles = [
            w for w in self._message_widgets if isinstance(w, widget_types)
        ]
        if not collapsibles:
            return
        should_collapse = any(not w.collapsed for w in collapsibles)
        for widget in collapsibles:
            widget.collapsed = should_collapse
        self._request_sticky_update()

    async def action_clear_view(self) -> None:
        self.context.clear()
        self.counter.reset()
        self._widgets.clear()
        self._message_widgets.clear()
        self._last_render.clear()
        self._dirty.clear()
        self._turn_refs.clear()
        self._jump_index = -1
        await self._clear_messages()
        self._refresh_tokens()
        self._set_status("就绪")


def run_agent_in_tui(
    agent: Agent | MultimodalAgent,
    max_tokens: int | None = None,
    *,
    reasoning_collapsed: bool = True,
    auto_confirm: bool = True,
    unlimited_context: bool = False,
    session_root: str | None = None,
) -> None:
    """在终端启动 tina 界面

    Args:
        agent: tina.Agent / tina.MultimodalAgent 实例
        max_tokens: 用户设置的最大 token 数，用于进度展示与超限警告
        reasoning_collapsed: 推理内容默认是否折叠
        auto_confirm: 是否自动为 Agent 注册工具确认弹窗
        unlimited_context: 是否用 tina 提供的无限制上下文管理器替换 Agent 的
            （不裁剪历史、不截断工具结果，现有历史会保留）
        session_root: 会话归档目录的根（默认用 Agent 的上下文管理器 root，
            都没有则用当前工作目录），会话放在 ``<root>/.tina/chat_sessions/``

    每次启动都是全新对话：只有在发出第一条真正的消息（非 ``#switch`` 等切换
    历史的指令）时才会创建会话文件；想接着上次聊，用 ``#switch`` 切回历史会话。
    """
    app = TinaTUI(
        agent,
        max_tokens=max_tokens,
        reasoning_collapsed=reasoning_collapsed,
        auto_confirm=auto_confirm,
        unlimited_context=unlimited_context,
        session_root=session_root,
    )
    app.run()


__all__ = ["TinaTUI", "run_agent_in_tui"]
