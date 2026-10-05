"""LLM usage 记录

统一不同厂商的 usage 字段命名（OpenAI Chat Completions / Responses / DeepSeek），
并提供累加器 ``UsageTracker``。配合 ``AgentEvents`` 的 ``on_usage`` 事件使用：

    from tina.utils import UsageTracker

    tracker = UsageTracker()
    agent.events.add_on_usage_handler(tracker.add)
    for _ in agent.predict("你好"):
        pass
    print(tracker.summary())

``on_usage`` 每次 LLM 请求返回 usage 时触发一次（含工具循环中的每一轮）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Usage:
    """归一化后的单次请求用量"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    raw: dict[str, Any] | None = None

    @classmethod
    def from_raw(cls, raw: Any) -> "Usage | None":
        """兼容多种命名的原始 usage；非法/空输入返回 None"""
        if not raw or not isinstance(raw, dict):
            return None

        prompt = raw.get("prompt_tokens")
        if prompt is None:
            prompt = raw.get("input_tokens", 0)
        completion = raw.get("completion_tokens")
        if completion is None:
            completion = raw.get("output_tokens", 0)
        total = raw.get("total_tokens")
        if not total:
            total = (prompt or 0) + (completion or 0)

        completion_details = raw.get("completion_tokens_details") or {}
        reasoning = completion_details.get(
            "reasoning_tokens", raw.get("reasoning_tokens", 0)
        )
        prompt_details = raw.get("prompt_tokens_details") or {}
        cached = prompt_details.get(
            "cached_tokens", raw.get("prompt_cache_hit_tokens", 0)
        )

        return cls(
            prompt_tokens=int(prompt or 0),
            completion_tokens=int(completion or 0),
            total_tokens=int(total or 0),
            reasoning_tokens=int(reasoning or 0),
            cached_tokens=int(cached or 0),
            raw=raw,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
        }


class UsageTracker:
    """累积多次 LLM 请求的 usage；可直接注册为 on_usage 事件处理器"""

    def __init__(self) -> None:
        self.reset()

    def add(self, usage: Usage | dict | None) -> None:
        """累加一次 usage（接受 Usage 或原始 dict）"""
        if usage is None:
            return
        if isinstance(usage, dict):
            usage = Usage.from_raw(usage)
        if usage is None:
            return

        self.calls += 1
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.reasoning_tokens += usage.reasoning_tokens
        self.cached_tokens += usage.cached_tokens
        self.last = usage
        self.history.append(usage.to_dict())

    def summary(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
        }

    def reset(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0
        self.last: Usage | None = None
        self.history: list[dict[str, int]] = []
