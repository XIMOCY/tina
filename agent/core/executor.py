"""
编写者：王出日
日期：2024，12，13
版本：0.4.2
功能：Agent的工具执行器
"""
import io
from contextlib import redirect_stdout, redirect_stderr
import threading
import time
import json
import asyncio
import inspect
from ...core import logger
# from .tools import Tools
from ...mcp.MCPToolExecutor import MCPToolExecutor
from ...core.error import NoConfirmationHanlder


from .events import Events


class ToolsExecutor:
    """
    工具执行器
    """

    def __init__(self):
        # 事件系统由外部注入（Agent / Runtime）
        self.events: Events = None
        self.running_threads = {} 
        self.thread_counter = 0    # 线程计数器
        self.thread_lock = threading.Lock()  # 线程安全锁
        self.thread_tools_registered = False  # 标记线程管理工具是否已注册

    def execute(self,_tool_calls:list[dict],_tools,_mcp_client = None,timeout=60,events:Events=None,**kwargs):
        """
        执行工具调用
        """
        _tool_calls_result = []

        if not _tool_calls:
            return _tool_calls_result

        if "index" in _tool_calls[0]:
            _tool_calls.sort(key=lambda x: x['index'])

        # 优先使用参数传入的 events，其次回退到自身持有的 events
        active_events = events if events is not None else self.events

        for tool_call in _tool_calls:
            _tool_name = tool_call["function"]["name"]
            _tool_args = json.loads(tool_call["function"]["arguments"])
            _tool_id = tool_call["id"]

            # ============= 事件处理：不捕获异常，让上层感知 =============
            if active_events is not None:
                for handler in active_events.get_handler("before_tool_call"):
                    handler(_tool_name, _tool_args)

            # ============= 工具执行：严格捕获异常，避免中断 Agent =============
            if _tool_name.startswith("mcp_"):
                # 使用 MCP 工具执行器执行 MCP 工具
                try:
                    result = MCPToolExecutor.execute_mcp_tool(_tool_name, _tool_args, _mcp_client)
                except Exception as e:
                    logger.error(f"ToolsExecutor - MCP 工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                    result = f"工具 '{_tool_name}' 执行失败: {str(e)}"

            else:
                _tool = _tools.get_tool(name=_tool_name)

                # 需要人工确认的工具
                if _tools.get_require_confirmations(_tool_name):
                    if active_events is None:
                        # 没有事件系统，无法完成确认流程
                        raise NoConfirmationHanlder()

                    confirmation_handler = active_events.get_tool_confirmation_handler()
                    # Events 默认把 on_tool_confirmation 初始化为内置 callable，需要特殊处理视为「未注册」
                    if confirmation_handler is None:
                        raise NoConfirmationHanlder()

                    # 事件处理阶段不包裹 try/except，错误直接抛出给上层
                    if confirmation_handler(_tool_name, _tool_args) is False:
                        result = f"用户阻止了{_tool_name}的运行"
                    else:
                        try:
                            result = self._execute(_tool_name, _tool_args, _tool, _tools, timeout=timeout)
                        except Exception as e:
                            logger.error(f"ToolsExecutor - 工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                            result = f"工具 '{_tool_name}' 执行失败: {str(e)}"
                else:
                    try:
                        result = self._execute(_tool_name, _tool_args, _tool, _tools, timeout=timeout)
                    except Exception as e:
                        logger.error(f"ToolsExecutor - 工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                        result = f"工具 '{_tool_name}' 执行失败: {str(e)}"

                logger.debug(f"ToolsExecutor - 工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}")

            # ============= after_tool_call 事件：只在工具执行结束后触发 =============
            if active_events is not None:
                for handler in active_events.get_handler("after_tool_call"):
                    handler(_tool_name, _tool_args, result)

            _tool_calls_result.append(self._tool_call_result(result,_tool_id,_tool_name))


        return _tool_calls_result

    async def aexecute(self,_tool_calls,_tools,_mcp_client=None,timeout=60,events:Events=None,**kwargs)->any:
        _tool_calls_result = []
        if not _tool_calls:
            return _tool_calls_result

        if "index" in _tool_calls[0]:
            _tool_calls.sort(key=lambda x: x['index'])

        active_events = events if events is not None else self.events

        for tool_call in _tool_calls:
            _tool_name = tool_call["function"]["name"]
            _tool_args = json.loads(tool_call["function"]["arguments"])
            _tool_id = tool_call["id"]

            # ============= 事件处理：不捕获异常，让上层感知 =============
            if active_events is not None:
                for handler in active_events.get_handler("before_tool_call"):
                    if inspect.iscoroutinefunction(handler):
                        await handler(_tool_name, _tool_args)
                    else:
                        handler(_tool_name, _tool_args)

            # 根据工具类型选择执行方式：
            # - 异步工具：直接在当前事件循环中 await 执行
            # - 同步工具：复用现有线程逻辑，但通过线程池避免阻塞事件循环
            if _tool_name.startswith("mcp_"):
                # 使用MCP工具执行器执行MCP工具
                try:
                    result = await MCPToolExecutor.aexecute_mcp_tool(_tool_name, _tool_args, _mcp_client)
                except Exception as e:
                    logger.error(f"ToolsExecutor - MCP 工具 '{_tool_name}' 异步执行失败: {str(e)}：参数 {_tool_args}")
                    result = f"工具 '{_tool_name}' 执行失败: {str(e)}"

            else:    
                _tool = _tools.get_tool(name=_tool_name)

                # 需要人工确认的工具
                if _tools.get_require_confirmations(_tool_name):
                    if active_events is None:
                        raise NoConfirmationHanlder()

                    confirmation_handler = active_events.get_tool_confirmation_handler()
                    if confirmation_handler is None:
                        raise NoConfirmationHanlder()

                    # 支持异步 / 同步确认处理器
                    if inspect.iscoroutinefunction(confirmation_handler):
                        confirmed = await confirmation_handler(_tool_name, _tool_args)
                    else:
                        confirmed = confirmation_handler(_tool_name, _tool_args)

                    if confirmed is False:
                        result = f"用户阻止了{_tool_name}的运行"
                    else:
                        try:
                            result = await self._aexecute_single(
                                _tool_name=_tool_name,
                                _tool_args=_tool_args,
                                _tool=_tool,
                                _tools=_tools,
                                timeout=timeout,
                            )
                        except Exception as e:
                            logger.error(f"ToolsExecutor - 异步工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                            result = f"工具 '{_tool_name}' 执行失败: {str(e)}"
                else:
                    try:
                        result = await self._aexecute_single(
                            _tool_name=_tool_name,
                            _tool_args=_tool_args,
                            _tool=_tool,
                            _tools=_tools,
                            timeout=timeout,
                        )
                    except Exception as e:
                        logger.error(f"ToolsExecutor - 异步工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                        result = f"工具 '{_tool_name}' 执行失败: {str(e)}"

                logger.debug(f"ToolsExecutor - 异步工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}")

            # ============= after_tool_call 事件（异步版，同步/异步 handler 都支持） =============
            if active_events is not None:
                for handler in active_events.get_handler("after_tool_call"):
                    if inspect.iscoroutinefunction(handler):
                        await handler(_tool_name, _tool_args, result)
                    else:
                        handler(_tool_name, _tool_args, result)

            _tool_calls_result.append(self._tool_call_result(result,_tool_id,_tool_name))
        
        return _tool_calls_result

    async def _aexecute_single(self,_tool_name:str,_tool_args:dict,_tool:callable,_tools,timeout=60):
        """
        异步环境下执行单个工具调用：
        - 如果工具是异步函数，则直接 await
        - 如果工具是同步函数，则在单独线程中执行，避免阻塞事件循环
        """
        if _tool is None:
            return f"工具 '{_tool_name}' 未找到"

        # 异步工具：直接 await，不再包一层线程，尊重调用方的事件循环
        if inspect.iscoroutinefunction(_tool):
            try:
                result = await _tool(**_tool_args)

                logger.debug(f"ToolsExecutor - 异步工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}")
                return str(result)
            except Exception as e:
                logger.error(f"ToolsExecutor - 异步工具 '{_tool_name}' 执行失败: {str(e)}：参数 {_tool_args}")
                return f"工具 '{_tool_name}' 执行失败: {str(e)}"

        # 同步工具：在单独线程中执行，复用已有的线程管理和超时逻辑
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._execute(_tool_name,_tool_args,_tool,_tools,timeout=timeout)
        )

    def _tool_call_result(self,_tool_result,_tool_id,_tool_name):
        return {"role":"tool","content":_tool_result,"tool_call_id":_tool_id,"tool_name":_tool_name}
    def _execute(self,_tool_name:str,_tool_args:dict,_tool:callable,_tools,timeout=60):
        """
        执行工具
        Args:
            name (str): 工具名称
            timeout (int): 超时时间（秒）, 默认60秒
            **kwargs: 关键字参数
        Returns:
            any: 工具返回值
        """
        self._auto_cleanup_threads()

        if self.thread_tools_registered and _tool_name in ['list_running_threads', 'kill_thread', 'get_thread_output', 'cleanup_finished_threads']:
            try:
                result = _tool(**_tool_args)

                return str(result)
            except Exception as e:
                return f"线程管理工具 '{_tool_name}' 执行失败: {str(e)}"
        
        # 为工具执行创建输出捕获
        output_buffer = io.StringIO()
        tool_result = None
        exception_occurred = None
        
        # 生成线程ID
        with self.thread_lock:
            self.thread_counter += 1
            thread_id = self.thread_counter
        
        def func(**kwargs):
            nonlocal tool_result, exception_occurred
            try:
                # 重定向标准输出和错误输出到缓冲区
                with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                    tool_result = _tool(**kwargs)
                    if tool_result is not None:
                        output_buffer.write(f"\n{tool_result}")
            except Exception as e:
                exception_occurred = e
                output_buffer.write(f"\n[错误]: {str(e)}")
                tool_result = f"工具执行失败: {str(e)}"
        
        try:
            tool_thread = threading.Thread(target=func, kwargs=_tool_args)
            tool_thread.daemon = True  # 设置为守护线程
            
            # 记录线程信息
            with self.thread_lock:
                self.running_threads[thread_id] = {
                    "thread": tool_thread,
                    "name": _tool_name,
                    "output": output_buffer,
                    "start_time": time.time(),
                    "should_stop": False  # 停止标志
                }
            
            tool_thread.start()
            tool_thread.join(timeout=timeout)
            
            if tool_thread.is_alive():
                current_output = output_buffer.getvalue()
                runtime = time.time() - self.running_threads[thread_id]["start_time"]
                
                # 如果超时时间达到60秒，动态注册线程管理工具
                if runtime >= timeout:
                    self._add_thread_management_tools(_tools)
                    thread_management_hint = f"工具执行时间较长\n" \
                                           f"- list_running_threads(): 查看所有运行中的线程\n" \
                                           f"- get_thread_output({thread_id}): 获取线程最新输出\n" \
                                           f"- kill_thread({thread_id}): 强制停止线程\n" \
                                           f"- cleanup_finished_threads(): 清理已完成的线程"
                else:
                    thread_management_hint = f"该线程仍在后台运行，如需管理请使用更长的超时时间（≥60秒）"
                
                return f"工具执行超时（{timeout}秒），线程ID {thread_id} 仍在后台运行\n" \
                       f"工具名: {_tool_name}\n" \
                       f"运行时间: {runtime:.1f}秒\n" \
                       f"当前输出:\n{current_output}\n\n" \
                       f"{thread_management_hint}"
            else:
                # 线程正常结束，清理记录
                with self.thread_lock:
                    if thread_id in self.running_threads:
                        del self.running_threads[thread_id]
                
        except Exception as e:
            # 清理线程记录
            with self.thread_lock:
                if thread_id in self.running_threads:
                    del self.running_threads[thread_id]
            return f"工具执行失败: {str(e)}" 
        
        if exception_occurred:
            return str(tool_result)
        
        full_output = output_buffer.getvalue()
        
        # 确定最终结果
        result = tool_result if tool_result is not None else full_output
        
        
        if full_output.strip() and str(result) != full_output.strip():
            return f"{full_output}\n"
        
        return str(result)
    
    def _auto_cleanup_threads(self):
        """自动清理已完成的线程（内部方法）"""
        try:
            with self.thread_lock:
                finished_threads = []
                for thread_id, thread_info in self.running_threads.items():
                    if not thread_info["thread"].is_alive():
                        finished_threads.append(thread_id)
                
                for thread_id in finished_threads:
                    del self.running_threads[thread_id]
        except Exception:
            # 静默处理清理错误，不影响主程序
            pass
    
    def _add_thread_management_tools(self,_tools):
        """动态添加线程管理工具（仅在需要时调用）"""
        # 防止重复注册
        if self.thread_tools_registered:
            return
            
        self.thread_tools_registered = True
        
        def list_running_threads():
            """
            获取当前正在运行的工具线程列表
            Returns:
                str: 格式化的线程信息
            """
            if not self.running_threads:
                return "🔍 当前没有正在运行的工具线程"
            
            result = "🔍 正在运行的工具线程:\n"
            current_time = time.time()
            
            with self.thread_lock:
                for thread_id, thread_info in self.running_threads.items():
                    runtime = current_time - thread_info["start_time"]
                    status = "运行中" if thread_info["thread"].is_alive() else "已完成"
                    result += f"线程ID: {thread_id}\n"
                    result += f"工具名: {thread_info['name']}\n"
                    result += f"运行时间: {runtime:.1f}秒\n"
                    result += f"状态: {status}\n"
            
            return result
            
        def kill_thread(thread_id: int):
            """
            强制终止指定的工具线程
            Args:
                thread_id (int): 线程ID
            Returns:
                str: 操作结果
            """
            if thread_id not in self.running_threads:
                return f"线程ID {thread_id} 不存在"
            
            with self.thread_lock:
                thread_info = self.running_threads[thread_id]
                thread = thread_info["thread"]
                
                if not thread.is_alive():
                    del self.running_threads[thread_id]
                    return f"线程ID {thread_id} 已经结束，已从记录中移除"
                

                try:
                    # 标记线程需要停止（需要工具内部配合检查这个标志）
                    thread_info["should_stop"] = True
                    
                    # 等待短时间看线程是否自己停止
                    thread.join(timeout=2)
                    
                    if thread.is_alive():
                        # 线程仍在运行，从记录中移除但线程可能继续运行
                        del self.running_threads[thread_id]
                        return f"线程ID {thread_id} 收到停止信号" \
                               f"工具名: {thread_info['name']}\n" \
 
                    else:
                        del self.running_threads[thread_id]
                        return f"线程ID {thread_id} 已成功停止"
                        
                except Exception as e:
                    return f"停止线程ID {thread_id} 时发生错误: {str(e)}"
                    
        def get_thread_output(thread_id: int):
            """
            获取指定线程的最新输出
            Args:
                thread_id (int): 线程ID
            Returns:
                str: 线程的当前输出
            """
            if thread_id not in self.running_threads:
                return f"线程ID {thread_id} 不存在"
                
            thread_info = self.running_threads[thread_id]
            current_time = time.time()
            runtime = current_time - thread_info["start_time"]
            
            try:
                output = thread_info["output"].getvalue()
                status = "运行中" if thread_info["thread"].is_alive() else "已完成"
                
                result = f"线程ID {thread_id} 输出信息:\n"
                result += f"工具名: {thread_info['name']}\n"
                result += f"运行时间: {runtime:.1f}秒\n"
                result += f"状态: {status}\n"
                result += f"{'='*50}\n"
                result += f"输出内容:\n{output}\n"
                result += f"{'='*50}"
                
                # 如果线程已完成，从记录中移除
                if not thread_info["thread"].is_alive():
                    with self.thread_lock:
                        if thread_id in self.running_threads:
                            del self.running_threads[thread_id]
                
                return result
                
            except Exception as e:
                return f"获取线程ID {thread_id} 输出时发生错误: {str(e)}"
                
        def cleanup_finished_threads():
            """
            清理已完成的线程记录
            Returns:
                str: 清理结果
            """
            cleaned_count = 0
            
            with self.thread_lock:
                finished_threads = []
                for thread_id, thread_info in self.running_threads.items():
                    if not thread_info["thread"].is_alive():
                        finished_threads.append(thread_id)
                
                for thread_id in finished_threads:
                    del self.running_threads[thread_id]
                    cleaned_count += 1
            
            return f"已清理 {cleaned_count} 个已完成的线程记录"
        
        # 注册线程管理工具
        _tools.registerTool(list_running_threads, "获取当前正在运行的工具线程列表")
        _tools.registerTool(kill_thread, "强制终止指定的工具线程")
        _tools.registerTool(get_thread_output, "获取指定线程的最新输出")
        _tools.registerTool(cleanup_finished_threads, "清理已完成的线程记录")
        
