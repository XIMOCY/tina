"""
MCP客户端类
用于管理MCP服务端工具，并与现有的Tools类集成
"""
import asyncio
import json
import uuid
import threading
from typing import Dict, List, Any, Optional, Union ,Tuple
from contextlib import AsyncExitStack
from datetime import datetime


try:
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from ..agent.core.tools import Tools


class MCPClient:
    """
    MCP客户端类，用于管理与MCP服务端的连接和交互
    
    功能：
    1. 从服务端获取工具
    2. 配置和添加服务端
    3. 将请求发送给服务端
    4. 获取智能体请求的历史
    5. 与现有的Tools类集成
    """
    
    def __init__(self):
        """初始化MCP客户端"""
        if not MCP_AVAILABLE:
            raise ImportError("请先安装MCP依赖: pip install mcp-python")
            
        self.servers = {}  # 存储服务端连接信息 {server_id: {session, tools, config}}
        self.exit_stack = AsyncExitStack()
        self.request_history = []  # 存储请求历史
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._loop_is_running = False
        # 启动事件循环线程
        self.start_loop_thread()
    
    def start_loop_thread(self):
        """启动一个专用线程来运行事件循环"""
        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_forever()
            except Exception as e:
                print(f"事件循环线程出错: {e}")
            finally:
                # 确保循环关闭
                try:
                    pending_tasks = [t for t in asyncio.all_tasks(self.loop) 
                                  if not t.done() and t is not asyncio.current_task(self.loop)]
                    if pending_tasks:
                        self.loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                    self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                    if hasattr(self.loop, 'shutdown_default_executor'):
                        self.loop.run_until_complete(self.loop.shutdown_default_executor())
                except Exception:
                    pass  # Ignore errors during cleanup
                finally:
                    self.loop.close()
                    self._loop_is_running = False
        
        if not self._loop_is_running:
            self._loop_is_running = True
            thread = threading.Thread(target=run_event_loop, daemon=True)
            thread.start()
    
    # 同步方法 - 用户主要使用的方法
    
    def addServer(self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
        """
        添加MCP服务端（同步版本，带重试机制）
        
        Args:
            server_id: 服务端唯一标识
            config: 服务端配置，格式为:
                   - SSE: {"type": "sse", "url": "https://example.com/sse"}
                   - stdio: {"type": "stdio", "command": "python", "args": ["server.py"]}
            max_retries: 最大重试次数
            timeout: 每次尝试的超时时间（秒）
        
        Returns:
            bool: 添加是否成功
        """
        for attempt in range(max_retries):
            try:
                if not self._loop_is_running:
                    self.start_loop_thread()
                
                future = asyncio.run_coroutine_threadsafe(
                    self._add_server_async(server_id, config), 
                    self.loop
                )
                result = future.result(timeout=timeout)
                if result:
                    return True
                elif attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                else:
                    return False
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                else:
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                else:
                    return False
        
        return False
    
    def closeServer(self, server_id: str, max_retries=2, timeout=30) -> bool:
        """
        关闭指定服务端连接（同步版本）
        
        Args:
            server_id: 服务端唯一标识
            max_retries: 最大重试次数
            timeout: 每次尝试的超时时间（秒）
        
        Returns:
            bool: 关闭是否成功
        """
        for attempt in range(max_retries):
            try:
                # 确保事件循环在运行
                if not self._loop_is_running:
                    self.start_loop_thread()
                    
                future = asyncio.run_coroutine_threadsafe(
                    self._close_server_async(server_id), 
                    self.loop
                )
                return future.result(timeout=timeout)
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                else:
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                else:
                    return False
        
        return False
    
    def removeServer(self, server_id: str) -> bool:
        """
        移除MCP服务端（同步版本）
        
        Args:
            server_id: 服务端唯一标识
        
        Returns:
            bool: 移除是否成功
        """
        return self.closeServer(server_id)
    
    def getTools(self, server_id: Optional[str] = None, max_retries=2, timeout=30) -> List[Dict[str, Any]]:
        """
        获取服务端提供的工具（同步版本）
        
        Args:
            server_id: 服务端唯一标识，如果为None，则返回所有服务端的工具
            max_retries: 最大重试次数
            timeout: 每次尝试的超时时间（秒）
        
        Returns:
            List[Dict[str, Any]]: 工具列表
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"尝试获取工具 (尝试 {attempt+1}/{max_retries})...")
                
                # 确保事件循环在运行
                if not self._loop_is_running:
                    self.start_loop_thread()
                    
                future = asyncio.run_coroutine_threadsafe(
                    self._get_tools_async(server_id), 
                    self.loop
                )
                return future.result(timeout=timeout)
            except asyncio.TimeoutError:
                print(f"获取工具超时")
                if attempt < max_retries - 1:
                    print(f"将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    print(f"获取工具在 {max_retries} 次尝试后仍然超时")
                    return []
            except Exception as e:
                print(f"获取工具调用失败: {e}")
                if attempt < max_retries - 1:
                    print(f"将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    return []
        
        return []
    
    def callTool(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None, max_retries=2, timeout=120) -> Dict[str, Any]:
        """
        调用工具（同步版本）
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            server_id: 服务端唯一标识，如果为None，则在所有服务端中查找工具
            max_retries: 最大重试次数
            timeout: 每次尝试的超时时间（秒）
        
        Returns:
            Dict[str, Any]: 工具调用结果
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"尝试调用工具 {tool_name} (尝试 {attempt+1}/{max_retries})...")
                
                # 确保事件循环在运行
                if not self._loop_is_running:
                    self.start_loop_thread()
                    
                future = asyncio.run_coroutine_threadsafe(
                    self._call_tool_async(tool_name, tool_args, server_id), 
                    self.loop
                )
                return future.result(timeout=timeout)
            except asyncio.TimeoutError as e:
                print(f"调用工具 {tool_name} 超时")
                if attempt < max_retries - 1:
                    print(f"将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    print(f"调用工具 {tool_name} 在 {max_retries} 次尝试后仍然超时")
                    return {
                        "success": False,
                        "error": f"调用工具超时: {str(e)}"
                    }
            except Exception as e:
                print(f"调用工具 {tool_name} 失败: {e}")
                if attempt < max_retries - 1:
                    print(f"将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    return {
                        "success": False,
                        "error": f"调用工具失败: {str(e)}"
                    }
        
        return {
            "success": False,
            "error": "达到最大重试次数"
        }
    
    def toTinaTools(self) -> Tools:
        """
        将MCP工具转换为tina的Tools类实例（同步版本）
        
        Returns:
            Tools: tina的Tools类实例
        """
        # 创建一个新的Tools实例
        tina_tools = Tools()
        
        # 获取所有MCP工具
        try:
            mcp_tools = self.getTools()
            
            if not mcp_tools:
                print("没有获取到MCP工具，返回空的Tools实例")
                return tina_tools
                
            # 转换MCP工具为tina工具格式
            for tool in mcp_tools:
                name = tool["name"]
                description = tool["description"]
                server_id = tool["server_id"]
                
                # 解析输入模式获取参数
                input_schema = tool["input_schema"]
                required_parameters = input_schema.get("required", [])
                properties = input_schema.get("properties", {})
                
                parameters = {}
                for param_name, param_info in properties.items():
                    parameters[param_name] = {
                        "type": param_info.get("type", "str"),
                        "description": param_info.get("description", "")
                    }
                
                # 注册工具到tina的Tools实例
                tina_tools.register(
                    name=f"mcp_{server_id}_{name}",
                    description=f"[MCP:{server_id}] {description}",
                    required_parameters=required_parameters,
                    parameters=parameters,
                    path=f"mcp://{server_id}/{name}"
                )
            
            print(f"成功转换了 {len(mcp_tools)} 个MCP工具到tina工具")
        except Exception as e:
            print(f"转换MCP工具时出错: {e}")
        
        return tina_tools
    
    def updateTinaTools(self, tina_tools: Tools) -> Tools:
        """
        更新现有的tina Tools实例，添加MCP工具（同步版本）
        
        Args:
            tina_tools: 现有的tina Tools实例
        
        Returns:
            Tools: 更新后的tina Tools实例
        """
        # 获取MCP工具转换为tina工具格式
        mcp_tina_tools = self.toTinaTools()
        
        # 合并工具
        combined_tools = tina_tools + mcp_tina_tools
        
        return combined_tools
    
    def close(self):
        """关闭所有连接（同步版本）"""
        try:
            future = asyncio.run_coroutine_threadsafe(self._close_async(), self.loop)
            return future.result(timeout=30)  # 30秒超时
        except asyncio.TimeoutError:
            print("关闭客户端超时，可能有资源未正确清理")
            return False
        except Exception as e:
            print(f"关闭客户端调用失败: {e}")
            return False
    
    def loadConfig(self, config_path: str) -> bool:
        """
        从配置文件加载服务端配置
        
        Args:
            config_path: 配置文件路径
        
        Returns:
            bool: 加载是否成功
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            if "mcpServers" in config:
                for server_id, server_config in config["mcpServers"].items():
                    self.addServer(server_id, server_config)
                return True
            else:
                print("配置文件格式错误，缺少mcpServers字段")
                return False
        
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return False
    
    def saveConfig(self, config_path: str) -> bool:
        """
        保存服务端配置到文件
        
        Args:
            config_path: 配置文件路径
        
        Returns:
            bool: 保存是否成功
        """
        try:
            config = {
                "mcpServers": {
                    server_id: server_info["config"]
                    for server_id, server_info in self.servers.items()
                }
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            return True
        
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def getRequestHistory(self, limit: int = 100, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取请求历史
        
        Args:
            limit: 返回的最大记录数
            filter_type: 过滤记录类型，如"tool_call"
        
        Returns:
            List[Dict[str, Any]]: 请求历史记录
        """
        if filter_type:
            filtered_history = [record for record in self.request_history if record.get("type") == filter_type]
            return filtered_history[-limit:]
        else:
            return self.request_history[-limit:]
    
    def getServerInfo(self, server_id: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        获取服务端信息
        
        Args:
            server_id: 服务端唯一标识，如果为None，则返回所有服务端信息
        
        Returns:
            Union[Dict[str, Any], List[Dict[str, Any]]]: 服务端信息
        """
        if server_id:
            if server_id in self.servers:
                server_info = self.servers[server_id]
                return {
                    "id": server_id,
                    "config": server_info["config"],
                    "tools_count": len(server_info["tools"]),
                    "added_at": server_info["added_at"].isoformat()
                }
            else:
                return {"error": f"服务端 {server_id} 不存在"}
        else:
            return [{
                "id": sid,
                "config": server_info["config"],
                "tools_count": len(server_info["tools"]),
                "added_at": server_info["added_at"].isoformat()
            } for sid, server_info in self.servers.items()]
    
    # 异步方法 - 带Async后缀，用于开发者可以异步调用这个类
    async def addServerAsync(self, server_id: str, config: Dict[str, Any]) -> bool:
        """
        添加MCP服务端（异步版本）
        
        Args:
            server_id: 服务端唯一标识
            config: 服务端配置，格式为:
                   - SSE: {"type": "sse", "url": "https://example.com/sse"}
                   - stdio: {"type": "stdio", "command": "python", "args": ["server.py"]}
        
        Returns:
            bool: 添加是否成功
        """
        return await self._add_server_async(server_id, config)
    
    async def closeServerAsync(self, server_id: str) -> bool:
        """
        关闭指定服务端连接（异步版本）
        
        Args:
            server_id: 服务端唯一标识
        
        Returns:
            bool: 关闭是否成功
        """
        return await self._close_server_async(server_id)
    
    async def removeServerAsync(self, server_id: str) -> bool:
        """
        移除MCP服务端（异步版本）
        
        Args:
            server_id: 服务端唯一标识
        
        Returns:
            bool: 移除是否成功
        """
        return await self._close_server_async(server_id)
    
    async def getToolsAsync(self, server_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取服务端提供的工具（异步版本）
        
        Args:
            server_id: 服务端唯一标识，如果为None，则返回所有服务端的工具
        
        Returns:
            List[Dict[str, Any]]: 工具列表
        """
        return await self._get_tools_async(server_id)
    
    async def callToolAsync(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        调用工具（异步版本）
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            server_id: 服务端唯一标识，如果为None，则在所有服务端中查找工具
        
        Returns:
            Dict[str, Any]: 工具调用结果
        """
        return await self._call_tool_async(tool_name, tool_args, server_id)
    
    async def toTinaToolsAsync(self) -> Tools:
        """
        将MCP工具转换为tina的Tools类实例（异步版本）
        
        Returns:
            Tools: tina的Tools类实例
        """
        # 创建一个新的Tools实例
        tina_tools = Tools()
        
        # 获取所有MCP工具
        try:
            mcp_tools = await self._get_tools_async()
            
            # 转换MCP工具为tina工具格式
            for tool in mcp_tools:
                name = tool["name"]
                description = tool["description"]
                server_id = tool["server_id"]
                
                # 解析输入模式获取参数
                input_schema = tool["input_schema"]
                required_parameters = input_schema.get("required", [])
                properties = input_schema.get("properties", {})
                
                parameters = {}
                for param_name, param_info in properties.items():
                    parameters[param_name] = {
                        "type": param_info.get("type", "str"),
                        "description": param_info.get("description", "")
                    }
                
                # 注册工具到tina的Tools实例
                tina_tools.register(
                    name=f"mcp_{server_id}_{name}",
                    description=f"[MCP:{server_id}] {description}",
                    required_parameters=required_parameters,
                    parameters=parameters,
                    path=f"mcp://{server_id}/{name}"
                )
            
            
        except Exception as e:
            raise e
        
        return tina_tools
    
    async def updateTinaToolsAsync(self, tina_tools: Tools) -> Tools:
        """
        更新现有的tina Tools实例，添加MCP工具（异步版本）
        
        Args:
            tina_tools: 现有的tina Tools实例
        
        Returns:
            Tools: 更新后的tina Tools实例
        """
        # 获取MCP工具转换为tina工具格式
        mcp_tina_tools = await self.toTinaToolsAsync()
        
        # 合并工具
        combined_tools = tina_tools + mcp_tina_tools
        
        return combined_tools
    
    async def closeAsync(self):
        """关闭所有连接（异步版本）"""
        return await self._close_async()
    
    
    async def _add_server_async(self, server_id: str, config: Dict[str, Any]) -> Dict:
        """
        添加MCP服务端（内部异步实现）
        
        Args:
            server_id: 服务端唯一标识
            config: 服务端配置，格式为:
                   - SSE: {"type": "sse", "url": "https://example.com/sse"}
                   - stdio: {"type": "stdio", "command": "python", "args": ["server.py"]}
        
        Returns:
            bool: 添加是否成功
        """
        if server_id in self.servers:
            raise ValueError(f"服务端 {server_id} 已存在，请选择另一个名称")
        
        try:
            server_type = config.get("type", "").lower()
            
            if server_type == "sse":
                # SSE服务端
                if "url" not in config:
                    raise ValueError("SSE服务端配置缺少URL")
                
                transport = await self.exit_stack.enter_async_context(
                    sse_client(config["url"])
                )
                read_stream, write_stream = transport  # 正确解包两个流
                session = await self.exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)  # 提供两个必要的参数
                )
            
            elif server_type == "stdio":
                # stdio服务端
                if "command" not in config:
                    raise ValueError("stdio服务端配置缺少command")
                
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env", None)
                )
                
                stdio_transport = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                stdin, stdout = stdio_transport
                session = await self.exit_stack.enter_async_context(
                    ClientSession(stdin, stdout)
                )
            
            else:
                raise ValueError(f"不支持的服务端类型: {server_type}")
            
            # 初始化会话
            await session.initialize()
            
            # 获取可用工具
            response = await session.list_tools()
            tools = response.tools
            
            # 存储服务端信息
            self.servers[server_id] = {
                "session": session,
                "tools": tools,
                "config": config,
                "added_at": datetime.now()
            }
            
   
            return {"status":True,"tools":[tool.name for tool in tools]}
        
        except Exception as e:
            raise e
    
    async def _close_server_async(self, server_id: str) -> bool:
        """
        关闭指定服务端连接（内部异步实现）
        
        Args:
            server_id: 服务端唯一标识
        
        Returns:
            bool: 关闭是否成功
        """
        if server_id not in self.servers:
            print(f"服务端 {server_id} 不存在")
            return False
        
        try:
            # 获取服务器配置类型
            server_info = self.servers[server_id]
            server_type = server_info["config"].get("type", "").lower()
            
            # 不同类型的服务端采用不同的关闭策略
            if server_type == "stdio":
                # stdio类型：尝试关闭session
                session = server_info.get("session")
                if session:
                    try:
                        # 标准关闭方法
                        await session.close()
                    except Exception as e:
                        print(f"关闭stdio session时出错: {e}")
            elif server_type == "sse":
                session = server_info.get("session")
                if session:
                    try:
                        pass
                    except Exception as e:
                        pass
        finally:
            if server_id in self.servers:  
                del self.servers[server_id]
                print(f"已关闭服务端 {server_id}")
            return True
    
    async def _get_tools_async(self, server_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取服务端提供的工具（内部异步实现）
        
        Args:
            server_id: 服务端唯一标识，如果为None，则返回所有服务端的工具
        
        Returns:
            List[Dict[str, Any]]: 工具列表
        """
        tools = []
        
        if server_id:
            # 获取指定服务端的工具
            if server_id in self.servers:
                server_tools = self.servers[server_id]["tools"]
                tools.extend([{
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "server_id": server_id
                } for tool in server_tools])
            else:
                print(f"服务端 {server_id} 不存在")
        else:
            # 获取所有服务端的工具
            for sid, server_info in self.servers.items():
                server_tools = server_info["tools"]
                tools.extend([{
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "server_id": sid
                } for tool in server_tools])
        
        return tools
    
    async def _call_tool_async(self, tool_name: str, tool_args: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        调用工具（内部异步实现）
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            server_id: 服务端唯一标识，如果为None，则在所有服务端中查找工具
        
        Returns:
            Dict[str, Any]: 工具调用结果
        """
        # 记录请求
        request_id = str(uuid.uuid4())
        request_record = {
            "id": request_id,
            "timestamp": datetime.now().isoformat(),
            "type": "tool_call",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "server_id": server_id,
            "status": "pending"
        }
        self.request_history.append(request_record)
        
        try:
            if server_id:
                # 在指定服务端调用工具
                if server_id not in self.servers:
                    raise ValueError(f"服务端 {server_id} 不存在")
                
                session = self.servers[server_id]["session"]
                result = await session.call_tool(tool_name, tool_args)
                
                # 更新请求记录
                request_record["status"] = "success"
                request_record["result"] = result.content
                
                return {
                    "success": True,
                    "content": result.content,
                    "request_id": request_id
                }
            else:
                # 在所有服务端中查找工具
                for sid, server_info in self.servers.items():
                    tools = server_info["tools"]
                    if any(tool.name == tool_name for tool in tools):
                        session = server_info["session"]
                        result = await session.call_tool(tool_name, tool_args)
                        
                        # 更新请求记录
                        request_record["status"] = "success"
                        request_record["result"] = result.content
                        request_record["server_id"] = sid
                        
                        return {
                            "success": True,
                            "content": result.content,
                            "server_id": sid,
                            "request_id": request_id
                        }
                
                # 没有找到工具
                request_record["status"] = "failed"
                request_record["error"] = f"未找到工具 {tool_name}"
                
                return {
                    "success": False,
                    "error": f"未找到工具 {tool_name}",
                    "request_id": request_id
                }
        
        except Exception as e:
            # 更新请求记录
            request_record["status"] = "failed"
            request_record["error"] = str(e)
            
            return {
                "success": False,
                "error": str(e),
                "request_id": request_id
            }
    
    async def _close_async(self):
        """关闭所有连接（内部异步实现）"""
        # 首先尝试关闭所有服务端连接
        server_ids = list(self.servers.keys())
        for server_id in server_ids:
            try:
                await self._close_server_async(server_id)
            except Exception as e:
                print(f"关闭服务端 {server_id} 时出错: {e}")
        
        # 清空服务端列表
        self.servers.clear()
        
        # 确保事件循环中没有未完成的任务
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task(self.loop)]
        if tasks:
            print(f"等待 {len(tasks)} 个未完成的任务...")
            await asyncio.gather(*tasks, return_exceptions=True)
            print("所有任务已完成")
            
        # 最后关闭exit_stack，确保在所有服务都关闭后再关闭
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception as e:
                print(f"关闭exit_stack时出错: {e}")
                
    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            # 尝试关闭所有连接
            if hasattr(self, 'loop') and self._loop_is_running:
                asyncio.run_coroutine_threadsafe(self._close_async(), self.loop)
            elif hasattr(self, 'servers') and self.servers:
                # 如果事件循环没有运行，创建一个新的循环来关闭资源
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._close_async())
                finally:
                    loop.close()
        except Exception as e:
            print(f"析构函数中关闭资源时出错: {e}")
            