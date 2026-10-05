"""兼容转发层：多 Agent 已迁移到独立包 ``tina-multi-agent``。

保留旧的 ``tina.utils.multi_agent`` 导入路径；未安装扩展包时给出明确提示。
"""

try:
    from tina_multi_agent import (  # noqa: F401
        Message,
        MessageBus,
        MultiAgentEnvironment,
        MultiAgentWeb,
    )
except ModuleNotFoundError as exc:
    if (exc.name or "").split(".")[0] == "tina_multi_agent":
        raise ImportError(
            "多 Agent 已迁移到独立包：请先安装 tina-multi-agent，"
            "例如 `pip install tina-multi-agent` 或 `pip install tina-python[multi-agent]`。"
        ) from exc
    raise

__all__ = [
    "Message",
    "MessageBus",
    "MultiAgentEnvironment",
    "MultiAgentWeb",
]
