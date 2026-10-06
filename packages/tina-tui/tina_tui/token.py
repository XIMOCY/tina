"""TUI token 计数器

记录最近一次大模型请求返回的 `usage`，反映当前上下文占用。

因为每次请求都会携带完整消息，服务端返回的 `total_tokens` 基本就等于
当前上下文长度，所以这里**只记录最新一次的值，不累加**。
上层界面按需读取 total / ratio / is_exceeded / cache_hit_rate。

顺带记录 prompt 的缓存命中情况（上下文越长命中率越高，直接决定实际费用），
兼容 DeepSeek 的 `prompt_cache_hit_tokens` 与 OpenAI 风格的
`prompt_tokens_details.cached_tokens`。
"""

from __future__ import annotations

from typing import Any


def _split_cache_tokens(usage: dict[str, Any], prompt: int) -> tuple[int, int]:
    """从 usage 里取出 prompt 的 (命中缓存, 未命中) token 数

    服务端没返回缓存信息时返回 (0, 0)。
    """
    hit = usage.get("prompt_cache_hit_tokens")
    if hit is None:
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            hit = details.get("cached_tokens")
    if hit is None:
        return 0, 0

    hit = int(hit or 0)
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = max(0, int(prompt or 0) - hit)
    return hit, int(miss or 0)


class TokenCounter:
    """token 计数器（记录最近一次请求的上下文占用）

    用法：
        counter = TokenCounter(max_tokens=32000)
        for chunk in agent.predict(...):
            counter.add_from_chunk(chunk)
        print(counter.total_tokens, counter.ratio)
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        self.max_tokens = max_tokens
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.calls = 0
        self.last_usage: dict[str, Any] | None = None
        self.cache_hit_tokens = 0
        self.cache_miss_tokens = 0

    def set_max_tokens(self, max_tokens: int | None) -> None:
        """设置用户的最大 token 数，传 None 表示不限制"""
        self.max_tokens = max_tokens

    def add_from_chunk(self, chunk: dict[str, Any]) -> None:
        """从 AgentResponse 分片中提取 usage 并记录"""
        if not chunk:
            return
        self.add_usage(chunk.get("usage"))

    def add_usage(self, usage: dict[str, Any] | None) -> None:
        """记录一次请求的 usage（覆盖上一次），兼容不同厂商的字段命名"""
        if not usage:
            return

        prompt = usage.get("prompt_tokens")
        if prompt is None:
            prompt = usage.get("input_tokens", 0)
        completion = usage.get("completion_tokens")
        if completion is None:
            completion = usage.get("output_tokens", 0)
        total = usage.get("total_tokens")
        if not total:
            total = (prompt or 0) + (completion or 0)

        self.prompt_tokens = int(prompt or 0)
        self.completion_tokens = int(completion or 0)
        self.total_tokens = int(total or 0)
        self.cache_hit_tokens, self.cache_miss_tokens = _split_cache_tokens(
            usage, self.prompt_tokens
        )
        self.calls += 1
        self.last_usage = usage

    @property
    def remaining(self) -> int | None:
        """剩余可用 token，未设置上限时返回 None"""
        if self.max_tokens is None:
            return None
        return self.max_tokens - self.total_tokens

    @property
    def ratio(self) -> float:
        """当前上下文占用比例（0.0 ~ 1.0+），未设置上限时为 0.0"""
        if not self.max_tokens:
            return 0.0
        return self.total_tokens / self.max_tokens

    @property
    def is_exceeded(self) -> bool:
        """当前上下文是否已超过用户设置的最大 token 数"""
        return self.max_tokens is not None and self.total_tokens > self.max_tokens

    @property
    def cache_hit_rate(self) -> float | None:
        """prompt 命中缓存的比例（0.0 ~ 1.0）

        上下文越长命中率越高（前缀被服务端缓存了），直接决定实际费用。
        服务端没返回缓存信息时返回 None。
        """
        total = self.cache_hit_tokens + self.cache_miss_tokens
        if total <= 0:
            return None
        return self.cache_hit_tokens / total

    def reset(self) -> None:
        """清零"""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.calls = 0
        self.last_usage = None
        self.cache_hit_tokens = 0
        self.cache_miss_tokens = 0
