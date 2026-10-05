"""兼容转发层：TUI 已迁移到独立包 ``tina-tui``。

保留旧的 ``tina.utils.tui`` 导入路径；未安装扩展包时给出明确提示。
``TinaTUI`` / ``run_agent_in_tui`` 仍延迟导入，避免在未安装 textual 时失败。
"""

try:
    from tina_tui import (  # noqa: F401
        TuiBlock,
        TuiMessageStore,
        UnlimitedContextManager,
        UnlimitedMultimodalContextManager,
        make_unlimited_context_manager,
        TokenCounter,
    )
except ModuleNotFoundError as exc:
    if (exc.name or "").split(".")[0] == "tina_tui":
        raise ImportError(
            "TUI 已迁移到独立包：请先安装 tina-tui，"
            "例如 `pip install tina-tui` 或 `pip install tina-python[tui]`。"
        ) from exc
    raise

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
    if name in ("TinaTUI", "run_agent_in_tui"):
        from tina_tui import TinaTUI, run_agent_in_tui

        return {"TinaTUI": TinaTUI, "run_agent_in_tui": run_agent_in_tui}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
