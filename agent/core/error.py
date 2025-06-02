"""
tina错误类定义
"""
class TinaError(Exception):
    pass

class TinaWarning(Warning):
    pass

class TinaInfo(UserWarning):
    pass

class ToolNotFound(TinaError):
    def __init__(self, tool_name: str):
        super().__init__(f"Tool {tool_name} not found. \n工具 {tool_name}并没有找到，查看是否为拼写错误或者没有注册")
class ToolsAddError(TinaError):
    def __init__(self):
        super().__init__("Error adding Tools: Only objects of the Tools class can be merged. Please ensure both objects are instances of the Tools class.  \n工具合并失败：仅支持将两个Tools类对象进行合并。请检查参与合并的对象是否均为Tools类实例。")
class ToolParameterError(TinaError):
    def __init__(self, tool_name: str, parameter_name: str, parameter_type: str):
        super().__init__(f"{tool_name} parameter {parameter_name} should be {parameter_type}.")
class ToolParameterNotFound(TinaError):
    def __init__(self, tool_name: str, parameter_name: str):
        super().__init__(f"{tool_name} parameter {parameter_name} not found.")
class ToolParameterTypeError(TinaError):
    def __init__(self, tool_name: str, parameter_name: str, expected_type: str, actual_type: str):
        super().__init__(f"{tool_name} parameter {parameter_name} should be {expected_type}, but got {actual_type}."\
                         "\n工具{tool_name}的参数{parameter_name}应该是{expected_type}类型，但是实际是{actual_type}类型。，请检查参数类型是否正确。")
