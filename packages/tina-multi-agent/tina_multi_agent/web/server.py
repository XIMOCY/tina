import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..environment import MultiAgentEnvironment


_STATIC_DIR = Path(__file__).parent / "static"
_CHUNK_FIELDS = (
    "role",
    "content",
    "reasoning_content",
    "tool_name",
    "tool_arguments",
    "tool_calls",
    "tool_index",
    "tool_call_id",
    "usage",
    "timing",
    "duration",
)


class MultiAgentWeb:
    """
    多 Agent 的简易 Web 观测 / 交互前端。

    用法：
        web = MultiAgentWeb(env, host="127.0.0.1", port=7077)
        web.run()          # 启动环境 + Web 服务

    数据来源：
    - 消息记录来自 env.history()（总线历史）；
    - 实时输出通过给每个 Agent 注册 on_stream_chunk / on_turn_end 事件转发。
    环境本身不感知事件，事件由本层挂载。
    """

    def __init__(
        self,
        environment: "MultiAgentEnvironment",
        host: str = "127.0.0.1",
        port: int = 7077,
        tool_confirmation: str = "ask",
        confirm_timeout: float = 300.0,
    ):
        self.env = environment
        self.host = host
        self.port = port
        self.tool_confirmation = tool_confirmation
        self.confirm_timeout = confirm_timeout
        self._clients: set = set()
        self._events_attached = False
        self._pending_confirmations: dict = {}
        # 工具权限：{agent_name: {tool_name: "allow" | "deny"}}，缺省为 ask
        self._permissions: dict = {}
        self.app = self._build_app()

    def _build_app(self):
        try:
            from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
            from fastapi.responses import HTMLResponse
        except ImportError as error:
            raise ImportError(
                "使用 Web 前端需要安装：pip install tina-python[web]"
            ) from error

        app = FastAPI(title="tina multi-agent")

        @app.get("/")
        async def index():
            html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
            return HTMLResponse(html)

        @app.get("/favicon.svg")
        @app.get("/favicon.ico")
        async def favicon():
            svg = (_STATIC_DIR / "favicon.svg").read_text(encoding="utf-8")
            return Response(svg, media_type="image/svg+xml")

        @app.get("/health")
        async def health():
            return {
                "ok": True,
                "agents": self.env.agent_names,
                "running": getattr(self.env, "_running", False),
            }

        @app.post("/instruction")
        async def instruction(payload: dict):
            """外部（如 opencode）向多 Agent 环境投放指令。

            body: {"content": str, "main_agent": str | null}
            main_agent 为空时广播给所有 Agent。
            """
            content = (payload.get("content") or "").strip()
            if not content:
                return {"ok": False, "error": "content 不能为空"}
            main_agent = payload.get("main_agent") or None
            try:
                message = self.env.predict(content, main_agent=main_agent)
            except Exception as error:
                return {"ok": False, "error": str(error)}
            return {
                "ok": True,
                "sender": message.sender,
                "recipient": message.recipient,
                "content": message.content,
            }

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self._clients.add(websocket)
            try:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "init",
                            "agents": self.env.agent_names,
                            "messages": [
                                self._message_to_dict(message)
                                for message in self.env.history()
                            ],
                            "permissions": self._permission_snapshot(),
                            "confirmable_tools": self._confirmable_tools(),
                            "queues": self._queue_snapshot(),
                            "backend_error": self.env.backend_error,
                        },
                        ensure_ascii=False,
                    )
                )
                while True:
                    raw = await websocket.receive_text()
                    await self._handle_client_message(raw)
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    async def _handle_client_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if data.get("type") == "confirm_result":
            await self._resolve_confirmation(data)
            return
        if data.get("type") == "set_permission":
            if self._apply_permission(data):
                await self._broadcast_permissions()
            return
        if data.get("type") == "interrupt":
            await self._handle_interrupt(data.get("agent") or None)
            return
        if data.get("type") == "get_queues":
            await self._broadcast(
                {"type": "queues", "queues": self._queue_snapshot()}
            )
            return
        if data.get("type") != "instruction":
            return
        content = (data.get("content") or "").strip()
        if not content:
            return
        main_agent = data.get("main_agent") or None
        try:
            self.env.predict(content, main_agent=main_agent)
        except Exception as error:
            await self._broadcast({"type": "error", "message": str(error)})

    def _attach_agent_events(self) -> None:
        if self._events_attached:
            return
        self._events_attached = True

        def make_stream_handler(agent_name: str):
            async def on_stream_chunk(response):
                await self._broadcast(
                    {
                        "type": "chunk",
                        "agent": agent_name,
                        "chunk": self._chunk_to_dict(response),
                    }
                )

            return on_stream_chunk

        def make_turn_end_handler(agent_name: str):
            async def on_turn_end():
                await self._broadcast({"type": "turn_end", "agent": agent_name})

            return on_turn_end

        def make_confirm_handler(agent_name: str):
            async def on_tool_confirmation(tool_name, tool_arguments):
                return await self._request_confirmation(
                    agent_name, tool_name, tool_arguments
                )

            return on_tool_confirmation

        for agent_name, agent in self.env.agents.items():
            agent.add_on_stream_chunk_handler(make_stream_handler(agent_name))
            agent.add_on_turn_end_handler(make_turn_end_handler(agent_name))
            agent.add_on_tool_confirmation_handler(make_confirm_handler(agent_name))

    async def _request_confirmation(self, agent_name, tool_name, tool_arguments):
        """向前端请求一次工具执行确认；返回 True 或 (False, 原因)。"""
        if self.tool_confirmation == "allow":
            return True
        if self.tool_confirmation == "deny":
            return (False, "已按配置拒绝该工具")

        setting = self._permissions.get(agent_name, {}).get(tool_name)
        if setting == "allow":
            return True
        if setting == "deny":
            return (False, "已按权限设置始终拒绝该工具")

        if not self._clients:
            return (False, "当前没有前端在线，无法确认，已拒绝")

        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending_confirmations[request_id] = {
            "future": future,
            "agent": agent_name,
            "tool": tool_name,
        }
        await self._broadcast(
            {
                "type": "confirm",
                "request_id": request_id,
                "agent": agent_name,
                "tool_name": tool_name,
                "tool_arguments": tool_arguments,
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=self.confirm_timeout)
        except asyncio.TimeoutError:
            return (False, "确认超时，已拒绝")
        finally:
            self._pending_confirmations.pop(request_id, None)

    async def _resolve_confirmation(self, data: dict) -> None:
        entry = self._pending_confirmations.get(data.get("request_id"))
        if entry is None:
            return
        future = entry["future"]
        if future.done():
            return
        remember = data.get("remember")
        if remember in ("allow", "deny"):
            if self._set_permission(entry["agent"], entry["tool"], remember):
                await self._broadcast_permissions()
        if data.get("allowed"):
            future.set_result(True)
        else:
            future.set_result((False, data.get("reason") or "用户拒绝执行该工具"))

    def _permission_snapshot(self) -> dict:
        return {agent: dict(tools) for agent, tools in self._permissions.items()}

    def _confirmable_tools(self) -> dict:
        """每个 Agent 需要确认的工具清单（名称 + 描述）"""
        result = {}
        for name, agent in self.env.agents.items():
            entries = []
            tools = getattr(agent, "tools", None)
            if tools is not None:
                for tool in tools.tools:
                    if getattr(tool, "require_confirmation", False):
                        entries.append(
                            {
                                "name": tool.name,
                                "description": getattr(tool, "description", "") or "",
                            }
                        )
            result[name] = entries
        return result

    def _set_permission(self, agent_name: str, tool_name: str, value: str) -> bool:
        """设置 (agent, tool) 权限；返回是否发生变化。"""
        bucket = self._permissions.setdefault(agent_name, {})
        current = bucket.get(tool_name, "ask")
        if value == "ask":
            if tool_name in bucket:
                bucket.pop(tool_name)
                if not bucket:
                    self._permissions.pop(agent_name, None)
                return True
            return False
        if current == value:
            return False
        bucket[tool_name] = value
        return True

    def _apply_permission(self, data: dict) -> bool:
        tool_name = data.get("tool")
        value = data.get("value")
        if not tool_name or value not in ("allow", "deny", "ask"):
            return False
        if data.get("scope") == "all":
            changed = False
            for name in self.env.agent_names:
                changed = self._set_permission(name, tool_name, value) or changed
            return changed
        agent_name = data.get("agent")
        if not agent_name:
            return False
        return self._set_permission(agent_name, tool_name, value)

    async def _broadcast_permissions(self) -> None:
        await self._broadcast(
            {
                "type": "permissions",
                "permissions": self._permission_snapshot(),
                "confirmable_tools": self._confirmable_tools(),
            }
        )

    async def _handle_interrupt(self, agent_name) -> None:
        """打断某个（或全部）Agent 当前正在进行的输出。"""
        if agent_name:
            ok = self.env.interrupt(agent_name)
        else:
            ok = self.env.interrupt_all() > 0
        await self._cancel_confirmations(agent_name)
        await self._broadcast(
            {"type": "interrupted", "agent": agent_name, "ok": bool(ok)}
        )

    async def _cancel_confirmations(self, agent_name) -> None:
        """取消该 Agent（或全部）还挂着的工具确认请求。"""
        cancelled = []
        for request_id, entry in list(self._pending_confirmations.items()):
            if agent_name and entry.get("agent") != agent_name:
                continue
            future = entry.get("future")
            if future is not None and not future.done():
                future.set_result((False, "该工具调用已被打断"))
            self._pending_confirmations.pop(request_id, None)
            cancelled.append(request_id)
        if cancelled:
            await self._broadcast(
                {"type": "confirm_cancel", "request_ids": cancelled}
            )

    async def _on_bus_message(self, message) -> None:
        await self._broadcast(
            {"type": "message", "message": self._message_to_dict(message)}
        )

    def _queue_snapshot(self) -> dict:
        """每个 Agent 的消息队列快照：{名称: [{消息..., active}]}，按先后顺序。"""
        snapshot = {}
        for name in self.env.agent_names:
            active = self.env.active_message(name)
            entries = []
            for message in self.env.pending_messages(name):
                item = self._message_to_dict(message)
                item["active"] = message is active
                entries.append(item)
            snapshot[name] = entries
        return snapshot

    async def _on_queue_change(self) -> None:
        await self._broadcast(
            {"type": "queues", "queues": self._queue_snapshot()}
        )

    def _notify_queue_change(self) -> None:
        """环境队列变化回调：在当前事件循环里异步推送队列快照。"""
        if not self._clients:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._on_queue_change())

    def _notify_bus_message(self, message) -> None:
        """MessageBus 的同步监听器：在当前事件循环里异步推送消息。"""
        if not self._clients:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._on_bus_message(message))

    async def _on_turn_error(self, name: str, error, info: dict) -> None:
        """Agent 一轮推理失败：把「谁、为什么」推给前端。"""
        await self._broadcast(
            {
                "type": "error",
                "agent": name,
                "kind": info.get("kind"),
                "fatal": bool(info.get("fatal")),
                "message": info.get("message") or str(error),
                "backend": self.env.backend_error,
            }
        )

    def _notify_turn_error(self, name: str, error, info: dict) -> None:
        """环境回合失败回调：在当前事件循环里异步推送。"""
        if not self._clients:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._on_turn_error(name, error, info))

    async def _broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        text = json.dumps(payload, ensure_ascii=False)
        for websocket in list(self._clients):
            try:
                await websocket.send_text(text)
            except Exception:
                self._clients.discard(websocket)

    @staticmethod
    def _chunk_to_dict(response) -> dict:
        data = dict(response)
        return {key: data[key] for key in _CHUNK_FIELDS if key in data}

    @staticmethod
    def _message_to_dict(message) -> dict:
        return {
            "sender": message.sender,
            "recipient": message.recipient,
            "content": message.content,
            "role": message.role,
        }

    async def serve(self, start_env: bool = True) -> None:
        """异步启动：可选代启环境，然后运行 Web 服务直到退出。"""
        try:
            import uvicorn
        except ImportError as error:
            raise ImportError(
                "使用 Web 前端需要安装：pip install tina-python[web]"
            ) from error

        if start_env:
            await self.env.start()
        self._attach_agent_events()
        self.env.bus.add_listener(self._notify_bus_message)
        self.env.add_queue_listener(self._notify_queue_change)
        self.env.add_error_listener(self._notify_turn_error)
        print(f"tina-多Agent调试控制台运行中: http://{self.host}:{self.port}")
        server = uvicorn.Server(
            uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        )
        try:
            await server.serve()
        finally:
            self.env.bus.remove_listener(self._notify_bus_message)
            self.env.remove_queue_listener(self._notify_queue_change)
            self.env.remove_error_listener(self._notify_turn_error)
            if start_env:
                await self.env.stop()

    def run(self, start_env: bool = True) -> None:
        """同步入口：启动环境 + Web 服务，阻塞直到退出。"""
        asyncio.run(self.serve(start_env=start_env))
