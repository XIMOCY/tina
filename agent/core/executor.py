"""
编写者：王出日
日期：2024，12，13
版本：0.4.2
功能：Agent的工具执行器
通过导入AgentExecutor类，可以调用Agent的工具执行器，该类包含一个parser参数，该参数为解析工具调用的函数，默认为tina_parser函数。
通过传入Tools对象来动态导入工具类，并调用该类的方法。
使用方法：
1. 导入AgentExecutor类
from executor import AgentExecutor
2. 不需要创建实例，里面的方法为静态方法，可以直接调用
例如使用execute方法执行工具调用：
    result = AgentExecutor.execute(tool_call, tools, is_permissions)


"""
import importlib.util
from .parser import tina_parser
from .tools import Tools
import threading

class AgentExecutor:  
    @staticmethod
    def execute(tool_call: tuple[str, dict, bool], tools: type) -> tuple[str, bool]:
        """
        执行工具调用
        如何使用：
        result = AgentExecutor.execute(tool_call, tools, is_permissions)
        其中，tool_call为工具调用的字符串，tools为Agent的工具类，is_permissions为是否需要验证权限，默认为True。
        返回值：
        第一个元素为执行结果，第二个元素为是否成功。
        可以使用变量拆包的方式获取执行结果：
        result, success = AgentExecutor.execute(tool_call, tools, is_permissions)
        其中，success为是否使用了工具调用，True表示成功，False表示失败。
        Args:
            tool_call (tuple[str, dict, bool]): 元组,内含解析器会解析的工具调用
            tools (type): 工具类，用于内部调用检测工具是否存在和参数验证
        Returns:
            tuple[str, bool]: 元组，执行结果和是否成功
        """
        if not tool_call[2]:
            return tool_call
        try:
            module = AgentExecutor.import_module(tools.getToolsPath(name=tool_call[0]))
            func = getattr(module, tool_call[0])
            result_cont = None  # 使用None初始化更清晰
            exception = []
            exception_lock = threading.Lock()

            if hasattr(func, "_original"):
                func = func._original

            def run_func():
                nonlocal result_cont
                try:
                    if tool_call[1]:
                        result = func(**tool_call[1])
                    else:
                        result = func()
                    result_cont = result  # 统一赋值结果
                except Exception as e:
                    with exception_lock:
                        exception.append(e)

            run_func_t = threading.Thread(target=run_func)
            run_func_t.start()
            run_func_t.join(timeout=30)

            if run_func_t.is_alive():
                with exception_lock:
                    exception.append(TimeoutError("Execution timed out after 30 seconds"))
                result_cont = "Execution timed out"

            if exception:
                return f"Error: {str(exception[0])}", True
            else:
                if tools.getPostHandler(tool_call[0]):
                    result_cont = tools.getPostHandler(tool_call[0])(result_cont)
                return str(result_cont),True

        except Exception as e:
            return f"Error: {str(e)}", True

    @staticmethod   
    def import_module(module_path: str):
        """
        动态导入工具类
        给了路径，就可以导入
        """
        try:
            spec = importlib.util.spec_from_file_location("tool", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            raise Exception(f"导入工具失败,原因：{str(e)}")
