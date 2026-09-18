import asyncio
import concurrent.futures
import json
import uuid
import threading
from typing import Dict, List, Any, Optional, Union, Tuple
from contextlib import AsyncExitStack
from datetime import datetime
from ..core import logger  # 假设你有统一的logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


def _tool_input_schema(tool: Any) -> Dict[str, Any]:
    """获取 MCP 工具的输入 schema，兼容 SDK 的字段改名

    MCP Python SDK 早期版本用驼峰 `inputSchema`，新版本（pydantic 模型）改为
    下划线 `input_schema`。这里两种都取，取不到返回空 dict。
    """
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    return schema or {}


class MCPClient:
    def __init__(self):
        if not MCP_AVAILABLE:
            raise ImportError("请先安装MCP依赖: pip install mcp")

        self.servers = (
            {}
        )  # {server_id: {"session": s, "tools": [], "config": {}, "stop": Event}}
        self.request_history = []
        self._server_futures = {}  # {server_id: concurrent.futures.Future}
        self.loop = asyncio.new_event_loop()
        self._loop_is_running = False
        self._lock = threading.Lock()  # 保护 servers 字典的线程安全

        self.start_loop_thread()

    def start_loop_thread(self):
        """启动专用后台线程运行事件循环"""

        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            self._loop_is_running = True
            try:
                self.loop.run_forever()
            finally:
                # 最后的清理逻辑
                self._loop_is_running = False
                self.loop.close()

        thread = threading.Thread(target=run_event_loop, daemon=True)
        thread.start()

    # --- 核心内部异步实现 ---

    async def _serve_server(
        self,
        server_id: str,
        config: Dict[str, Any],
        ready: concurrent.futures.Future,
    ) -> None:
        """在同一个 task 内完成 MCP 会话的进入与退出。

        mcp 2.x 基于 anyio，context 的进入/退出必须在同一个 task，
        否则退出时会报 "Attempted to exit cancel scope in a different task"。
        因此这里用一个常驻 task 持有会话，直到 stop 事件触发再统一关闭。
        """
        stack = AsyncExitStack()
        stop = asyncio.Event()
        try:
            server_type = config.get("type", "").lower()
            if server_type == "stdio":
                params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env"),
                )
                transport = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(
                    ClientSession(transport[0], transport[1])
                )
            elif server_type == "sse":
                transport = await stack.enter_async_context(sse_client(config["url"]))
                session = await stack.enter_async_context(
                    ClientSession(transport[0], transport[1])
                )
            else:
                raise ValueError(f"Unsupported server type: {server_type}")

            await session.initialize()
            res = await session.list_tools()

            with self._lock:
                self.servers[server_id] = {
                    "session": session,
                    "tools": res.tools,
                    "config": config,
                    "added_at": datetime.now(),
                    "stop": stop,
                }

            ready.set_result(True)
            await stop.wait()
        except Exception as e:
            logger.error(f"MCP Server Error [{server_id}]: {e}")
            if not ready.done():
                ready.set_result(False)
        finally:
            with self._lock:
                self.servers.pop(server_id, None)
                self._server_futures.pop(server_id, None)
            try:
                await stack.aclose()
            except Exception as e:
                logger.error(f"MCP Cleanup Error [{server_id}]: {e}")

    # --- 同步接口桥接 ---

    def add_server(
        self,
        server_id: str,
        config: Dict[str, Any],
        max_retries: int = 1,
        timeout: int = 90,
    ) -> bool:
        """添加并连接一个 MCP 服务器，失败时按 max_retries 重试"""
        with self._lock:
            if server_id in self.servers:
                return True

        for attempt in range(1, max(1, max_retries) + 1):
            ready: concurrent.futures.Future = concurrent.futures.Future()
            future = asyncio.run_coroutine_threadsafe(
                self._serve_server(server_id, config, ready), self.loop
            )
            try:
                ok = ready.result(timeout=timeout)
            except Exception as e:
                logger.error(f"Sync add_server timeout/error [{server_id}]: {e}")
                ok = False

            if ok:
                with self._lock:
                    self._server_futures[server_id] = future
                return True

            if attempt < max_retries:
                logger.warning(
                    f"MCP 添加服务器 '{server_id}' 第 {attempt} 次失败，重试中..."
                )
        return False

    def remove_server(self, server_id: str, timeout: int = 10) -> bool:
        """移除服务器并等待其资源（子进程/连接）释放"""
        with self._lock:
            info = self.servers.get(server_id)
            if info is None:
                return False
            stop = info["stop"]
            future = self._server_futures.get(server_id)

        self.loop.call_soon_threadsafe(stop.set)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logger.error(f"Sync remove_server timeout/error [{server_id}]: {e}")
        return True

    @staticmethod
    def _format_server_info(server_id: str, info: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "server_id": server_id,
            "config": info["config"],
            "tools": [t.name for t in info["tools"]],
            "added_at": info["added_at"].isoformat(),
        }

    def get_server_info(
        self, server_id: Optional[str] = None
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """获取已连接 MCP 服务器的信息；不传 server_id 时返回全部"""
        with self._lock:
            if server_id is not None:
                info = self.servers.get(server_id)
                return self._format_server_info(server_id, info) if info else None
            return [
                self._format_server_info(sid, info)
                for sid, info in self.servers.items()
            ]

    def call_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        server_id: Optional[str] = None,
        timeout=60,
    ):
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(tool_name, tool_args, server_id), self.loop
        )
        return future.result(timeout=timeout)

    # --- 异步接口 (a开头，保持Tina风格) ---

    async def acall_tool(
        self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None
    ):
        return await self._call_tool_async(tool_name, tool_args, server_id)

    async def _call_tool_async(
        self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None
    ):
        target_sid = server_id
        # 自动寻址逻辑
        if not target_sid:
            with self._lock:
                for sid, info in self.servers.items():
                    if any(t.name == tool_name for t in info["tools"]):
                        target_sid = sid
                        break

        if not target_sid or target_sid not in self.servers:
            return {"success": False, "error": f"Tool {tool_name} not found"}

        session = self.servers[target_sid]["session"]
        try:
            # 记录历史
            res = await session.call_tool(tool_name, tool_args)
            # 这里统一处理结果，避免 TextContent 对象导致后续 JSON 序列化失败

            history_item = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "server": target_sid,
                "success": True,
            }
            self.request_history.append(history_item)

            return {"success": True, "content": res.content, "server_id": target_sid}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_tina_tools(self):
        """
        将当前已连接的所有 MCP 工具转换为 Tina 格式
        确保指定 name="mcp" 以避免 ToolsNotNamed 异常
        """
        from ..agent.core.tools import Tools

        # 必须指定 name，这样 self.tools = _tools + self.tools 才能正常工作
        tina_tools = Tools(name="mcp")

        with self._lock:
            for sid, info in self.servers.items():
                for tool in info["tools"]:
                    # 注意：Tina Tools 内部可能还会根据包名加一层前缀
                    # 这里的 register_no_function 保持你习惯的格式
                    schema = _tool_input_schema(tool)
                    properties = schema.get("properties", {}) or {}
                    tina_tools.register_no_function(
                        name=f"{sid}_{tool.name}",  # 外部包名是mcp，内部就是 mcp_sid_name
                        description=f"[MCP:{sid}] {tool.description}",
                        parameters={
                            k: {
                                "type": v.get("type", "str"),
                                "description": v.get("description", ""),
                            }
                            for k, v in properties.items()
                        },
                        required_parameters=schema.get("required", []) or [],
                    )
        return tina_tools

    def close(self):
        """优雅关闭所有资源"""
        if not self._loop_is_running:
            return

        with self._lock:
            ids = list(self.servers.keys())

        # 通知各 server 的常驻 task 退出，并在原 task 内完成资源清理
        for sid in ids:
            self.remove_server(sid)

        self.loop.call_soon_threadsafe(self.loop.stop)

    def __del__(self):
        # 析构时尽量尝试静默关闭
        try:
            if hasattr(self, "loop") and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)
        except:
            pass
