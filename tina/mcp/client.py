import asyncio
import concurrent.futures
import json
import uuid
import threading
from typing import (
    Dict,
    List,
    Any,
    Optional,
    Union,
    Tuple,
    Literal,
    overload,
)
from contextlib import AsyncExitStack
from datetime import datetime
from ..core import logger  # 假设你有统一的logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import (
        streamable_http_client,
        create_mcp_http_client,
    )

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


# 远程传输类型别名：Streamable HTTP 在不同客户端里叫法不一，这里统一归一化。
# 官方新规范为 Streamable HTTP，`sse` 为旧版（已废弃）传输。
_REMOTE_TYPE_ALIASES = {
    "sse": "sse",
    "http": "http",
    "https": "http",
    "streamable_http": "http",
    "streamablehttp": "http",
    "streamable-http": "http",
}


def _normalize_server_type(server_type: str) -> str:
    return _REMOTE_TYPE_ALIASES.get(str(server_type).lower(), str(server_type).lower())


StdioType = Literal["stdio"]
RemoteType = Literal[
    "sse",
    "http",
    "https",
    "streamable_http",
    "streamableHttp",
    "streamable-http",
]


def _build_server_config(
    server_type: str,
    *,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """把扁平化参数组装为内部 config 字典，并做必要校验。"""
    stype = _normalize_server_type(server_type)
    if stype == "stdio":
        if not command:
            raise ValueError("stdio 类型必须提供 command 参数")
        config: Dict[str, Any] = {
            "type": "stdio",
            "command": command,
            "args": list(args) if args else [],
        }
        if env:
            config["env"] = dict(env)
        return config
    if stype in ("sse", "http"):
        if not url:
            raise ValueError(f"{server_type} 类型必须提供 url 参数")
        config = {"type": stype, "url": url}
        if headers:
            config["headers"] = dict(headers)
        return config
    raise ValueError(
        f"Unsupported server type: {server_type} "
        f"(supported: stdio, sse, http/streamable_http)"
    )


def _tool_input_schema(tool: Any) -> Dict[str, Any]:
    """获取 MCP 工具的输入 schema，兼容 SDK 的字段改名

    MCP Python SDK 早期版本用驼峰 `inputSchema`，新版本（pydantic 模型）改为
    下划线 `input_schema`。这里两种都取，取不到返回空 dict。
    """
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    return schema or {}


def _normalize_property(prop: Any) -> Dict[str, Any]:
    """将单个 MCP 属性 schema 归一化为 Tina/大模型友好的形式。

    修复原先只保留 `type` 且缺省退化为 Python 类型名 ``"str"`` 的问题：
    - 缺少顶层 `type` 时，从 enum / anyOf 推断，最后回退为 JSON Schema 的
      ``"string"``，不再输出 ``"str"``；
    - 保留 `enum` 等约束信息，避免模型失去取值范围；
    - 将带 null 的 `anyOf`/`oneOf` 及 ``["string", "null"]`` 形式的 type
      压平为 `type` + `nullable`，提升对不支持联合类型的模型兼容性。
    """
    prop = dict(prop) if isinstance(prop, dict) else {}
    description = prop.get("description", "")

    # 压平 nullable 联合类型（例如 zod 的 z.enum([...]).nullable()）
    variants = prop.get("anyOf") or prop.get("oneOf")
    if isinstance(variants, list):
        non_null = [
            v for v in variants if isinstance(v, dict) and v.get("type") != "null"
        ]
        has_null = any(
            isinstance(v, dict) and v.get("type") == "null" for v in variants
        )
        if len(non_null) == 1 and has_null:
            merged = dict(non_null[0])
            merged.setdefault("description", description)
            merged["nullable"] = True
            return _normalize_property(merged)

    # 压平 type 为数组的形式，如 ["string", "null"]
    raw_type = prop.get("type")
    if isinstance(raw_type, list):
        types = [t for t in raw_type if t != "null"]
        prop["nullable"] = prop.get("nullable", "null" in raw_type)
        if len(types) == 1:
            prop["type"] = types[0]
        else:
            prop.pop("type", None)

    # 缺少 type 时从 enum 推断，否则回退 "string"（而非 Python 的 "str"）
    if "type" not in prop:
        values = prop.get("enum")
        if isinstance(values, list) and values:
            if all(isinstance(v, str) for v in values):
                prop["type"] = "string"
            elif all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in values
            ):
                prop["type"] = "number"
        elif not (
            prop.get("anyOf") or prop.get("oneOf") or prop.get("$ref")
        ):
            prop["type"] = "string"

    prop["description"] = description
    return prop


def _convert_input_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """将 MCP 工具的 input schema.properties 转为 Tina 工具参数格式"""
    properties = schema.get("properties", {}) or {}
    return {name: _normalize_property(prop) for name, prop in properties.items()}


class MCPClient:
    def __init__(self):
        if not MCP_AVAILABLE:
            raise ImportError("请先安装MCP依赖: pip install mcp")

        self.servers = (
            {}
        )  # {server_id: {"session": s, "tools": [], "config": {}, "stop": Event}}
        self.request_history = []
        self._server_futures = {}  # {server_id: concurrent.futures.Future}
        self._server_configs = {}  # {server_id: add_server 的 kwargs，掉线时用它重连}
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
            server_type = _normalize_server_type(config.get("type", ""))
            headers = config.get("headers") or None
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
                transport = await stack.enter_async_context(
                    sse_client(config["url"], headers=headers)
                )
                session = await stack.enter_async_context(
                    ClientSession(transport[0], transport[1])
                )
            elif server_type == "http":
                # Streamable HTTP：单端点，取代旧的 SSE 传输。
                # headers 需通过预配置的 httpx 客户端传入；该客户端由 stack 负责关闭。
                http_client = create_mcp_http_client(headers=headers)
                await stack.enter_async_context(http_client)
                transport = await stack.enter_async_context(
                    streamable_http_client(config["url"], http_client=http_client)
                )
                session = await stack.enter_async_context(
                    ClientSession(transport[0], transport[1])
                )
            else:
                raise ValueError(
                    f"Unsupported server type: {server_type} "
                    f"(supported: stdio, sse, http/streamable_http)"
                )

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

    @overload
    def add_server(
        self,
        server_id: str,
        *,
        type: StdioType,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        max_retries: int = 1,
        timeout: int = 90,
    ) -> bool: ...

    @overload
    def add_server(
        self,
        server_id: str,
        *,
        type: RemoteType,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 1,
        timeout: int = 90,
    ) -> bool: ...

    def add_server(
        self,
        server_id: str,
        *,
        type: str,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 1,
        timeout: int = 90,
    ) -> bool:
        """添加并连接一个 MCP 服务器，失败时按 max_retries 重试。

        参数按传输类型扁平化：

        - ``type="stdio"``：需要 ``command``，可选 ``args`` / ``env``。
        - ``type="http"``（或 ``streamable_http`` 等别名）/ ``type="sse"``：
          需要 ``url``，可选 ``headers``。
        """
        config = _build_server_config(
            type,
            command=command,
            args=args,
            env=env,
            url=url,
            headers=headers,
        )

        # 记住配置：会话掉线后可按需重连
        with self._lock:
            self._server_configs[server_id] = {
                "type": type,
                "command": command,
                "args": args,
                "env": env,
                "url": url,
                "headers": headers,
                "max_retries": max_retries,
                "timeout": timeout,
            }
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
            # 显式移除后不再自动重连
            self._server_configs.pop(server_id, None)
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

    def _ensure_connected(self, server_id: str) -> bool:
        """该 server 掉线时，用记住的配置尝试重连；返回是否已连接。"""
        if server_id in self.servers:
            return True
        with self._lock:
            kwargs = self._server_configs.get(server_id)
        if not kwargs:
            return False
        logger.warning(f"MCP - 服务器 '{server_id}' 未连接，尝试重连…")
        return bool(self.add_server(server_id, **kwargs))

    def submit_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        server_id: Optional[str] = None,
    ) -> concurrent.futures.Future:
        """把一次 MCP 工具调用调度到 MCP 自己的事件循环上，返回 concurrent future。

        执行体始终跑在 MCP 专用 loop 线程，调用方只拿到 future：
        - 同步：``future.result(timeout)``
        - 异步：``asyncio.wrap_future(future)`` 后再 ``wait_for``
        timeout<0 表示不限制。
        """
        if server_id is not None:
            self._ensure_connected(server_id)
        return asyncio.run_coroutine_threadsafe(
            self._call_tool_async(tool_name, tool_args, server_id), self.loop
        )

    def call_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        server_id: Optional[str] = None,
        timeout=60,
    ):
        future = self.submit_tool_call(tool_name, tool_args, server_id)
        if timeout is None or timeout < 0:
            return future.result()
        return future.result(timeout=timeout)

    # --- 异步接口 (a开头，保持Tina风格) ---

    async def acall_tool(
        self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None
    ):
        future = self.submit_tool_call(tool_name, tool_args, server_id)
        return await asyncio.wrap_future(future)

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
            detail = f"（server={target_sid}）" if target_sid else "（未找到所属 server）"
            return {
                "success": False,
                "error": f"服务器未连接，无法调用 {tool_name}{detail}",
            }

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
                    tina_tools.register_no_function(
                        name=f"{sid}_{tool.name}",  # 外部包名是mcp，内部就是 mcp_sid_name
                        description=f"[MCP:{sid}] {tool.description}",
                        parameters=_convert_input_schema(schema),
                        required_parameters=schema.get("required", []) or [],
                        original_name=tool.name,  # 反查时按纯工具名匹配
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
