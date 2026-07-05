"""
编写者：王出日
日期：2026, 02, 13
版本：0.5.3
功能：Agent的工具执行器
"""

import io
from contextlib import redirect_stdout, redirect_stderr
import threading
import json
import asyncio
import inspect
from ...mcp.mcp_tools_executor import MCPToolExecutor

from .events import AgentEvents
from ...core import logger


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
        timeout=60,
        events: AgentEvents = None,
        **kwargs,
    ):
        """
        执行工具调用
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

            try:
                _tool_args = json.loads(_tool_args_raw)

                _tool_name, _tool_args = active_events.trigger_before_tool_call(
                    tool_name=_tool_name, tool_arguments=_tool_args
                )

                with self.sync_semaphore:
                    if _tool_name.startswith("mcp_"):
                        result = MCPToolExecutor.execute_mcp_tool(
                            _tool_name, _tool_args, _mcp_client
                        )
                    else:
                        _tool = _tools.get_tool(name=_tool_name)
                        # 同步模式下的核心执行与超时
                        result = self._execute_sync_logic(
                            _tool_name,
                            _tool_args,
                            _tool,
                            timeout,
                            active_events,
                            _tools,
                        )

                # After 钩子
                _, _, result = active_events.trigger_after_tool_call(
                    _tool_name, _tool_args, result
                )
            except Exception as e:
                logger.error(f"ToolsExecutor - 同步执行异常: {str(e)}")
                result = f"工具执行失败: {str(e)}"

            _tool_calls_result[idx] = self._tool_call_result(
                result, _tool_id, _tool_name
            )

        threads = [
            threading.Thread(target=_worker, args=(idx, call))
            for idx, call in indexed_calls
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return [res for res in _tool_calls_result if res is not None]

    async def aexecute(
        self,
        _tool_calls,
        _tools,
        _mcp_client=None,
        timeout=60,
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

            try:
                _tool_args = json.loads(_tool_args_raw)
                # 强制触发，None 则 Crash
                _tool_name, _tool_args = await active_events.atrigger_before_tool_call(
                    tool_name=_tool_name, tool_arguments=_tool_args
                )

                async with self._async_semaphore:
                    if _tool_name.startswith("mcp_"):
                        result = await MCPToolExecutor.aexecute_mcp_tool(
                            _tool_name, _tool_args, _mcp_client
                        )
                    else:
                        _tool = _tools.get_tool(name=_tool_name)
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
                                    _tool_name, _tool_args, _tool, timeout
                                )
                        else:
                            result = await self._async_dispatch(
                                _tool_name, _tool_args, _tool, timeout
                            )

                _, _, result = await active_events.atrigger_after_tool_call(
                    _tool_name, _tool_args, result
                )
            except Exception as e:
                logger.error(f"ToolsExecutor - 异步执行异常: {str(e)}")
                result = f"异步执行失败: {str(e)}"

            return idx, self._tool_call_result(result, _tool_id, _tool_name)

        tasks = [_async_worker(idx, call) for idx, call in indexed_calls]
        done_results = await asyncio.gather(*tasks)

        final_results = [None] * len(_tool_calls)
        for idx, res in done_results:
            final_results[idx] = res
        return final_results

    async def _async_dispatch(self, _tool_name, _tool_args, _tool, timeout):
        """异步分发逻辑：区分协程和同步函数"""
        if _tool is None:
            return f"工具 '{_tool_name}' 未找到"

        if inspect.iscoroutinefunction(_tool):
            return await asyncio.wait_for(_tool(**_tool_args), timeout=timeout)

        # 对于同步函数，run_in_executor 占用一个线程，asyncio.wait_for 负责超时监控
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self._raw_execute(_tool, _tool_args)
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return f"工具执行超时（{timeout}秒）: {_tool_name}"

    def _raw_execute(self, _tool, _tool_args):
        """最底层的执行体：仅负责捕获输出，不负责线程管理"""
        output_buffer = io.StringIO()
        try:
            with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                tool_result = _tool(**_tool_args)

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
        t.join(timeout=timeout)
        return res[0]

    def _execute(
        self, _tool_name: str, _tool_args: dict, _tool: callable, _tools, timeout=60
    ):
        # 兼容性封装
        return self._execute_sync_logic(
            _tool_name, _tool_args, _tool, timeout, self.events, _tools
        )

    async def _aexecute_single(self, _tool_name, _tool_args, _tool, _tools, timeout=60):
        # 兼容性封装
        return await self._async_dispatch(_tool_name, _tool_args, _tool, timeout)

    def _tool_call_result(self, _tool_result, _tool_id, _tool_name):
        if isinstance(_tool_result, str) != True:
            _tool_result = str(_tool_result)
        return {
            "role": "tool",
            "content": _tool_result,
            "tool_call_id": _tool_id,
            "tool_name": _tool_name,
        }
