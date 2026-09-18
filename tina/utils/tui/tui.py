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
import time
from typing import TYPE_CHECKING, Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.message import Message
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (
    Collapsible,
    Footer,
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

from ...agent.core.state import AgentState
from .context_manager import (
    TuiBlock,
    TuiMessageStore,
    make_unlimited_context_manager,
)
from .token import TokenCounter

if TYPE_CHECKING:
    from ...agent import Agent, BaseContextManager, MultimodalAgent


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
        super().__init__(f"[bold #e0a45e]❯[/] {escape(content)}", **kwargs)
        self.add_class("user-message")


class ErrorMessage(Static):
    """错误消息块"""

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(f"[bold red]✗[/] {escape(content)}", markup=True, **kwargs)
        self.add_class("error-message")


class SystemMessage(Static):
    """系统 / 提示消息块"""

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(escape(content), markup=True, **kwargs)
        self.add_class("system-message")


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
        await super()._on_key(event)


class ReasoningBlock(Collapsible):
    """推理内容块，可折叠"""

    def __init__(self, collapsed: bool = True, **kwargs: Any) -> None:
        self._text = Static("", classes="reasoning-text", markup=False)
        super().__init__(self._text, title="思考", collapsed=collapsed, **kwargs)
        self.add_class("reasoning-block")

    def set_block(self, block: TuiBlock) -> None:
        self._text.update(block.content)
        self.title = "思考中…" if block.is_streaming else "思考过程"


class MessageScroll(VerticalScroll):
    """消息滚动区：把滚动位置变化通知 App，用于粘性到底判断"""

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        try:
            app = self.app
        except Exception:
            return
        updater = getattr(app, "_update_stick", None)
        if updater is not None:
            updater(self)


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
        self.title = f"{name} · {status}"

        args = _stringify(block.tool_arguments).strip()
        self._args.update(f"参数：{args}" if args else "参数：-")

        result = _stringify(block.tool_result).strip()
        self._result.update(f"结果：\n{result}" if result else "结果：等待中…")


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
            yield Static(f"工具参数 · {escape(self._tool_name)}", id="args-title")
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
        height: 2;
        padding: 0 2;
        color: $accent;
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
        "#tools": "查看当前工具、描述与参数",
        "#context": "查看当前上下文",
        "#model": "查看当前模型信息",
        "#tokens": "查看 token 统计",
        "#compact": "压缩上下文（总结并写入 system）",
        "#clear": "清空上下文与界面",
        "#exit": "退出",
    }

    COMPACT_INSTRUCTION = (
        "请你根据你过去的历史，总结你接下来需要用的信息，"
        "我们将会使用这个信息作为新的开始。"
    )

    # 关闭 Textual 自带的命令面板（默认 ctrl+p），tina 用自己的 # 命令
    ENABLE_COMMAND_PALETTE = False

    # 渲染泵间隔：界面更新与滚动统一在这里做，与 chunk 速率解耦
    PUMP_INTERVAL = 0.1
    # 流式块重渲染的最小间隔（秒），内容越长间隔越大，避免 O(n²) 重解析
    RENDER_INTERVAL = 0.08
    RENDER_INTERVAL_MAX = 0.5

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
    ) -> None:
        super().__init__()
        self.agent: Agent | MultimodalAgent = agent
        self.context = TuiMessageStore()
        self.counter = TokenCounter(max_tokens=max_tokens)
        self.reasoning_collapsed = reasoning_collapsed
        self.auto_confirm = auto_confirm
        if unlimited_context:
            self.install_context_manager(make_unlimited_context_manager(agent))

        self._widgets: dict[int, Any] = {}
        self._message_widgets: list[Any] = []
        self._jump_index = -1
        self._busy = False
        self._confirm_future: asyncio.Future | None = None
        self._confirm_lock: asyncio.Lock | None = None
        self._pending_confirms = 0
        self._pending_tool: str | None = None
        self._pending_tool_args: str | None = None
        self._always_allow: set[str] = set()
        self._completion_matches: list[str] = []
        self._completion_index = 0
        self._last_render: dict[int, float] = {}
        self._stick = True

        # 渲染泵状态
        self._dirty: dict[int, TuiBlock] = {}
        self._turn_refs: dict[int, TuiBlock] = {}
        self._scroll_pending = False
        self._last_status: str | None = None

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
            placeholder="输入消息，Enter 发送，Shift+Enter 换行；#help / Tab 补全",
            id="prompt",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._apply_theme()
        self.title = "tina"
        self.sub_title = getattr(self.agent, "name", "") or ""
        self._messages = self.query_one("#messages", MessageScroll)
        self._status_text = self.query_one("#status-text", Label)
        self._token_label = self.query_one("#token-text", Label)
        self._token_bar = self.query_one("#token-bar", ProgressBar)
        self._loading = self.query_one("#loading", LoadingIndicator)
        self._loading.display = False
        self._render_welcome()
        self._refresh_tokens()
        self.query_one("#command-hint", Static).display = False
        self.query_one("#confirm-bar", Vertical).display = False
        self.query_one("#prompt", ChatInput).focus()
        self.set_interval(self.PUMP_INTERVAL, self._render_pump)

    def _apply_theme(self) -> None:
        try:
            self.register_theme(TINA_THEME)
            self.theme = TINA_THEME.name
        except Exception:
            pass

    def install_context_manager(self, context_manager: BaseContextManager) -> None:
        """替换 Agent 的上下文管理器（委托 `agent.set_context_manager`）

        注意：替换会立即生效，但只有传入的实例里已有的消息会被使用；想保留
        当前历史，用 `tina.utils.tui.make_unlimited_context_manager(agent)`。
        """
        self.agent.set_context_manager(context_manager)

    def _render_welcome(self) -> None:
        model = escape(getattr(getattr(self.agent, "llm", None), "model", "") or "")
        name = escape(getattr(self.agent, "name", "") or "tina")
        lines = [
            f"[bold #e0a45e]tina[/] [#7aa2f7]terminal[/]  [dim]{name}[/]",
        ]
        if model:
            lines.append(f"[dim]model  {model}[/]")
        lines.append(
            "[dim]Ctrl+↑/↓ 跳转消息 · Ctrl+R 折叠思考 · Ctrl+T 折叠工具 · 输入 # 查看命令[/]"
        )
        self._messages_widget().mount(Static("\n".join(lines), id="welcome"))

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

        header = f"允许执行工具 [b]{escape(tool_name)}[/] 吗？"
        if not args:
            text = header
        elif (
            len(args) <= self.CONFIRM_INLINE_ARGS
            and args.count("\n") < self.CONFIRM_INLINE_LINES
        ):
            text = f"{header}\n[dim]{escape(args)}[/]"
        else:
            # 参数过长时不内联显示，避免把下面的选项挤出可视区
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
        """Escape：参数窗口/确认框在则关闭，否则打断本轮回复"""
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
        if text.startswith("#"):
            await self._handle_command(text)
            return
        if self._busy:
            self.notify("正在回复中，Esc 可打断，请稍候…", severity="warning")
            return
        self._turn_worker = self._run_turn(text)

    async def _handle_command(self, command: str) -> None:
        cmd = command.strip().lower()
        if cmd in ("#exit", "#quit"):
            self.exit()
        elif cmd in ("#help", "#?", "#h"):
            self._show_help()
        elif cmd == "#tools":
            self._show_tools()
        elif cmd == "#model":
            self._show_model()
        elif cmd == "#tokens":
            self._show_tokens()
        elif cmd == "#clear":
            await self.action_clear_view()
            self._result("提示", "已清空上下文与界面")
        elif cmd == "#context":
            self._show_context()
        elif cmd in ("#compact", "#compress", "#summary"):
            if self._busy:
                self.notify("正在回复中，Esc 可打断，请稍候…", severity="warning")
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
            f"{name:<9} {desc}" for name, desc in self.TUI_COMMANDS.items()
        ]
        self._result("可用命令", "\n".join(lines))

    def _show_context(self) -> None:
        self.context.commit()
        blocks = self.context.get_blocks()
        lines = [f"{b.role}: {len(b.content)} 字" for b in blocks] or ["（空）"]
        self._result("当前上下文", "\n".join(lines))

    def _show_tools(self) -> None:
        tools = getattr(self.agent, "tools", None)
        if tools is None:
            self._result("工具", "当前 Agent 没有工具")
            return
        try:
            schemas = tools.get_tools_for_llm()
        except Exception as error:  # noqa: BLE001
            self._result("工具", f"读取工具失败：{error}")
            return
        if not schemas:
            self._result("工具", "（无工具）")
            return

        blocks: list[str] = []
        for index, schema in enumerate(schemas, 1):
            function = schema.get("function", {})
            name = function.get("name", "?")
            description = _one_line(function.get("description"))
            params = function.get("parameters", {}) or {}
            properties = params.get("properties", {}) or {}
            required = set(params.get("required", []) or [])

            blocks.append(f"{index}. [bold #7aa2f7]{escape(name)}[/]")
            if description:
                blocks.append(f"   [dim]{escape(_shorten(description))}[/]")

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
                        f"     [#7dcfff]{escape(str(p_name)):<{name_width}}[/]  "
                        f"[dim]{escape(param_type):<{type_width}}[/]  {flag}"
                    )
                    if p_desc:
                        line += f"  {escape(_shorten(p_desc, 80))}"
                    blocks.append(line.rstrip())
            blocks.append("")

        self._result(
            f"工具（{len(schemas)}）", "\n".join(blocks).rstrip(), markup=True
        )

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
        self._result("Token 统计", "\n".join(lines))

    def _update_command_hint(self, value: str) -> None:
        hint = self.query_one("#command-hint", Static)
        text = value.strip().lower()
        if not text.startswith("#"):
            hint.display = False
            return
        matches = [c for c in self.TUI_COMMANDS if c.startswith(text)]
        if not matches:
            hint.display = False
            return
        hint.update("  ".join(f"{c} {self.TUI_COMMANDS[c]}" for c in matches))
        hint.display = True

    def _hide_command_hint(self) -> None:
        self.query_one("#command-hint", Static).display = False

    def complete_command(self, input_widget: ChatInput) -> None:
        """Tab 补全：把当前 # 前缀补成命令，多候选时循环"""
        text = input_widget.text.strip().lower()
        if not text.startswith("#"):
            self._completion_matches = []
            return

        if self._completion_matches and text in self._completion_matches:
            self._completion_index = (self._completion_index + 1) % len(
                self._completion_matches
            )
            matches = self._completion_matches
        else:
            matches = [c for c in self.TUI_COMMANDS if c.startswith(text)]
            if not matches:
                self._completion_matches = []
                return
            self._completion_matches = matches
            self._completion_index = 0

        value = matches[self._completion_index]
        input_widget.text = value
        input_widget.move_cursor((0, len(value)))
        self._update_command_hint(value)

    # ------------------------------------------------------------------ 推理

    @work(exclusive=True)
    async def _run_turn(self, instruction: str) -> None:
        self._busy = True
        self._interrupted = False
        self._active_assistant = None
        self._turn_refs.clear()
        self._dirty.clear()
        self._start_loading()
        self._set_status("思考中…")

        user_block = self.context.add_user(instruction)
        self._mark_dirty(user_block, turn=True)

        try:
            async for chunk in self.agent.apredict(instruction=instruction):
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

    async def _reset_view(self) -> None:
        self.context.clear()
        self._widgets.clear()
        self._message_widgets.clear()
        self._last_render.clear()
        self._dirty.clear()
        self._turn_refs.clear()
        self._jump_index = -1
        await self._messages_widget().remove_children()
        self._render_welcome()

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
        return Markdown("", classes="assistant-message")

    def _ensure_widget(self, block: TuiBlock) -> Any:
        widget = self._widgets.get(block.id)
        if widget is None:
            widget = self._create_widget(block)
            self._widgets[block.id] = widget
            self._message_widgets.append(widget)
            self._messages_widget().mount(widget)
        return widget

    def _apply_block(self, block: TuiBlock) -> Any:
        """把块更新到组件；Markdown 为异步渲染，返回可等待对象"""
        widget = self._ensure_widget(block)
        if isinstance(widget, Markdown):
            # Markdown.update() 异步全量重解析，必须在渲染泵里按节流调用。
            # Textual 挂载时会用 _initial_markdown 再渲染一次，这里同步成最新内容，
            # 避免它用空串覆盖已流式写入的内容。
            widget._initial_markdown = block.content
            return widget.update(block.content)
        if isinstance(widget, (ReasoningBlock, ToolBlock, ResultBlock)):
            widget.set_block(block)
        elif block.role in ("user", "error", "system"):
            pass
        else:
            widget.update(block.content)
        return None

    def _should_render(self, block_id: int, length: int = 0) -> bool:
        """流式节流：内容越长间隔越大，避免反复全量重解析"""
        now = time.monotonic()
        interval = min(
            self.RENDER_INTERVAL_MAX, self.RENDER_INTERVAL + length / 20000
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

    def _request_scroll(self) -> None:
        """合并滚动请求：同一时刻最多挂一个回调"""
        if not self._stick or self._scroll_pending:
            return
        self._scroll_pending = True
        self.call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        self._scroll_pending = False
        if self._stick and self._messages is not None:
            self._messages.scroll_end(animate=False)

    def _sync_block(self, block: TuiBlock) -> None:
        """同步更新（命令结果等 Static/Collapsible 块）"""
        self._apply_block(block)
        self._dirty.pop(block.id, None)
        self._request_scroll()

    async def _sync_block_async(self, block: TuiBlock) -> None:
        """异步更新（助手 Markdown 流式），渲染完成后再跟随滚动"""
        pending = self._apply_block(block)
        if pending is not None:
            await pending
        self._dirty.pop(block.id, None)
        self._request_scroll()

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
            label.update(
                f"{counter.total_tokens}/{counter.max_tokens} ({counter.ratio:.1%})"
            )
        else:
            bar.display = False
            label.update(f"{counter.total_tokens} tokens")

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

    async def action_clear_view(self) -> None:
        self.context.clear()
        self.counter.reset()
        self._widgets.clear()
        self._message_widgets.clear()
        self._last_render.clear()
        self._dirty.clear()
        self._turn_refs.clear()
        self._jump_index = -1
        await self._messages_widget().remove_children()
        self._render_welcome()
        self._refresh_tokens()
        self._set_status("就绪")


def run_agent_in_tui(
    agent: Agent | MultimodalAgent,
    max_tokens: int | None = None,
    *,
    reasoning_collapsed: bool = True,
    auto_confirm: bool = True,
    unlimited_context: bool = False,
) -> None:
    """在终端启动 tina 界面

    Args:
        agent: tina.Agent / tina.MultimodalAgent 实例
        max_tokens: 用户设置的最大 token 数，用于进度展示与超限警告
        reasoning_collapsed: 推理内容默认是否折叠
        auto_confirm: 是否自动为 Agent 注册工具确认弹窗
        unlimited_context: 是否用 tina 提供的无限制上下文管理器替换 Agent 的
            （不裁剪历史、不截断工具结果，现有历史会保留）
    """
    app = TinaTUI(
        agent,
        max_tokens=max_tokens,
        reasoning_collapsed=reasoning_collapsed,
        auto_confirm=auto_confirm,
        unlimited_context=unlimited_context,
    )
    app.run()


__all__ = ["TinaTUI", "run_agent_in_tui"]
