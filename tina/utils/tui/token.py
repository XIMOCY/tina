"""TUI token 计数器

独立于消息上下文，负责从大模型返回的 `usage` 中累加 token 消耗，
并允许用户设置最大 token 数用于界面展示进度与超限警告。

只累加、不裁剪；上层界面按需读取 total / ratio / is_exceeded。
"""

from __future__ import annotations

from typing import Any


class TokenCounter:
    """token 累加器

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

    def set_max_tokens(self, max_tokens: int | None) -> None:
        """设置用户的最大 token 数，传 None 表示不限制"""
        self.max_tokens = max_tokens

    def add_from_chunk(self, chunk: dict[str, Any]) -> None:
        """从 AgentResponse 分片中提取 usage 并累加"""
        if not chunk:
            return
        self.add_usage(chunk.get("usage"))

    def add_usage(self, usage: dict[str, Any] | None) -> None:
        """累加一次请求的 usage，兼容不同厂商的字段命名"""
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

        self.prompt_tokens += int(prompt or 0)
        self.completion_tokens += int(completion or 0)
        self.total_tokens += int(total or 0)
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
        """已用占比（0.0 ~ 1.0+），未设置上限时为 0.0"""
        if not self.max_tokens:
            return 0.0
        return self.total_tokens / self.max_tokens

    @property
    def is_exceeded(self) -> bool:
        """是否已超过用户设置的最大 token 数"""
        return self.max_tokens is not None and self.total_tokens > self.max_tokens

    def reset(self) -> None:
        """清零所有累计值"""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.calls = 0
        self.last_usage = None
