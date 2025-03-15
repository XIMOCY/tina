"""
编写者：王出日
日期：2024，12，13
版本 0.1.0
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
import ast
import importlib.util
from .parser import tina_parser
from .tools import Tools

class AgentExecutor:
    def __init__(self, parser: callable = tina_parser):
        """
        Agent的工具执行器
        """
        self.parser = parser
    @staticmethod
    def is_safe(node):
        """
        验证AST节点是否安全
        """
        if isinstance(node, ast.Expression):
            return all(AgentExecutor.is_safe(child) for child in ast.walk(node))
        if isinstance(node, ast.BinOp):
            return AgentExecutor.is_safe(node.left) and AgentExecutor.is_safe(node.right)
        if isinstance(node, ast.UnaryOp):
            return AgentExecutor.is_safe(node.operand)
        if isinstance(node, ast.Num):  # 用于Python 3.8及以下版本
            return True
        if isinstance(node, ast.Constant):  # 用于Python 3.8及以上版本
            return True
        if isinstance(node, ast.Name):
            return node.id.isidentifier() and not node.id.startswith('__')
        if isinstance(node, ast.Call):
            return AgentExecutor.is_safe(node.func) and all(AgentExecutor.is_safe(arg) for arg in node.args)
        if isinstance(node, ast.Attribute):
            return isinstance(node.value, ast.Name) and node.value.id.isidentifier()
        raise ValueError(f"Unsupported AST node: {node}")
    
    @staticmethod
    def execute(tool_call: tuple[str, dict, bool], tools: type,is_permissions: bool = True,LLM:type = None) -> tuple[str, bool]:
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
            tool_call (str): 字符串,内含解析器会解析的工具调用
            tools (type): 工具类，用于内部调用检测工具是否存在和参数验证
            is_permissions (bool, optional): 对执行字符串进行安全验证，默认是True.
        Returns:
            tuple[str, bool]: 元组，执行结果和是否成功
        """
        if not tool_call[2]:
            return result
        module = AgentExecutor.import_module(tools.getToolsPath(name = tool_call[0]))

        func = getattr(module, tool_call[0])
        if tool_call[1]:
            result = func(**tool_call[1])
        else:
            result = func()
        
        #参数判断
        if isinstance(result,str):
            return result,True
        elif isinstance(result, list):
            result_str = "，".join(f"列表第{index+1}元素{value}" for index, value in enumerate(result))
        elif isinstance(result,bool):
            if result:
                result_str = "True"
            else:
                result_str = "False"
        elif isinstance(result, dict):
            result_str = "，".join(f"字典的{key}键对应的值为{value}" for key, value in result.items())
        else:
            result_str = str(result)
        return result_str,True
    @staticmethod
    def _extract_value(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return [AgentExecutor._extract_value(el) for el in node.elts]
        else:
            raise TypeError(f"不支持的节点类型: {type(node)}")

    
    @staticmethod   
    def import_module(module_path:str):
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
