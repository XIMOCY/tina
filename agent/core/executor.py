"""
编写者：王出日
日期：2024，12，13
版本：0.4.2
功能：Agent的工具执行器
通过导入ToolsExecutor类，可以调用Agent的工具执行器，该类包含一个parser参数，该参数为解析工具调用的函数，默认为tina_parser函数。
通过传入Tools对象来动态导入工具类，并调用该类的方法。
使用方法：
1. 导入AgentExecutor类
from executor import AgentExecutor



"""
import io
from contextlib import redirect_stdout, redirect_stderr
import threading
from .tools import Tools
import time
class ToolsExecutor:
    """
    工具执行器
    """
    def __init__(self,safe_mode=True):
        self.safe_mode = safe_mode

        self.running_threads = {} 
        self.thread_counter = 0    # 线程计数器
        self.thread_lock = threading.Lock()  # 线程安全锁
        self.thread_tools_registered = False  # 标记线程管理工具是否已注册
    def execute(self,_tool_name,_tool:callable,_post_handler:callable,_tools:Tools,timeout=60,*args,**kwargs):
        """
        执行工具
        Args:
            name (str): 工具名称
            timeout (int): 超时时间（秒）, 默认60秒
            *args: 位置参数
            **kwargs: 关键字参数
        Returns:
            any: 工具返回值
        """
        self.__auto_cleanup_threads()

        if self.thread_tools_registered and _tool_name in ['list_running_threads', 'kill_thread', 'get_thread_output', 'cleanup_finished_threads']:
            try:
                result = _tool(*args, **kwargs)
                post_handler = _post_handler
                if post_handler is not None:
                    try:
                        result = post_handler(result)
                    except Exception as e:
                        return f"线程管理工具 '' 的后处理器执行失败: {str(e)}\n" \
                               f"请检查后处理器的参数类型是否与工具输出类型匹配\n" \
                               f"工具原始输出: {result}"
                return str(result)
            except Exception as e:
                return f"线程管理工具 '' 执行失败: {str(e)}"
        
        # 为工具执行创建输出捕获
        output_buffer = io.StringIO()
        tool_result = None
        exception_occurred = None
        
        # 生成线程ID
        with self.thread_lock:
            self.thread_counter += 1
            thread_id = self.thread_counter
        
        def func(*args, **kwargs):
            nonlocal tool_result, exception_occurred
            try:
                # 重定向标准输出和错误输出到缓冲区
                with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                    tool_result = _tool(*args, **kwargs)
                    if tool_result is not None:
                        output_buffer.write(f"\n[返回值]: {tool_result}")
            except Exception as e:
                exception_occurred = e
                output_buffer.write(f"\n[错误]: {str(e)}")
                tool_result = f"工具执行失败: {str(e)}"
        
        try:
            tool_thread = threading.Thread(target=func, args=args, kwargs=kwargs)
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
                if timeout >= 60:
                    self.__add_thread_management_tools(_tools)
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
        
        # 应用后处理器（仅在成功时）
        post_handler = _tools.post_handler.get(_tool_name, None)
        if post_handler is not None:
            try:
                result = post_handler(result)
            except Exception as e:
                return f"工具 '{_tool_name}' 的后处理器执行失败: {str(e)}\n" \
                       f"请检查后处理器的参数类型是否与工具输出类型匹配\n" \
                       f"工具原始输出: {result}"
        
        if full_output.strip() and str(result) != full_output.strip():
            return f"{full_output}\n[最终结果]: {result}"
        
        return str(result)
    
    def __auto_cleanup_threads(self):
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
    
    def __add_thread_management_tools(self,_tools: Tools):
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
        