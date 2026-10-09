"""会话持久化：把不同聊天归档到 ``<root>/.tina/chat_sessions/``

每个会话是一个 JSON 文件，保存标题（自动生成或用户自定义）与模型消息历史，
TUI 用它实现「切换不同聊天 / 自定义命名 / 会话名自动补全」。

目录结构::

    <root>/.tina/
        chat_sessions/
            20250101-120000-ab12.json    # 单个会话：元数据 + 消息

会话文件格式::

    {
      "id": "20250101-120000-ab12",
      "title": "重构登录模块",
      "title_auto": false,
      "created_at": 1735689600.0,
      "updated_at": 1735689600.0,
      "messages": [{"role": "user", "content": "..."}]
    }

用法::

    from tina.utils.session_store import SessionStore

    store = SessionStore(root=".")
    sid = store.create(messages=agent.context_manager.get_messages())
    store.rename(sid, "重构登录模块")
    for meta in store.list_sessions():
        print(meta.id, meta.display_title)
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Any

DEFAULT_WORK_DIR = ".tina"
DEFAULT_SESSIONS_DIR = "chat_sessions"
SESSION_SUFFIX = ".json"
MAX_TITLE_LENGTH = 80


def ensure_session_dir(
    root: str = ".",
    work_dir: str = DEFAULT_WORK_DIR,
    sessions_dir: str = DEFAULT_SESSIONS_DIR,
) -> str:
    """确保 ``<root>/<work_dir>/<sessions_dir>`` 存在，返回其绝对路径"""
    path = os.path.join(os.path.abspath(root), work_dir, sessions_dir)
    os.makedirs(path, exist_ok=True)
    return path


def clean_title(title: Any) -> str:
    """把任意文本压成单行标题并按需截断"""
    text = " ".join(str(title or "").split())
    if len(text) > MAX_TITLE_LENGTH:
        text = text[:MAX_TITLE_LENGTH].rstrip() + "…"
    return text


def _write_json(path: str, payload: dict) -> None:
    """先写同行唯一临时文件再替换，避免中断留下半截 JSON / 并发互相踩"""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".session_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass
class SessionMeta:
    """会话摘要信息（列表展示 / 选择 / 补全用）"""

    id: str
    title: str = ""
    title_auto: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    message_count: int = 0
    path: str = ""

    @property
    def display_title(self) -> str:
        """展示用标题，空标题给个占位"""
        return self.title or "（未命名会话）"

    @property
    def is_custom_title(self) -> bool:
        """是否为用户自定义命名（自动标题不算）"""
        return bool(self.title) and not self.title_auto

    def label(self) -> str:
        """``id · 标题`` 形式的单行标签，供界面与补全使用"""
        return f"{self.id} · {self.display_title}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "title_auto": self.title_auto,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }

    @classmethod
    def from_record(cls, record: dict, path: str = "") -> "SessionMeta":
        messages = record.get("messages")
        if not isinstance(messages, list):
            messages = []
        fallback_id = os.path.splitext(os.path.basename(path))[0] if path else ""
        return cls(
            id=str(record.get("id") or fallback_id),
            title=clean_title(record.get("title")),
            title_auto=bool(record.get("title_auto", False)),
            created_at=float(record.get("created_at") or 0.0),
            updated_at=float(record.get("updated_at") or 0.0),
            message_count=len(messages),
            path=path,
        )


class SessionStore:
    """``.tina/chat_sessions/`` 下的会话仓库

    Args:
        root: 项目根目录（``.tina`` 建在这里）
        work_dir: 工作目录名，默认 ``.tina``
        sessions_dir: 会话子目录名，默认 ``chat_sessions``
    """

    def __init__(
        self,
        root: str = ".",
        work_dir: str = DEFAULT_WORK_DIR,
        sessions_dir: str = DEFAULT_SESSIONS_DIR,
    ) -> None:
        self.root = os.path.abspath(root)
        self.work_dir = work_dir
        self.sessions_dir = sessions_dir
        self.base_dir = os.path.join(self.root, work_dir)
        # 构造即建目录：保证 ``.tina/chat_sessions`` 一定存在
        self.dir = ensure_session_dir(self.root, work_dir, sessions_dir)

    # ------------------------------------------------------------------ 路径

    def path_for(self, session_id: str) -> str:
        """会话 id 对应的文件路径"""
        return os.path.join(self.dir, f"{session_id}{SESSION_SUFFIX}")

    @staticmethod
    def new_id() -> str:
        """生成可排序且唯一的会话 id：``20250101-120000-ab12``"""
        return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    # ------------------------------------------------------------------ 查询

    def list_sessions(self) -> list[SessionMeta]:
        """列出全部会话，按最近更新倒序"""
        metas: list[SessionMeta] = []
        try:
            names = os.listdir(self.dir)
        except OSError:
            return metas
        for name in names:
            if not name.endswith(SESSION_SUFFIX):
                continue
            path = os.path.join(self.dir, name)
            record = _read_json(path)
            if record is None:
                continue
            metas.append(SessionMeta.from_record(record, path))
        metas.sort(key=lambda m: (m.updated_at, m.created_at), reverse=True)
        return metas

    def labels(self) -> list[str]:
        """全部会话的 ``id · 标题`` 标签（补全候选）"""
        return [meta.label() for meta in self.list_sessions()]

    def exists(self, session_id: str) -> bool:
        return bool(session_id) and os.path.isfile(self.path_for(session_id))

    def get_meta(self, session_id: str) -> SessionMeta | None:
        record = self.load(session_id)
        if record is None:
            return None
        return SessionMeta.from_record(record, self.path_for(session_id))

    def load(self, session_id: str) -> dict | None:
        """读取完整会话记录（元数据 + messages），不存在返回 None"""
        if not session_id:
            return None
        return _read_json(self.path_for(session_id))

    def get_messages(self, session_id: str) -> list[dict]:
        """只取消息列表"""
        record = self.load(session_id) or {}
        messages = record.get("messages")
        return messages if isinstance(messages, list) else []

    def find(self, query: str) -> list[SessionMeta]:
        """按 id / id 前缀 / 标题模糊匹配（大小写不敏感），供切换与补全"""
        text = str(query or "").strip()
        metas = self.list_sessions()
        if not text:
            return metas
        exact = [m for m in metas if m.id == text]
        if exact:
            return exact
        prefix = [m for m in metas if m.id.startswith(text)]
        if prefix:
            return prefix
        lowered = text.lower()
        return [m for m in metas if lowered in m.display_title.lower()]

    def resolve(self, query: str) -> SessionMeta | None:
        """返回最佳匹配的会话；query 为空时返回最近更新的一个"""
        matches = self.find(query)
        return matches[0] if matches else None

    # ------------------------------------------------------------------ 写入

    def create(self, messages=None, title: str = "", title_auto: bool = False) -> str:
        """新建会话并返回 id"""
        session_id = self.new_id()
        self.save(session_id, messages or [], title=title, title_auto=title_auto)
        return session_id

    def get_blocks(self, session_id: str) -> list[dict]:
        """取该会话保存的渲染块快照（含耗时/timing）；没有返回 []"""
        record = self.load(session_id) or {}
        blocks = record.get("blocks")
        return blocks if isinstance(blocks, list) else []

    def save(
        self,
        session_id: str,
        messages,
        title: str | None = None,
        title_auto: bool | None = None,
        blocks: list[dict] | None = None,
    ) -> SessionMeta:
        """写入会话（不存在则新建）

        ``title`` / ``title_auto`` 传 None 表示保留原有值，避免刷新消息时把
        用户自定义的命名冲掉；``blocks`` 传 None 表示保留原有的渲染块快照。
        """
        session_id = str(session_id or "").strip()
        if not session_id:
            raise ValueError("session_id 不能为空")
        path = self.path_for(session_id)
        existing = _read_json(path) or {}
        now = time.time()
        if title is None:
            new_title = existing.get("title", "") or ""
            new_auto = existing.get("title_auto", False)
        else:
            new_title = clean_title(title)
            new_auto = bool(title_auto)
        record = {
            "id": session_id,
            "title": new_title,
            "title_auto": bool(new_auto),
            "created_at": float(existing.get("created_at") or now),
            "updated_at": now,
            "messages": list(messages or []),
            "blocks": (
                blocks if blocks is not None else existing.get("blocks", [])
            ),
        }
        _write_json(path, record)
        return SessionMeta.from_record(record, path)

    def rename(self, session_id: str, title: str) -> SessionMeta | None:
        """自定义命名（同时清除「自动标题」标记，之后不再被自动标题覆盖）"""
        record = self.load(session_id)
        if record is None:
            return None
        record["title"] = clean_title(title)
        record["title_auto"] = False
        record["updated_at"] = time.time()
        _write_json(self.path_for(session_id), record)
        return SessionMeta.from_record(record, self.path_for(session_id))

    def set_auto_title(self, session_id: str, title: str) -> SessionMeta | None:
        """写入自动生成的标题；已有用户自定义命名时保持不变"""
        record = self.load(session_id)
        if record is None:
            return None
        if record.get("title") and not record.get("title_auto"):
            return SessionMeta.from_record(record, self.path_for(session_id))
        record["title"] = clean_title(title)
        record["title_auto"] = True
        record["updated_at"] = time.time()
        _write_json(self.path_for(session_id), record)
        return SessionMeta.from_record(record, self.path_for(session_id))

    def delete(self, session_id: str) -> bool:
        """删除会话；不存在返回 False"""
        path = self.path_for(session_id)
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
        except OSError:
            return False
        return True
