from .context_manager import TuiBlock, TuiContextManager
from .token import TokenCounter

__all__ = [
    "TuiBlock",
    "TuiContextManager",
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
