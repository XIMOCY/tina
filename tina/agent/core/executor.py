"""
编写者：王出日
日期：2026, 02, 13
版本：0.5.3
功能：Agent的工具执行器
"""

import io
from contextlib import redirect_stdout, redirect_stderr
import sys
import threading
import json
import asyncio
import inspect
import time
from ...mcp.mcp_tools_executor import MCPToolExecutor

from .events import AgentEvents
from ...core import logger


def _tool_timeout(_tools, name: str, default: float = 60):
    """安全获取工具超时；MCP 工具可能不在 Tools 里，取不到就用默认值"""
    try:
        return _tools.get_timeout(name)
    except Exception:
        return default


class _ThreadLocalStream:
    """按线程路由的 stdout/stderr 代理。

    `contextlib.redirect_stdout` 是**进程级**的，非线程安全；多个工具线程并发
    进入/退出会互相顶替 `sys.stdout`，最终可能把它留在一个被遗弃的缓冲区上。
    这里改成：每个线程可压入自己的缓冲区，`write` 只路由到「当前线程栈顶」的
    缓冲区；没有压栈的线程（如主线程）仍然写到真实流。
    """

    def __init__(self, real):
        self._real = real
        self._local = threading.local()

    def push(self, buffer) -> None:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = self._local.stack = []
        stack.append(buffer)

    def pop(self) -> None:
        stack = getattr(self._local, "stack", None)
        if stack:
            stack.pop()

    def _target(self):
        stack = getattr(self._local, "stack", None)
        return stack[-1] if stack else self._real

    def write(self, data):
        return self._target().write(data)

    def flush(self):
        try:
            self._target().flush()
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name):
        return getattr(self._real, name)


_CAPTURE_LOCK = threading.Lock()
_capture_depth = 0
_saved_streams = None
_stdout_proxy = None
_stderr_proxy = None


def _install_stream_capture() -> None:
    """（引用计数地）把 sys.stdout/stderr 换成线程路由代理。"""
    global _capture_depth, _saved_streams, _stdout_proxy, _stderr_proxy
    with _CAPTURE_LOCK:
        if _capture_depth == 0:
            _saved_streams = (sys.stdout, sys.stderr)
            _stdout_proxy = _ThreadLocalStream(sys.stdout)
            _stderr_proxy = _ThreadLocalStream(sys.stderr)
            sys.stdout = _stdout_proxy
            sys.stderr = _stderr_proxy
        _capture_depth += 1


def _uninstall_stream_capture() -> None:
    global _capture_depth
    with _CAPTURE_LOCK:
        if _capture_depth > 0:
            _capture_depth -= 1
        if _capture_depth == 0 and _saved_streams is not None:
            sys.stdout, sys.stderr = _saved_streams


class ToolsExecutor:
    """
    工具执行器
    """

    def __init__(self, max_workers: int = 5):
        self.events: AgentEvents = None
        self.sync_semaphore = threading.Semaphore(max_workers)
        self._async_semaphore = None
        self.max_workers = max_workers

    def execute(
        self,
        _tool_calls: list[dict],
        _tools,
        _mcp_client=None,
        events: AgentEvents = None,
        **kwargs,
    ):
        """
        执行工具调用（每个工具的超时由其自身的 Tool.timeout 决定）
        """
        if not _tool_calls:
            return []

        _tool_calls_result = [None] * len(_tool_calls)
        # 强制使用传入的 events，不进行 None 检查，异常将直接抛出
        active_events = events if events is not None else self.events

        # 记录原始索引并根据 index 排序（如有）
        indexed_calls = list(enumerate(_tool_calls))
        if "index" in _tool_calls[0]:
            indexed_calls.sort(key=lambda x: x[1].get("index", 0))

        def _worker(idx, tool_call):
            _tool_name = tool_call["function"]["name"]
            _tool_args_raw = tool_call["function"]["arguments"]
            _tool_id = tool_call["id"]
            _duration = None

            try:
                _tool_args = json.loads(_tool_args_raw)

                _tool_name, _tool_args = active_events.trigger_before_tool_call(
                    tool_name=_tool_name, tool_arguments=_tool_args
                )

                with self.sync_semaphore:
                    _t0 = time.perf_counter()
                    if _tool_name.startswith("mcp_"):
                        result = MCPToolExecutor.execute_mcp_tool(
                            _tool_name,
                            _tool_args,
                            _mcp_client,
                            _tool_timeout(_tools, _tool_name),
                        )
                    else:
                        _tool = _tools.get_tool(name=_tool_name)
                        # 同步模式下的核心执行与超时（按工具自身声明）
                        result = self._execute_sync_logic(
                            _tool_name,
                            _tool_args,
                            _tool,
                            _tool_timeout(_tools, _tool_name),
                            active_events,
                            _tools,
                        )
                    _duration = time.perf_counter() - _t0

                # After 钩子
                _, _, result = active_events.trigger_after_tool_call(
                    _tool_name, _tool_args, result
                )
            except Exception as e:
                logger.error(f"ToolsExecutor - 同步执行异常: {str(e)}")
                result = f"工具执行失败: {str(e)}"

            _tool_calls_result[idx] = self._tool_call_result(
                result, _tool_id, _tool_name, _duration
            )

        threads = [
            threading.Thread(target=_worker, args=(idx, call))
            for idx, call in indexed_calls
        ]
        _install_stream_capture()
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            _uninstall_stream_capture()

        return [res for res in _tool_calls_result if res is not None]

    async def aexecute(
        self,
        _tool_calls,
        _tools,
        _mcp_client=None,
        events: AgentEvents = None,
        **kwargs,
    ) -> any:
        if not _tool_calls:
            return []

        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(self.max_workers)

        active_events = events if events is not None else self.events
        indexed_calls = list(enumerate(_tool_calls))
        if "index" in _tool_calls[0]:
            indexed_calls.sort(key=lambda x: x[1].get("index", 0))

        async def _async_worker(idx, tool_call):
            _tool_name = tool_call["function"]["name"]
            _tool_args_raw = tool_call["function"]["arguments"]
            _tool_id = tool_call["id"]
            _duration = None

            try:
                _tool_args = json.loads(_tool_args_raw)
                # 强制触发，None 则 Crash
                _tool_name, _tool_args = await active_events.atrigger_before_tool_call(
                    tool_name=_tool_name, tool_arguments=_tool_args
                )

                async with self._async_semaphore:
                    _t0 = time.perf_counter()
                    if _tool_name.startswith("mcp_"):
                        result = await MCPToolExecutor.aexecute_mcp_tool(
                            _tool_name,
                            _tool_args,
                            _mcp_client,
                            _tool_timeout(_tools, _tool_name),
                        )
                    else:
                        _tool = _tools.get_tool(name=_tool_name)
                        tool_timeout = _tool_timeout(_tools, _tool_name)
                        if _tools.get_require_confirmations(_tool_name):
                            confirmed = (
                                await active_events.atrigger_on_tool_confirmation(
                                    _tool_name, _tool_args
                                )
                            )
                            if confirmed[0] is False:
                                result = confirmed[1]
                            else:
                                result = await self._async_dispatch(
                                    _tool_name, _tool_args, _tool, tool_timeout
                                )
                        else:
                            result = await self._async_dispatch(
                                _tool_name, _tool_args, _tool, tool_timeout
                            )
                    _duration = time.perf_counter() - _t0

                _, _, result = await active_events.atrigger_after_tool_call(
                    _tool_name, _tool_args, result
                )
            except Exception as e:
                logger.error(f"ToolsExecutor - 异步执行异常: {str(e)}")
                result = f"异步执行失败: {str(e)}"

            return idx, self._tool_call_result(
                result, _tool_id, _tool_name, _duration
            )

        tasks = [_async_worker(idx, call) for idx, call in indexed_calls]
        _install_stream_capture()
        try:
            done_results = await asyncio.gather(*tasks)
        finally:
            _uninstall_stream_capture()

        final_results = [None] * len(_tool_calls)
        for idx, res in done_results:
            final_results[idx] = res
        return final_results

    async def _async_dispatch(self, _tool_name, _tool_args, _tool, timeout):
        """异步分发逻辑：区分协程和同步函数；timeout<0 表示不限制"""
        if _tool is None:
            return f"工具 '{_tool_name}' 未找到"

        wait = None if (timeout is None or timeout < 0) else timeout

        try:
            if inspect.iscoroutinefunction(_tool):
                return await asyncio.wait_for(_tool(**_tool_args), timeout=wait)

            # 对于同步函数，run_in_executor 占用一个线程，asyncio.wait_for 负责超时监控
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self._raw_execute(_tool, _tool_args)
                ),
                timeout=wait,
            )
        except asyncio.TimeoutError:
            return f"工具执行超时（{timeout}秒）: {_tool_name}"

    def _raw_execute(self, _tool, _tool_args):
        """最底层的执行体：仅负责捕获输出，不负责线程管理"""
        output_buffer = io.StringIO()

        def _call():
            # 同步路径同样支持异步工具：把协程跑完
            if inspect.iscoroutinefunction(_tool):
                return self._run_coroutine(_tool(**_tool_args))
            return _tool(**_tool_args)

        try:
            if _stdout_proxy is not None and _stderr_proxy is not None:
                # 并发安全：按线程把输出路由到本线程的缓冲区
                _stdout_proxy.push(output_buffer)
                _stderr_proxy.push(output_buffer)
                try:
                    tool_result = _call()
                finally:
                    _stdout_proxy.pop()
                    _stderr_proxy.pop()
            else:
                with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                    tool_result = _call()

            full_output = output_buffer.getvalue()
            if tool_result is not None:
                if (
                    full_output.strip()
                    and str(tool_result).strip() != full_output.strip()
                ):
                    return f"{full_output}\n{tool_result}"
                return tool_result
            return full_output
        except Exception as e:
            return f"工具内部执行失败: {str(e)}"

    @staticmethod
    def _run_coroutine(coro):
        """在同步执行路径里跑完一个协程

        `_raw_execute` 通常跑在没有事件循环的线程里（`execute` 的工作线程，
        或异步路径的 `run_in_executor`），直接 `asyncio.run` 即可；若当前线程
        已经存在运行中的事件循环，则另开线程用独立循环执行，避免 `asyncio.run`
        直接抛 `RuntimeError`。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        box: dict = {}

        def _target():
            try:
                box["value"] = asyncio.run(coro)
            except BaseException as e:  # noqa: BLE001
                box["error"] = e

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join()
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _execute_sync_logic(
        self, _tool_name, _tool_args, _tool, timeout, active_events, _tools
    ):
        """同步模式下的逻辑包装（含确认和线程超时）"""
        if _tool is None:
            return f"工具 '{_tool_name}' 未找到"

        if _tools.get_require_confirmations(_tool_name):
            confirmed = active_events.trigger_on_tool_confirmation(
                _tool_name, _tool_args
            )
            if confirmed[0] is False:
                return confirmed[1]

        res = [f"工具执行超时（{timeout}秒）: {_tool_name}"]

        def target():
            res[0] = self._raw_execute(_tool, _tool_args)

        t = threading.Thread(target=target)
        t.daemon = True
        t.start()
        # timeout<0 表示不限制（卡死只能靠外部打断）
        if timeout is None or timeout < 0:
            t.join()
        else:
            t.join(timeout=timeout)
        return res[0]

    def _tool_call_result(self, _tool_result, _tool_id, _tool_name, duration=None):
        if isinstance(_tool_result, str) != True:
            _tool_result = str(_tool_result)
        result = {
            "role": "tool",
            "content": _tool_result,
            "tool_call_id": _tool_id,
            "tool_name": _tool_name,
        }
        if duration is not None:
            result["duration"] = round(duration, 3)
        return result
