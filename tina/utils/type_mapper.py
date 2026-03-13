"""
Python类型到JSON Schema映射工具
用于将Python类型系统转换为大模型可理解的JSON Schema格式
"""
import inspect
from typing import Any, Dict, List, Union, get_type_hints, get_origin, get_args
from enum import Enum


class TypeMapper:
    """
    Python类型到JSON Schema类型的映射器
    """
    
    # 基础类型映射
    PYTHON_TO_JSON_TYPES = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        tuple: "array",
        set: "array",
        frozenset: "array",
        bytes: "string",
        bytearray: "string",
    }
    
    @staticmethod
    def map_type(python_type: Any) -> Dict[str, Any]:
        """
        将Python类型映射为JSON Schema
        
        Args:
            python_type: Python类型对象
            
        Returns:
            Dict: JSON Schema定义
        """
        # 处理None类型
        if python_type is None or python_type is type(None):
            return {"type": "null"}
        
        # 处理基础类型
        if python_type in TypeMapper.PYTHON_TO_JSON_TYPES:
            return {"type": TypeMapper.PYTHON_TO_JSON_TYPES[python_type]}
        
        # 处理typing模块的泛型类型
        origin = get_origin(python_type)
        args = get_args(python_type)
        
        # 处理Union类型 (包括Optional)
        if origin is Union:
            # 特殊处理Optional[T] (实际上是Union[T, None])
            if len(args) == 2 and type(None) in args:
                non_none_type = args[0] if args[1] is type(None) else args[1]
                schema = TypeMapper.map_type(non_none_type)
                schema["nullable"] = True
                return schema
            else:
                # 一般Union类型
                schemas = [TypeMapper.map_type(arg) for arg in args]
                return {"anyOf": schemas}
        
        # 处理List类型
        if origin in (list, List):
            if args:
                items_schema = TypeMapper.map_type(args[0])
                return {"type": "array", "items": items_schema}
            else:
                return {"type": "array"}
        
        # 处理Dict类型
        if origin in (dict, Dict):
            schema = {"type": "object"}
            if args and len(args) == 2:
                # args[0]是key类型，args[1]是value类型
                # JSON中key总是string，所以我们只关心value类型
                value_schema = TypeMapper.map_type(args[1])
                schema["additionalProperties"] = value_schema
            else:
                schema["additionalProperties"] = True
            return schema
        
        # 处理Tuple类型
        if origin in (tuple, tuple):
            if args:
                if len(args) == 2 and args[1] is ...:
                    # Tuple[T, ...] 表示元素都是T的元组
                    items_schema = TypeMapper.map_type(args[0])
                    return {"type": "array", "items": items_schema}
                else:
                    # 固定长度的元组 Tuple[T1, T2, ...]
                    items_schemas = [TypeMapper.map_type(arg) for arg in args]
                    return {"type": "array", "items": items_schemas, "minItems": len(args), "maxItems": len(args)}
            else:
                return {"type": "array"}
        
        # 处理Enum类型
        if inspect.isclass(python_type) and issubclass(python_type, Enum):
            values = [e.value for e in python_type]
            if all(isinstance(v, str) for v in values):
                return {"type": "string", "enum": values}
            elif all(isinstance(v, (int, float)) for v in values):
                return {"type": "number", "enum": values}
            else:
                return {"enum": values}
        
        # 默认情况下，认为是object类型
        return {"type": "object"}
    
    @staticmethod
    def generate_function_schema(func) -> Dict[str, Any]:
        """
        为函数生成JSON Schema
        
        Args:
            func: 函数对象
            
        Returns:
            Dict: 函数的JSON Schema定义
        """
        # 获取函数签名
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        # 构建parameters对象
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            # 获取参数类型
            param_type = type_hints.get(param_name, Any)
            param_schema = TypeMapper.map_type(param_type)
            
            # 处理默认值
            if param.default is not inspect.Parameter.empty:
                param_schema["default"] = param.default
            else:
                # 没有默认值的参数是必需的
                required.append(param_name)
            
            properties[param_name] = param_schema
        
        schema = {
            "name": func.__name__,
            "description": inspect.getdoc(func) or "",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
        
        return schema

    @staticmethod
    def generate_tools_schema(tools_list: List) -> List[Dict[str, Any]]:
        """
        为工具列表生成完整的JSON Schema
        
        Args:
            tools_list: 工具列表
            
        Returns:
            List[Dict]: 工具的JSON Schema定义列表
        """
        schemas = []
        for tool in tools_list:
            if isinstance(tool, dict) and "function" in tool:
                # 如果已经是部分schema格式
                schema = {
                    "type": "function",
                    "function": tool["function"]
                }
                schemas.append(schema)
            elif callable(tool):
                # 如果是函数对象
                func_schema = TypeMapper.generate_function_schema(tool)
                schema = {
                    "type": "function",
                    "function": func_schema
                }
                schemas.append(schema)
        return schemas


# 便捷函数
def python_type_to_json_schema(python_type: Any) -> Dict[str, Any]:
    """
    将Python类型转换为JSON Schema
    
    Args:
        python_type: Python类型对象
        
    Returns:
        Dict: JSON Schema定义
    """
    return TypeMapper.map_type(python_type)


def function_to_tool_schema(func) -> Dict[str, Any]:
    """
    将函数转换为工具的JSON Schema
    
    Args:
        func: 函数对象
        
    Returns:
        Dict: 工具的JSON Schema定义
    """
    func_schema = TypeMapper.generate_function_schema(func)
    return {
        "type": "function",
        "function": func_schema
    }


def tools_to_json_schema(tools_list: List) -> List[Dict[str, Any]]:
    """
    将工具列表转换为JSON Schema列表
    
    Args:
        tools_list: 工具列表
        
    Returns:
        List[Dict]: 工具的JSON Schema定义列表
    """
    return TypeMapper.generate_tools_schema(tools_list)


def convert_tools_for_llm(tools) -> List[Dict[str, Any]]:
    """
    将Tina Tools对象转换为大模型可用的工具格式
    
    Args:
        tools: Tina Tools对象
        
    Returns:
        List[Dict]: 大模型可用的工具列表
    """
    result = []
    for tool_dict in tools.tools_schemas:
        # 直接使用已有的工具定义
        result.append({
            "type": "function",
            "function": {
                "name": tool_dict["function"]["name"],
                "description": tool_dict["function"]["description"],
                "parameters": tool_dict["function"]["parameters"]
            }
        })
    return result