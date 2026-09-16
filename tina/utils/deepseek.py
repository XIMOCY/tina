"""DeepSeek 思考（reasoning）与工具调用兼容处理

DeepSeek 思考模式在"边思考边调用工具"时，要求把本轮工具调用**之前**产生的
`reasoning_content`（以及正文 `content`）放在带 `tool_calls` 的那条 assistant
消息上一起回传。否则多轮之后请求会报错，例如：

    The `reasoning_content` in the thinking mode must be passed back to the API.

tina 核心不会自动处理：流式路径在有正文时先 `add_assistant_message(正文)`、再
`add_tool_calls()`，会留下两条连续的 assistant 消息，且 reasoning 被丢弃。

`enable_deepseek_reasoning_tools(agent)` 自动注册所需事件处理器：

- `on_stream_chunk`   累积本轮产生的 `reasoning_content`
- `before_tool_calls` 把累积的思考写进带 `tool_calls` 的 assistant 消息；
                      若其前面紧挨着一条纯 assistant 消息，则合并 content /
                      reasoning_content 并删除前一条
- `on_turn_end`       清空缓存，避免思考内容泄漏到下一轮

注意：该机制依赖流式输出（非流式路径不会通过事件派发 reasoning_content）。
"""

from __future__ import annotations

from typing import Any


def _chunk_field(chunk: Any, key: str) -> Any:
    """从 chunk（dict 或 AgentResponse 等对象）中取字段"""
    if chunk is None:
        return None
    if isinstance(chunk, dict):
        return chunk.get(key)
    return getattr(chunk, key, None)


def enable_deepseek_reasoning_tools(agent: Any) -> None:
    """为 Agent 开启 DeepSeek「思考 + 工具调用」兼容处理

    Args:
        agent: tina.Agent / tina.MultimodalAgent 实例
    """
    parts: list[str] = []

    @agent.on_stream_chunk()
    def _collect(chunk: Any) -> None:
        text = _chunk_field(chunk, "reasoning_content")
        if text:
            parts.append(text)

    @agent.before_tool_calls()
    def _patch(tool_calls: list | None = None) -> None:
        messages = agent.context_manager.get_messages()

        target = None
        for message in reversed(messages):
            if message.get("role") == "assistant" and message.get("tool_calls"):
                target = message
                break
            if message.get("role") in ("user", "system"):
                break
        if target is None:
            return

        reasoning = "".join(parts)
        parts.clear()
        if reasoning and not target.get("reasoning_content"):
            target["reasoning_content"] = reasoning

        try:
            index = messages.index(target)
        except ValueError:
            return

        # 把紧挨在前面的纯 assistant 消息合并进来，避免出现两条连续 assistant
        if index > 0:
            previous = messages[index - 1]
            if previous.get("role") == "assistant" and not previous.get("tool_calls"):
                if previous.get("content") and not target.get("content"):
                    target["content"] = previous["content"]
                if previous.get("reasoning_content") and not target.get(
                    "reasoning_content"
                ):
                    target["reasoning_content"] = previous["reasoning_content"]
                messages.pop(index - 1)

    @agent.on_turn_end()
    def _reset() -> None:
        parts.clear()


__all__ = ["enable_deepseek_reasoning_tools"]
