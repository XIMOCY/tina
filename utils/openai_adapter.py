"""
Utility functions to adapt tina outputs to OpenAI Chat Completions format.

Includes:
- to_openai_chat_completion: adapt non-streaming result
- to_openai_chat_completion_stream: adapt streaming generator
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Generator, Iterable


def _gen_id(prefix: str = "chatcmpl") -> str:
    """Generate a simple OpenAI-like id."""
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


def to_openai_chat_completion(
    tina_result: Dict[str, Any],
    model: str = "tina-agent",
    include_usage: bool = False,
) -> Dict[str, Any]:
    """
    Adapt a tina non-streaming result to OpenAI Chat Completions format.

    Expected tina_result structure:
        {"role": "assistant", "content": "...", "tool_calls": [...]}
    """
    created = int(time.time())
    response_id = _gen_id()

    role = tina_result.get("role", "assistant")
    content = tina_result.get("content", "")

    message: Dict[str, Any] = {
        "role": role,
        "content": content,
    }

    # Pass through tool_calls if present
    if "tool_calls" in tina_result:
        message["tool_calls"] = tina_result["tool_calls"]

    openai_resp: Dict[str, Any] = {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
    }

    if include_usage and "usage" in tina_result:
        openai_resp["usage"] = tina_result["usage"]

    return openai_resp


def to_openai_chat_completion_stream(
    tina_stream: Iterable[Dict[str, Any]],
    model: str = "tina-agent",
) -> Generator[Dict[str, Any], None, None]:
    """
    Adapt tina streaming output generator to OpenAI Chat Completions
    streaming chunks generator.

    Expected tina_stream yields dicts like:
        {"role": "assistant", "content": "..."} or
        {"role": "assistant", "tool_calls": [...], "id": "..."} etc.
    """
    response_id = _gen_id()
    created = int(time.time())

    # First chunk with role (optional but common for OpenAI style)
    yield {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        ],
    }

    for chunk in tina_stream:
        if not isinstance(chunk, dict):
            continue

        delta: Dict[str, Any] = {}

        # Text content
        content = chunk.get("content", "")
        if content:
            delta["content"] = content

        # Tool calls (if any)
        if "tool_calls" in chunk:
            delta["tool_calls"] = chunk["tool_calls"]

        if not delta:
            continue

        yield {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": None,
                }
            ],
        }

    # Final chunk with finish_reason
    yield {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }

