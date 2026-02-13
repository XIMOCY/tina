import asyncio
import json
import uuid
import threading
from typing import Dict, List, Any, Optional, Union, Tuple
from contextlib import AsyncExitStack
from datetime import datetime
from ..core import logger # 假设你有统一的logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

class MCPClient:
    def __init__(self):
        if not MCP_AVAILABLE:
            raise ImportError("请先安装MCP依赖: pip install mcp-python")
            
        self.servers = {}  # {server_id: {"session": s, "stack": stack, "tools": [], "config": {}}}
        self.request_history = []
        self.loop = asyncio.new_event_loop()
        self._loop_is_running = False
        self._lock = threading.Lock() # 保护 servers 字典的线程安全
        
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

    # --- 核心内部异步实现 (解决资源残留) ---

    async def _add_server_async(self, server_id: str, config: Dict[str, Any]) -> bool:
        if server_id in self.servers:
            return True
        
        # 为每个 Server 创建独立的 Stack
        stack = AsyncExitStack()
        try:
            server_type = config.get("type", "").lower()
            if server_type == "stdio":
                params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env")
                )
                # 进入 stdio 上下文 (管理子进程)
                transport = await stack.enter_async_context(stdio_client(params))
                # 进入 session 上下文 (管理协议)
                session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
            elif server_type == "sse":
                transport = await stack.enter_async_context(sse_client(config["url"]))
                session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
            else:
                raise ValueError(f"Unsupported server type: {server_type}")

            await session.initialize()
            res = await session.list_tools()

            with self._lock:
                self.servers[server_id] = {
                    "session": session,
                    "stack": stack, # 这里的 stack 包含了这个 server 的所有资源
                    "tools": res.tools,
                    "config": config,
                    "added_at": datetime.now()
                }
            return True
        except Exception as e:
            await stack.aclose() # 出错时立即清理已打开的资源
            logger.error(f"MCP Add Server Error [{server_id}]: {e}")
            return False

    async def _close_server_async(self, server_id: str) -> bool:
        """物理杀掉子进程并移除服务器"""
        with self._lock:
            server_info = self.servers.pop(server_id, None)
            
        if server_info:
            # 这一步是关键：调用 stack.aclose() 会按相反顺序关闭 session 和 transport
            # 对于 stdio 来说，这会发送信号给子进程并等待其退出
            await server_info["stack"].aclose()
            return True
        return False

    # --- 同步接口桥接 ---

    def add_server(self, server_id: str, config: Dict[str, Any], timeout=30) -> bool:
        future = asyncio.run_coroutine_threadsafe(self._add_server_async(server_id, config), self.loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            logger.error(f"Sync add_server timeout/error: {e}")
            return False

    def call_tool(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None, timeout=60):
        future = asyncio.run_coroutine_threadsafe(self._call_tool_async(tool_name, tool_args, server_id), self.loop)
        return future.result(timeout=timeout)

    # --- 异步接口 (a开头，保持Tina风格) ---

    async def acall_tool(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None):
        return await self._call_tool_async(tool_name, tool_args, server_id)

    async def _call_tool_async(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None):
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
            processed_content = []
            for item in res.content:
                if hasattr(item, 'text'):
                    processed_content.append({"type": "text", "text": item.text})
                else:
                    processed_content.append(str(item))

            history_item = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "server": target_sid,
                "success": True
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
                    tina_tools.register_no_function(
                        name=f"{sid}_{tool.name}", # 外部包名是mcp，内部就是 mcp_sid_name
                        description=f"[MCP:{sid}] {tool.description}",
                        parameters={
                            k: {
                                "type": v.get("type", "str"), 
                                "description": v.get("description", "")
                            } 
                            for k, v in tool.inputSchema.get("properties", {}).items()
                        },
                        required_parameters=tool.inputSchema.get("required", [])
                    )
        return tina_tools

    def close(self):
        """优雅关闭所有资源"""
        if self._loop_is_running:
            # 获取所有服务器 ID
            with self._lock:
                ids = list(self.servers.keys())
            
            # 提交清理任务
            tasks = [self._close_server_async(sid) for sid in ids]
            future = asyncio.run_coroutine_threadsafe(asyncio.gather(*tasks), self.loop)
            future.result(timeout=10)
            
            # 停止循环
            self.loop.call_soon_threadsafe(self.loop.stop)

    def __del__(self):
        # 析构时尽量尝试静默关闭
        try:
            if hasattr(self, 'loop') and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)
        except:
            pass