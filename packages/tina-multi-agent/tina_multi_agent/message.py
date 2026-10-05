from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    """
    多 Agent 环境中的一条消息。

    role:
        - "user"：环境（外部）投放的指令；
        - "assistant"：Agent 之间通过通信工具发送的消息。
    """

    sender: str
    content: str
    recipient: Optional[str] = None
    role: str = "assistant"
