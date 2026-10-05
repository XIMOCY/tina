import asyncio
import json
import httpx
import sys
import time
from typing import AsyncGenerator, Dict, Any
from ..core import logger
from ..core.error import APIRequestFailed


def _build_timing(
    t0,
    first_at,
    ended_at,
    chunks,
    usage,
    *,
    reasoning_first=None,
    reasoning_last=None,
    reasoning_chunks=0,
    content_first=None,
    content_last=None,
    content_chunks=0,
):
    """构造流式计时字典（时间单位：秒）

    - ttft            请求发出 -> 第一个 token（首字延迟）
    - duration        整段流总耗时
    - gen_duration    生成窗口（第一个 token -> 结束）
    - thinking_duration / answer_duration  思考阶段 / 回答阶段各自耗时
    - tokens          真实 completion token 数（含思考）
    - reasoning_tokens / output_tokens     思考 token / 正文 token
    - tps             生成速度（含思考）= tokens / gen_duration
    - output_tps      正文速度 = output_tokens / gen_duration
    """

    def _rate(numerator, denominator):
        if numerator and denominator and denominator > 0:
            return round(numerator / denominator, 2)
        return None

    duration = ended_at - t0
    ttft = (first_at - t0) if first_at is not None else None
    gen = (ended_at - first_at) if first_at is not None else None

    thinking_duration = (
        reasoning_last - reasoning_first
        if reasoning_first is not None and reasoning_last is not None
        else None
    )
    answer_duration = (
        content_last - content_first
        if content_first is not None and content_last is not None
        else None
    )

    completion = None
    reasoning_tokens = 0
    if usage:
        completion = usage.get("completion_tokens")
        if completion is None:
            completion = usage.get("output_tokens")
        details = usage.get("completion_tokens_details") or {}
        reasoning_tokens = (
            details.get("reasoning_tokens", usage.get("reasoning_tokens", 0)) or 0
        )

    output_tokens = None
    if completion is not None:
        output_tokens = max(0, completion - reasoning_tokens)

    return {
        "ttft": round(ttft, 3) if ttft is not None else None,
        "duration": round(duration, 3),
        "gen_duration": round(gen, 3) if gen is not None else None,
        "thinking_duration": (
            round(thinking_duration, 3) if thinking_duration is not None else None
        ),
        "answer_duration": (
            round(answer_duration, 3) if answer_duration is not None else None
        ),
        "chunks": chunks,
        "reasoning_chunks": reasoning_chunks,
        "content_chunks": content_chunks,
        "tokens": completion,
        "reasoning_tokens": reasoning_tokens if completion is not None else None,
        "output_tokens": output_tokens,
        "tps": _rate(completion, gen),
        "output_tps": _rate(output_tokens, gen),
    }


def stream_generator_parser(base_url, payload, headers, timeout):
    tool_calls_buffer = {}
    final_tool_calls = None
    received_ids = {}
    tool_name_sent = set()
    reasoning_buffer = ""
    usage = None  # 新增：缓存 usage
    t0 = time.perf_counter()
    first_at = None
    chunks = 0
    reasoning_first = None
    reasoning_last = None
    reasoning_chunks = 0
    content_first = None
    content_last = None
    content_chunks = 0

    with httpx.stream(
        "POST", f"{base_url}", json=payload, headers=headers, timeout=timeout
    ) as response:

        if response.status_code != 200:
            body = response.read()
            body_text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
            logger.error(
                f"BaseAPI - 在发送请求时收到错误状态码：{response.status_code}，错误信息：{body_text}，请求信息：{payload}"
            )
            raise APIRequestFailed(base_url, response.status_code, body_text)

        for line in response.iter_lines():
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    # 新增：如果这条 data 包含 usage，就缓存
                    if "usage" in data:
                        usage = data["usage"]

                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})

                        if "content" in delta:
                            content = delta.get("content", "")
                            if content:
                                now = time.perf_counter()
                                if first_at is None:
                                    first_at = now
                                if content_first is None:
                                    content_first = now
                                content_last = now
                                content_chunks += 1
                                chunks += 1
                                yield {"role": "assistant", "content": content}

                        if "reasoning_content" in delta:
                            reasoning_content = delta.get("reasoning_content", "")
                            if reasoning_content:
                                reasoning_buffer += reasoning_content
                                now = time.perf_counter()
                                if first_at is None:
                                    first_at = now
                                if reasoning_first is None:
                                    reasoning_first = now
                                reasoning_last = now
                                reasoning_chunks += 1
                                chunks += 1
                                yield {
                                    "role": "assistant",
                                    "reasoning_content": reasoning_content,
                                    "content": "",
                                }

                        if "tool_calls" in delta:
                            if delta["tool_calls"] is None:
                                continue
                            for tool_call in delta["tool_calls"]:
                                index = tool_call["index"]

                                if index not in tool_calls_buffer:
                                    tool_calls_buffer[index] = {
                                        "index": index,
                                        "function": {"arguments": ""},
                                        "type": "",
                                        "id": "",
                                    }

                                if tool_call.get("id") and index not in received_ids:
                                    received_ids[index] = tool_call["id"]

                                current = tool_calls_buffer[index]
                                current["id"] = received_ids.get(index, "")
                                current["type"] = (
                                    tool_call.get("type") or current["type"]
                                )

                                if tool_call.get("function"):
                                    func = tool_call["function"]
                                    current["function"]["name"] = func.get(
                                        "name"
                                    ) or current["function"].get("name", "")

                                    if (
                                        current["function"].get("name")
                                        and index not in tool_name_sent
                                    ):
                                        tool_name_sent.add(index)
                                        yield {
                                            "role": "assistant",
                                            "content": "",
                                            "tool_name": current["function"]["name"],
                                            "tool_index": index,
                                        }

                                    if func.get("arguments") is not None:
                                        new_args = func.get("arguments", "")
                                        if new_args:
                                            current["function"]["arguments"] += new_args
                                            if first_at is None:
                                                first_at = time.perf_counter()
                                            chunks += 1
                                            yield {
                                                "role": "assistant",
                                                "content": "",
                                                "tool_arguments": new_args,
                                                "tool_name": current["function"][
                                                    "name"
                                                ],
                                                "tool_index": index,
                                            }
                                    else:
                                        current["function"]["arguments"] += (
                                            func.get("arguments", "")
                                            if func.get("arguments")
                                            else ""
                                        )

                            final_tool_calls = [
                                v for k, v in sorted(tool_calls_buffer.items())
                            ]

                except GeneratorExit:
                    return
                except json.JSONDecodeError:
                    continue

        ended_at = time.perf_counter()
        timing = _build_timing(
            t0,
            first_at,
            ended_at,
            chunks,
            usage,
            reasoning_first=reasoning_first,
            reasoning_last=reasoning_last,
            reasoning_chunks=reasoning_chunks,
            content_first=content_first,
            content_last=content_last,
            content_chunks=content_chunks,
        )
        last = {"role": "assistant", "content": ""}
        if final_tool_calls:
            last["tool_calls"] = final_tool_calls
            last["id"] = final_tool_calls[0]["id"]
            logger.info(f"BaseAPI - 返回的最终工具调用信息：{final_tool_calls}")
        if usage is not None:
            logger.info(f"BaseAPI - 返回的usage信息：{usage}")
            last["usage"] = usage
        last["timing"] = timing
        logger.info(f"BaseAPI - 流式计时：{timing}")
        yield last


async def astream_generator_parser(
    client: httpx.AsyncClient,
    base_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    异步流式解析器，用于处理异步API调用返回的流式数据
    """
    tool_calls_buffer = {}
    final_tool_calls = None
    received_ids = {}
    tool_name_sent = set()
    reasoning_buffer = ""
    usage = None  # 新增：缓存 usage
    t0 = time.perf_counter()
    first_at = None
    chunks = 0
    reasoning_first = None
    reasoning_last = None
    reasoning_chunks = 0
    content_first = None
    content_last = None
    content_chunks = 0

    async with client.stream(
        "POST", f"{base_url}", json=payload, headers=headers, timeout=timeout
    ) as response:
        if response.status_code != 200:
            body = await response.aread()
            body_text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
            logger.error(
                f"BaseAPI - 在发送请求时收到错误状态码：{response.status_code}，错误信息：{body_text}，请求信息：{payload}"
            )
            raise APIRequestFailed(base_url, response.status_code, body_text)

        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    # 新增：如果这条 data 包含 usage，就缓存
                    if "usage" in data:
                        usage = data["usage"]

                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})

                        if "content" in delta:
                            content = delta.get("content", "")
                            if content:
                                now = time.perf_counter()
                                if first_at is None:
                                    first_at = now
                                if content_first is None:
                                    content_first = now
                                content_last = now
                                content_chunks += 1
                                chunks += 1
                                yield {"role": "assistant", "content": content}

                        if "reasoning_content" in delta:
                            reasoning_content = delta.get("reasoning_content", "")
                            if reasoning_content:
                                reasoning_buffer += reasoning_content
                                now = time.perf_counter()
                                if first_at is None:
                                    first_at = now
                                if reasoning_first is None:
                                    reasoning_first = now
                                reasoning_last = now
                                reasoning_chunks += 1
                                chunks += 1
                                yield {
                                    "role": "assistant",
                                    "reasoning_content": reasoning_content,
                                    "content": "",
                                }

                        if "tool_calls" in delta:
                            if delta["tool_calls"] is None:
                                continue
                            for tool_call in delta["tool_calls"]:
                                index = tool_call["index"]

                                if index not in tool_calls_buffer:
                                    tool_calls_buffer[index] = {
                                        "index": index,
                                        "function": {"arguments": ""},
                                        "type": "",
                                        "id": "",
                                    }

                                if tool_call.get("id") and index not in received_ids:
                                    received_ids[index] = tool_call["id"]

                                current = tool_calls_buffer[index]
                                current["id"] = received_ids.get(index, "")
                                current["type"] = (
                                    tool_call.get("type") or current["type"]
                                )

                                if tool_call.get("function"):
                                    func = tool_call["function"]
                                    current["function"]["name"] = func.get(
                                        "name"
                                    ) or current["function"].get("name", "")

                                    if (
                                        current["function"].get("name")
                                        and index not in tool_name_sent
                                    ):
                                        tool_name_sent.add(index)
                                        yield {
                                            "role": "assistant",
                                            "content": "",
                                            "tool_name": current["function"]["name"],
                                            "tool_index": index,
                                        }

                                    if func.get("arguments") is not None:
                                        new_args = func.get("arguments", "")
                                        if new_args:
                                            current["function"]["arguments"] += new_args
                                            if first_at is None:
                                                first_at = time.perf_counter()
                                            chunks += 1
                                            yield {
                                                "role": "assistant",
                                                "content": "",
                                                "tool_arguments": new_args,
                                                "tool_name": current["function"][
                                                    "name"
                                                ],
                                                "tool_index": index,
                                            }
                                    else:
                                        current["function"]["arguments"] += (
                                            func.get("arguments", "")
                                            if func.get("arguments")
                                            else ""
                                        )

                            final_tool_calls = [
                                v for k, v in sorted(tool_calls_buffer.items())
                            ]
                except GeneratorExit:
                    return
                except json.JSONDecodeError:
                    continue

        ended_at = time.perf_counter()
        timing = _build_timing(
            t0,
            first_at,
            ended_at,
            chunks,
            usage,
            reasoning_first=reasoning_first,
            reasoning_last=reasoning_last,
            reasoning_chunks=reasoning_chunks,
            content_first=content_first,
            content_last=content_last,
            content_chunks=content_chunks,
        )
        last = {"role": "assistant", "content": ""}
        if final_tool_calls:
            last["tool_calls"] = final_tool_calls
            last["id"] = final_tool_calls[0]["id"]
            logger.info(f"BaseAPI - 返回的最终工具调用信息：{final_tool_calls}")
        if usage is not None:
            logger.info(f"BaseAPI - 返回的usage信息：{usage}")
            last["usage"] = usage
        last["timing"] = timing
        logger.info(f"BaseAPI - 流式计时：{timing}")
        yield last

        # 让出事件循环控制权，让底层 TLS 连接的清理回调得以执行
        # (Windows ProactorEventLoop 在 asyncio.run() 关闭循环后
        #  无法处理这些回调，会导致 RuntimeError: Event loop is closed)
        await asyncio.sleep(0)


# 瞬时流式错误的默认重试次数与退避基数
_TRANSIENT_RETRIES = 2
_TRANSIENT_BACKOFF = 0.8


def _is_transient_stream_error(error: BaseException) -> bool:
    """判断是否值得重试的瞬时错误（连接 / 流中断）。

    - httpx.TransportError、超时：明确的网络类错误；
    - str(error) 为空：多为 anyio 的 ClosedResourceError / BrokenResourceError
      这类没有 message 的异常（线上「处理消息失败:」后面空白就是它）。
    HTTP 4xx/5xx（我们自己抛的带状态码文本的 Exception）不会被命中，因此不重试。
    """
    if isinstance(error, (asyncio.TimeoutError, httpx.TransportError)):
        return True
    return not str(error).strip()


async def astream_generator_parser_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
    retries: int = _TRANSIENT_RETRIES,
    backoff: float = _TRANSIENT_BACKOFF,
) -> AsyncGenerator[Dict[str, Any], None]:
    """在 astream_generator_parser 外再包一层重试。

    只对「还没吐出任何 chunk 就失败」的瞬时网络错误做有限次退避重试；
    一旦已经 yield 过内容就不再重试（避免重复输出），直接抛给上层。
    """
    last_error = None
    for attempt in range(retries + 1):
        yielded = False
        try:
            async for chunk in astream_generator_parser(
                client, base_url, payload, headers, timeout
            ):
                yielded = True
                yield chunk
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            if (
                yielded
                or attempt >= retries
                or not _is_transient_stream_error(error)
            ):
                raise
            wait = backoff * (attempt + 1)
            logger.warning(
                f"BaseAPI - 流式请求失败（{type(error).__name__}: {error!r}），"
                f"{wait:.1f}s 后重试 {attempt + 1}/{retries}"
            )
            await asyncio.sleep(wait)
    if last_error is not None:
        raise last_error