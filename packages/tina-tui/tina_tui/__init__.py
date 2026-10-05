from typing import TYPE_CHECKING

from .context_manager import (
    TuiBlock,
    TuiMessageStore,
    UnlimitedContextManager,
    UnlimitedMultimodalContextManager,
    make_unlimited_context_manager,
)
from .token import TokenCounter

if TYPE_CHECKING:
    # 仅给类型检查器/IDE 看，运行时由 __getattr__ 延迟导入（textual 是可选依赖）
    from .tui import TinaTUI, run_agent_in_tui

__all__ = [
    "TuiBlock",
    "TuiMessageStore",
    "UnlimitedContextManager",
    "UnlimitedMultimodalContextManager",
    "make_unlimited_context_manager",
    "TokenCounter",
    "TinaTUI",
    "run_agent_in_tui",
]


def __getattr__(name):
    # 延迟导入界面，保证未安装 textual 时仍可使用列表与计数组件
    if name in ("TinaTUI", "run_agent_in_tui"):
        from . import tui

        return getattr(tui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
