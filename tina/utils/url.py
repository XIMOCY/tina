"""URL 小工具

解析 / 规范化大模型 API 的 base_url。这类通用小函数集中放在 utils 下，
供 ``llm.base_api``、``llm.files_api`` 等模块复用。
"""

from __future__ import annotations


CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def normalize_base_url(base_url: str) -> str:
    """确保 base_url 以 /chat/completions 结尾（缺失时自动补上）

    传入根地址（``https://api.deepseek.com``）或完整地址
    （``.../chat/completions``）都可，返回规范化后的完整地址。
    """
    if not base_url or not isinstance(base_url, str):
        return base_url
    url = base_url.rstrip("/")
    if not url.lower().endswith(CHAT_COMPLETIONS_SUFFIX):
        url += CHAT_COMPLETIONS_SUFFIX
    return url


def derive_api_root(base_url: str) -> str:
    """从 base_url 去掉结尾的 /chat/completions，得到服务根地址"""
    url = (base_url or "").rstrip("/")
    if url.lower().endswith(CHAT_COMPLETIONS_SUFFIX):
        url = url[: -len(CHAT_COMPLETIONS_SUFFIX)]
    return url.rstrip("/")
