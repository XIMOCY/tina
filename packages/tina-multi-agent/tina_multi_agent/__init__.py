"""tina 实验性多 Agent 场景。使用方式见包的 README.md。"""

from .environment import MultiAgentEnvironment
from .message import Message
from .message_bus import MessageBus
from .web import MultiAgentWeb

__all__ = [
    "Message",
    "MessageBus",
    "MultiAgentEnvironment",
    "MultiAgentWeb",
]
