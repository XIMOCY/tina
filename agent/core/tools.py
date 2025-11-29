"""
编写者：王出日
日期：2025，5，20
版本 0.5.0
描述：工具类，用于管理大模型的工具
包含：
Tools类：用于管理大模型的工具，包括注册、查询、调用等功能
"""
import inspect
from .executor import ToolsExecutor
from typing import Any, Dict, List, get_type_hints, get_origin, get_args
from ...utils.doc_parser import parse_docstring
from ...core.error import ToolNotFound,ToolsAddError,PostHandlerTypeError

class Tools:
    """
    使用此类来管理你的工具，可以注册、查询、调用等功能
    可以使用一些自带的工具来调试
    """
    def add_tools(self, tools: "Tools") -> None:
        self += tools
    def addTools(self, tools: "Tools") -> None:
        self.add_tools(tools)
    def __add__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()

        combined = Tools()
        # 先复制当前实例的内容
        combined.tools = self.tools.copy()
        combined.tool = self.tool.copy()
        combined.tools_name_list = self.tools_name_list.copy()
        combined.tools_parameters_list = self.tools_parameters_list.copy()
        combined.post_handler = self.post_handler.copy()

        # 遍历另一个实例的工具
        for tool_dict in other.tools:
            tool_name = tool_dict["function"]["name"]
            if tool_name not in combined.tools_name_list:
                combined.tools.append(tool_dict)
                combined.tools_name_list.append(tool_name)
                # 获取对应参数（用 name 对应索引）
                try:
                    index = other.tools_name_list.index(tool_name)
                    combined.tools_parameters_list.append(other.tools_parameters_list[index])
                except (ValueError, IndexError):
                    # 如果找不到对应参数，就用空或默认值
                    combined.tools_parameters_list.append({})
                # 添加工具函数和后处理
                combined.tool[tool_name] = other.tool.get(tool_name)
                combined.post_handler[tool_name] = other.post_handler.get(tool_name)

        return combined
    def __str__(self):
        result = "工具列表:\n"
        for tool_dict in self.tools:
            tool_name = tool_dict["function"]["name"]
            result += f"  {tool_name}\n"
            result += f"    说明: {tool_dict['function']['description']}\n"
            result += f"    参数: {tool_dict['function']['parameters']}\n"
            result += f"    ─\n"
        return result
    def __init__(self,useSystemTools=False,useTerminal=False,tools_executor:ToolsExecutor=ToolsExecutor(True)):
        """
        使用此类来管理你的工具，可以注册、查询、调用等功能
        可以使用一些自带的工具来调试
        Args:
            useSystemTools (bool, optional): 是否使用系统工具. 默认为False.
            useTerminal (bool, optional): 是否使用终端工具.默认为False.
            setGoal (bool, optional): 是否注册目标管理工具（由Agent执行）.默认为False.
        """
        self.tools = [] # 工具的JSON Schema
        self.tool = {} # 工具名称对应的函数
        self.tools_name_list = [] # 工具名称列表
        self.tools_parameters_list = [] # 工具参数列表
        self.post_handler = {}
        self.tools_executor = tools_executor

        self._extendTools(useSystemTools,useTerminal)

    def _check_post_handler_compatibility(self, tool: callable, post_handler: callable, tool_name: str):
        """
        检查工具返回类型和后处理器参数类型的兼容性
        
        Args:
            tool (callable): 工具函数
            post_handler (callable): 后处理器函数
            tool_name (str): 工具名称
            
        Raises:
            PostHandlerTypeError: 当类型不兼容时抛出
        """
        if post_handler is None:
            return  
        
        try:
            tool_hints = get_type_hints(tool)
            tool_return_type = tool_hints.get('return', None)
            
            post_handler_hints = get_type_hints(post_handler)
            post_handler_signature = inspect.signature(post_handler)
            post_handler_params = list(post_handler_signature.parameters.values())
            
            if not post_handler_params:
                raise PostHandlerTypeError(
                    tool_name, 
                    "至少一个参数", 
                    "无参数",
                    "后处理器必须接受工具的返回值作为参数"
                )
            
            first_param = post_handler_params[0]
            first_param_type = post_handler_hints.get(first_param.name, None)
            
            if tool_return_type is None and first_param_type is None:
                print(f"警告: 工具 '{tool_name}' 和其后处理器都缺少类型注解，建议添加类型注解以确保类型安全")
                return
            
            if tool_return_type is None:
                print(f" 警告: 工具 '{tool_name}' 缺少返回类型注解，无法进行类型检查")
                return
                
            if first_param_type is None:
                print(f"警告: 工具 '{tool_name}' 的后处理器缺少参数类型注解，无法进行类型检查")
                return
            
            # 进行类型兼容性检查
            if not self._is_type_compatible(tool_return_type, first_param_type):
                raise PostHandlerTypeError(
                    tool_name,
                    self._format_type_name(first_param_type),
                    self._format_type_name(tool_return_type),
                    f"工具返回 {self._format_type_name(tool_return_type)}，但后处理器期望 {self._format_type_name(first_param_type)}"
                )
                
        except PostHandlerTypeError:
            # 重新抛出我们的自定义错误
            raise PostHandlerTypeError(
                tool_name,
                self._format_type_name(first_param_type) if first_param_type else "无参数",
                self._format_type_name(tool_return_type) if tool_return_type else "无返回值",
                "后处理器参数类型与工具返回类型不兼容"
            )
        except Exception as e:
            print(f"警告: 工具 '{tool_name}' 类型检查时发生错误: {str(e)}，跳过类型检查")
    
    def _is_type_compatible(self, tool_return_type, handler_param_type) -> bool:
        """
        检查两个类型是否兼容
        
        Args:
            tool_return_type: 工具返回类型
            handler_param_type: 后处理器参数类型
            
        Returns:
            bool: 是否兼容
        """
        # 完全相同的类型
        if tool_return_type == handler_param_type:
            return True
        
        # 检查是否是基本类型的子类关系
        try:
            # str 和 Any 兼容
            if handler_param_type == str or str(handler_param_type) == 'typing.Any':
                return True
            
            # 检查是否为Union类型
            if hasattr(handler_param_type, '__origin__'):
                origin = get_origin(handler_param_type)
                if origin is not None:
                    args = get_args(handler_param_type)
                    # Union类型检查
                    if str(origin) == 'typing.Union' and tool_return_type in args:
                        return True
            
            # 基本类型兼容性检查
            if isinstance(tool_return_type, type) and isinstance(handler_param_type, type):
                return issubclass(tool_return_type, handler_param_type)
                
        except Exception:
            # 如果类型检查出错，采用保守策略：允许通过
            return True
        
        return False
    
    def _format_type_name(self, type_hint) -> str:
        """
        格式化类型名称用于显示
        
        Args:
            type_hint: 类型提示
            
        Returns:
            str: 格式化的类型名称
        """
        if type_hint is None:
            return "Any"
        
        # 处理基本类型
        if hasattr(type_hint, '__name__'):
            return type_hint.__name__
        
        # 处理复杂类型（如Union、List等）
        return str(type_hint).replace('typing.', '')

    def _extendTools(self, useSystemTools:bool=False,useTerminal:bool=False,setGoal:bool=False):
        if useSystemTools:
            from ...utils.system_tools import getTime,shotdownSystem,listDir,getPath,makeDir,readCode,writeCode,delay
            SystemTools = [
                {
                    "tool":getTime,
                    "description": "获取当前时间",
                },
                {
                    "tool":shotdownSystem,
                    "description": "该工具会关闭计算机",
                },
                {
                    "tool":delay,
                    "description":"延时指定秒数",
                },
                {
                    "tool":makeDir,
                    "description":"创建一个文件夹，返回该文件夹的路径",
                },
                {
                    "tool":readCode,                    
                    "description":"读取文件内容",
                },
                {
                    "tool":writeCode,
                    "description":"写入或者覆盖文件内容，如果文件不存在会自动创建，你可以用它来输出各种文件",
                },
                {
                    "tool":listDir,
                    "description":"列出文件夹下的文件和文件夹",
                },
                {
                    "tool":getPath,
                    "description":"获取文件的绝对路径",
                }
            ]
            self.multiregister(SystemTools)
            
        if useTerminal:
            from ...utils.system_tools import terminal
            terminalTools =[
                {
                    "tool": terminal,
                    "description":"向终端发送一个指令，在windows下使用的是powershell，在linux下使用的是bash",
                }
            ]
            self.multiregister(terminalTools)
                        
    def registerNotWithFunction(self,
                name:str,
                description:str,
                required_parameters:list, 
                parameters:dict
            ):
        """
        注册工具，将工具信息添加到tools列表中
        Args:
            name (str): 函数的名称，一定要正确
            description (str): 函数的描述，可以详细描述函数的功能
            required_parameters (list): 一定要有输入的参数列表
            parameters (dict): 参数的详细信息，所有的参数都要有类型和描述
                格式：
                    {
                    "参数名": {
                        "type": "参数类型",
                        "description": "参数描述"
                        }
                    }
        Raises:
            ValueError: 如果输入参数不符合要求
        """
        # 验证输入参数的有效性
        if not isinstance(name, str) or not name:
            raise ValueError("函数名称必须是非空字符串")
        if not isinstance(description, str):
            raise ValueError("函数描述必须是字符串")
        if not isinstance(required_parameters, list):
            raise ValueError("必需参数必须是一个列表")
        if not isinstance(parameters, dict):
            raise ValueError("参数必须是一个字典")
        #将名称添加到tools_list中
        self.tools_name_list.append(name)
        # 将参数信息添加到tools_parameters_dict中
        self.tools_parameters_list.append(
            {
                "name": name,
                "parameters":[f"{k}:{v['type']}" for k,v in parameters.items()] 
            }
        )
        # 将工具信息添加到tools列表中
        self.tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "required": required_parameters,
                    "properties": parameters
                }
            }
        })

    def multiregister(self, tools: list):
        """
        注册多个工具
        """
        for tool in tools:
            self.registerTool(
                tool=tool["tool"],
                description=tool["description"],
                post_handler=tool.get("post_handler", None)
            )

    def unregister(self, name: str):
        """
        注销工具
        Args:
            name (str): 工具名称
        """
        if name not in self.tools_name_list:
            raise ToolNotFound(name)
        index = self.tools_name_list.index(name)
        del self.tools[index]
        del self.tools_name_list[index]
        del self.tools_parameters_list[index]
        return True

    def register(self,description:str=None,post_handler:callable=None):
        """
        注册一个工具，装饰器
        Args:
            tool (callable): 工具函数
            description (str): 工具描述
            post_handler (callable, optional): 工具执行后的处理函数，用于处理工具返回的结果
        """
        def decorator(func):
            self.registerTool(func,description,post_handler)
            return func
        return decorator

    def registerTool(self,tool:callable,description:str=None,post_handler:callable=None)->dict:
        """
        注册工具并进行类型检查
        
        Args:
            tool (callable): 工具函数
            description (str, optional): 工具描述
            post_handler (callable, optional): 后处理器函数
            
        Returns:
            dict: 注册的工具信息
            
        Raises:
            PostHandlerTypeError: 当工具返回类型与后处理器参数类型不兼容时
        """
        name = tool.__name__
        if name in self.tools_name_list:
            return
        
        self._check_post_handler_compatibility(tool, post_handler, name)
        
        properties = {}
        self.tool[name] = tool
        self.__update_tools_name_list(name)
        parameters = inspect.signature(tool).parameters
        required_parameters = [p for p in parameters if parameters[p].default is inspect.Parameter.empty]
        p_doc = parse_docstring(tool.__doc__)
        parameters = self.__get_parameters(name, parameters, required_parameters, p_doc, properties)
        self.__update_post_handler(post_handler, name)
        description = description if description is not None else tool.__doc__.strip()
        self.__update_tools(description, name, parameters)

        return self.getTools()[-1]

    def __update_tools_name_list(self, name):
        self.tools_name_list.append(name)

    def __update_post_handler(self, post_handler, name):
        self.post_handler.update({name: post_handler})

    def __update_tools(self, description, name, parameters):
        self.tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        })

    def __get_parameters(self, name, parameters, required_parameters, p_doc, properties):
        for p_name,p in parameters.items():
            # 使用TypeMapper来处理参数类型
            from ...utils.type_mapper import TypeMapper
            param_type = p.annotation if p.annotation != inspect.Parameter.empty else str
            json_schema = TypeMapper.map_type(param_type)
            properties.update({
                p_name: {
                    "type": json_schema["type"], 
                    "description": p_doc[0].get(p_name,"")
                }
            })
        parameters = {
            "type": "object",
            "required": required_parameters,
            "properties": properties
        }
        
        return parameters
    
    def getToolsForLLM(self) -> list:
        """
        获取适用于大语言模型的工具格式列表
        
        Returns:
            list: 大语言模型可用的工具列表，符合OpenAI工具调用格式
        """
        from ...utils.type_mapper import convert_tools_for_llm
        return convert_tools_for_llm(self)
    
    def getPostHandler(self,name:str)->callable:
        """
        获取工具的后处理函数
        """
        return self.post_handler.get(name,None)
    def getTool(self,name:str)->callable:
        if name not in self.tools_name_list:
            return None  
        return self.tool.get(name,None)
    
    def execute(self,_tool_calls,_tools)->any:
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
        self.check_tool_in_tools(_tool_calls)
            
        _tool_result = self.tools_executor.execute(
            _tool_calls,
            _tools
        )
        return _tool_result

    def check_tool_in_tools(self, _tool_calls):
        for _tool_call in _tool_calls:
            _tool_name = _tool_call["function"]["name"]
            if _tool_name not in self.tools_name_list:
                raise ToolNotFound(_tool_name)
            _tool = self.getTool(_tool_name)
            if _tool is None:
                raise ToolNotFound(_tool_name)
    async def aexecute(self,_tool_calls,_tools)->any:
        """
        工具执行的异步方法
        """
        self.check_tool_in_tools(_tool_calls)
        return await self.tools_executor.aexecute(_tool_calls,_tools)
        
    def checkTools(self,name:str)->bool:
        """
        检查工具是否存在
        Args:
            name (str): 工具名称
        Returns:
            bool: 工具是否存在
        """
        return (name in self.tools_name_list)
    
    def getTools(self,enable:bool=True)->list:
        """返回工具"""
        return self.tools

def convert_tools_for_llm(tools_instance: Tools) -> List[Dict[str, Any]]:
    """
    将 Tools 实例转换为适配大语言模型（如 OpenAI 格式）的工具列表。
    
    Args:
        tools_instance (Tools): 工具管理器实例
    
    Returns:
        List[Dict[str, Any]]: 兼容 LLM 工具调用格式的工具列表
    """
    return [
        {
            "type": tool_dict["type"],
            "function": tool_dict["function"]
        }
        for tool_dict in tools_instance.tools
    ]