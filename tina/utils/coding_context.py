"""项目感知的编码上下文管理器

在 tina 基础 ``ContextManager`` 之上，构造时自动把「项目上下文」注入系统提示：
项目约定文件（``AGENTS.md`` / ``.tinacode.md`` / ``.tina.md``）、工作目录、项目结构摘要。

用法::

    from tina import Agent
    from tina.utils.coding_context import CodingContextManager
    from tina.utils.coding_tools import CodingTools

    tools = CodingTools(root=".").get_tools()
    agent = Agent(llm=llm, tools=tools)
    agent.set_context_manager(CodingContextManager(root="."))

注意：``Agent(llm=..., context_manager=cm)`` 若不传 ``system_prompt``，Agent 会用默认
提示覆盖 cm 的系统消息。因此推荐构造后再 ``agent.set_context_manager(cm)``（本管理器的
项目上下文得以保留），或显式 ``system_prompt=cm.get_system_message()``。
"""

import os
import platform
import sys

from tina.agent.core.context_manager import MultimodalContextManager
from tina.utils.session_store import (
    DEFAULT_SESSIONS_DIR,
    DEFAULT_WORK_DIR,
    SessionStore,
    ensure_session_dir,
)

# 核心 ContextManager 用数值比较来裁剪，故用超大值表示「不限制」
_NO_LIMIT = sys.maxsize

_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".tox",
    ".eggs",
    "dist",
    "build",
}

_DEFAULT_CONVENTION_FILES = ("AGENTS.md", ".tinacode.md", ".tina.md")

_CODING_SYSTEM_PROMPT = """你是一个专业的编码助手，在一个本地代码仓库中工作。

工作准则：
- 修改前先阅读相关文件（code_read / code_grep / code_glob），不要凭记忆猜代码。
- 局部修改优先用 code_edit，并提供足够的上下文让 old_string 在文件中唯一；整文件重写才用 code_write。
- 改动保持最小、聚焦，不要顺手改动无关代码或排版风格。
- 执行命令用 code_bash；对危险或不可逆的操作，先说明再执行。
- 完成后简要说明改了什么、为什么。"""


class CodingContextManager(MultimodalContextManager):
    """编码上下文管理器

    继承 ``MultimodalContextManager``，因此既能给普通 ``Agent`` 用，也能给
    ``MultimodalAgent`` 用（支持 ``image`` / ``audio`` / ``url`` / ``file_id``）。
    若传入 ``tools``，还会自动把「工具返回的图片/音频」等多媒体结果提交给模型。

    Args:
        root: 项目根目录
        tools: 可选，对应的工具包（用于多模态工具结果识别）
        max_length: 上下文最大字符数；None（默认）表示**不裁剪历史**，避免短视
        max_tool_result_length: 单条工具结果最大字符数；None（默认）表示**不截断**
        convention_files: 需要自动读取并注入的项目约定文件名
        include_tree: 是否注入项目结构摘要
        tree_max_depth: 结构摘要最大深度
        tree_max_lines: 结构摘要最大行数
        system_prompt: 自定义系统提示（默认使用内置编码提示）
        extra_instructions: 追加到系统提示末尾的额外说明
        work_dir: 工作目录名，默认 ``.tina``（会话等状态文件放这里）
        sessions_dir: 会话子目录名，默认 ``chat_sessions``
        create_session_dir: 是否在构造时创建 ``.tina/chat_sessions`` 目录
    """

    def __init__(
        self,
        root: str = ".",
        tools=None,
        max_length: int | None = None,
        max_tool_result_length: int | None = None,
        convention_files=_DEFAULT_CONVENTION_FILES,
        include_tree: bool = True,
        tree_max_depth: int = 2,
        tree_max_lines: int = 200,
        system_prompt: str = None,
        extra_instructions: str = None,
        work_dir: str = DEFAULT_WORK_DIR,
        sessions_dir: str = DEFAULT_SESSIONS_DIR,
        create_session_dir: bool = True,
    ) -> None:
        super().__init__(
            tools=tools,
            max_length=_NO_LIMIT if max_length is None else max_length,
            max_tool_result_length=(
                _NO_LIMIT if max_tool_result_length is None else max_tool_result_length
            ),
        )
        self.root = os.path.abspath(root)
        self.work_dir = work_dir
        self.sessions_dir = sessions_dir
        # 在当前工作目录下建 ``.tina/chat_sessions``，供 TUI 等按会话归档聊天
        self.session_dir = (
            ensure_session_dir(self.root, work_dir, sessions_dir)
            if create_session_dir
            else os.path.join(self.root, work_dir, sessions_dir)
        )
        self._session_store: SessionStore | None = None
        self._convention_files = tuple(convention_files)
        self._include_tree = include_tree
        self._tree_max_depth = tree_max_depth
        self._tree_max_lines = tree_max_lines
        self._system_prompt = system_prompt or _CODING_SYSTEM_PROMPT
        self._extra_instructions = extra_instructions
        self.set_system_message(self._build_system_message())

    def add_user_message(
        self,
        instruction: str = None,
        image=None,
        audio=None,
        url=None,
        file_id=None,
    ):
        """文本消息用最朴素的字符串形式；带多媒体时走多模态格式"""
        if any(v is not None for v in (image, audio, url, file_id)):
            return super().add_user_message(
                instruction=instruction,
                image=image,
                audio=audio,
                url=url,
                file_id=file_id,
            )
        if instruction is not None:
            self.messages.append({"role": "user", "content": instruction})
            self.limit_messages()
        return self.messages

    def _extract_multimodal_result(self, item):
        # 未提供 tools 时退化为普通文本工具结果，避免 AttributeError
        if self.tools is None:
            return None
        return super()._extract_multimodal_result(item)

    def refresh_project_context(self) -> str:
        """重新读取项目上下文并刷新系统提示（如 AGENTS.md 变了）"""
        self.set_system_message(self._build_system_message())
        return self.get_system_message()

    @property
    def session_store(self) -> SessionStore:
        """本项目对应的会话仓库（惰性创建，指向 ``.tina/chat_sessions``）"""
        if self._session_store is None:
            self._session_store = SessionStore(
                root=self.root,
                work_dir=self.work_dir,
                sessions_dir=self.sessions_dir,
            )
        return self._session_store

    # ------------------------------------------------------------------ 内部

    def _build_system_message(self) -> str:
        parts = [self._system_prompt]
        context = self._project_context()
        if context:
            parts.append(context)
        if self._extra_instructions:
            parts.append(self._extra_instructions)
        return "\n\n".join(parts)

    def _project_context(self) -> str:
        lines = [
            "# 项目上下文",
            f"- 工作目录: {self.root}",
            f"- 操作系统: {platform.system()}",
        ]

        for name in self._convention_files:
            path = os.path.join(self.root, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    text = f.read().strip()
            except (UnicodeDecodeError, OSError):
                continue
            if text:
                lines.append(f"\n## 项目约定（{name}）\n{text}")

        if self._include_tree:
            tree = self._project_tree()
            if tree:
                lines.append(f"\n## 项目结构（部分）\n```\n{tree}\n```")

        return "\n".join(lines)

    def _project_tree(self) -> str:
        lines: list[str] = []
        truncated = False

        def walk(directory: str, depth: int) -> None:
            nonlocal truncated
            if depth >= self._tree_max_depth or len(lines) >= self._tree_max_lines:
                truncated = truncated or len(lines) >= self._tree_max_lines
                return
            try:
                entries = sorted(os.listdir(directory))
            except OSError:
                return
            dirs = [
                name
                for name in entries
                if name not in _IGNORE_DIRS
                and os.path.isdir(os.path.join(directory, name))
            ]
            files = [
                name
                for name in entries
                if os.path.isfile(os.path.join(directory, name))
            ]
            indent = "  " * (depth + 1)
            for name in dirs:
                lines.append(f"{indent}{name}/")
                if len(lines) >= self._tree_max_lines:
                    truncated = True
                    return
                walk(os.path.join(directory, name), depth + 1)
            for name in files:
                lines.append(f"{indent}{name}")
                if len(lines) >= self._tree_max_lines:
                    truncated = True
                    return

        walk(self.root, 0)
        if truncated:
            lines.append("...（已截断）")
        return "\n".join(lines)
