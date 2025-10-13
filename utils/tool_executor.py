"""
工具执行器模块
提供独立的工具执行能力，支持自定义执行环境
"""
import threading
import time
import io
import inspect
from typing import Callable, Any, Dict, Optional
from contextlib import redirect_stdout, redirect_stderr


class ToolExecutionEnvironment:
    """
    工具执行环境基类
    开发者可以继承此类来自定义工具执行环境
    """
    def __init__(self, name: str = "default"):
        self.name = name
        self.context = {}
    
    def setup(self):
        """
        执行环境初始化
        在工具执行前调用
        """
        pass
    
    def teardown(self):
        """
        执行环境清理
        在工具执行后调用
        """
        pass
    
    def handle_output(self, output: str) -> str:
        """
        处理工具输出
        """
        return output
    
    def handle_error(self, error: Exception) -> str:
        """
        处理工具执行错误
        """
        return f"执行错误: {str(error)}"


class DefaultToolExecutionEnvironment(ToolExecutionEnvironment):
    """
    默认工具执行环境
    """
    def __init__(self):
        super().__init__("default")
    
    def setup(self):
        print(f"正在初始化执行环境: {self.name}")
    
    def teardown(self):
        print(f"正在清理执行环境: {self.name}")


class SandboxToolExecutionEnvironment(ToolExecutionEnvironment):
    """
    沙箱执行环境示例
    限制工具的某些操作
    """
    def __init__(self):
        super().__init__("sandbox")
        self.allowed_modules = set()
        self.max_execution_time = 30  # 限制执行时间30秒
    
    def setup(self):
        print("正在初始化沙箱环境")
        # 可以在这里设置沙箱限制
    
    def handle_error(self, error: Exception) -> str:
        # 拦截特定类型的错误
        if isinstance(error, PermissionError):
            return "沙箱环境拒绝执行此操作"
        return super().handle_error(error)


class ToolExecutor:
    """
    独立的工具执行器
    支持自定义执行环境
    """
    def __init__(self, environment: ToolExecutionEnvironment = None):
        self.environment = environment or DefaultToolExecutionEnvironment()
        self.running_threads = {}
        self.thread_counter = 0
        self.thread_lock = threading.Lock()
    
    def execute(self, 
                tool: Callable, 
                tool_name: str = None,
                timeout: int = 60,
                *args, 
                **kwargs) -> Any:
        """
        执行工具函数
        
        Args:
            tool: 要执行的工具函数
            tool_name: 工具名称（用于日志和错误信息）
            timeout: 执行超时时间（秒）
            *args: 传递给工具函数的位置参数
            **kwargs: 传递给工具函数的关键字参数
            
        Returns:
            工具执行结果
        """
        tool_name = tool_name or tool.__name__
        
        # 初始化执行环境
        self.environment.setup()
        
        try:
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
                        tool_result = tool(*args, **kwargs)
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
                        "name": tool_name,
                        "output": output_buffer,
                        "start_time": time.time(),
                        "should_stop": False  # 停止标志
                    }
                
                tool_thread.start()
                tool_thread.join(timeout=timeout)
                
                if tool_thread.is_alive():
                    current_output = output_buffer.getvalue()
                    runtime = time.time() - self.running_threads[thread_id]["start_time"]
                    
                    return f"⚠️ 工具执行超时（{timeout}秒），线程ID {thread_id} 仍在后台运行\n" \
                           f"工具名: {tool_name}\n" \
                           f"运行时间: {runtime:.1f}秒\n" \
                           f"当前输出:\n{current_output}"
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
                error_output = self.environment.handle_error(exception_occurred)
                return error_output
            
            full_output = output_buffer.getvalue()
            
            # 应用环境的输出处理
            processed_output = self.environment.handle_output(full_output)
            
            # 确定最终结果
            result = tool_result if tool_result is not None else processed_output
            
            return str(result)
            
        finally:
            # 清理执行环境
            self.environment.teardown()


class ToolExecutorRegistry:
    """
    工具执行器注册表
    管理不同的执行器实例
    """
    def __init__(self):
        self.executors: Dict[str, ToolExecutor] = {}
        self.default_executor = ToolExecutor()
    
    def register_executor(self, name: str, executor: ToolExecutor):
        """
        注册工具执行器
        """
        self.executors[name] = executor
    
    def get_executor(self, name: str = None) -> ToolExecutor:
        """
        获取工具执行器
        """
        if name is None:
            return self.default_executor
        return self.executors.get(name, self.default_executor)
    
    def execute_tool(self, 
                     tool: Callable,
                     tool_name: str = None,
                     executor_name: str = None,
                     *args, 
                     **kwargs) -> Any:
        """
        使用指定的执行器执行工具
        """
        executor = self.get_executor(executor_name)
        return executor.execute(tool, tool_name, *args, **kwargs)


# 全局执行器注册表
executor_registry = ToolExecutorRegistry()


def execute_tool(tool: Callable,
                 tool_name: str = None,
                 executor_name: str = None,
                 timeout: int = 60,
                 *args, 
                 **kwargs) -> Any:
    """
    便捷函数：执行工具
    
    Args:
        tool: 要执行的工具函数
        tool_name: 工具名称
        executor_name: 执行器名称
        timeout: 超时时间
        *args: 传递给工具的位置参数
        **kwargs: 传递给工具的关键字参数
        
    Returns:
        工具执行结果
    """
    return executor_registry.execute_tool(
        tool, tool_name, executor_name, timeout, *args, **kwargs
    )