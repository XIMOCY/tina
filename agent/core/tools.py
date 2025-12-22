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
from ...utils.doc_parser import parse_docstring
from ...core.error import ToolNotFound,ToolsAddError

class Tool:
    tool: callable
    description: str
    parameters: dict
    require_confirmation:bool
    require_persistence:bool

    def __init__(self,
                 tool: callable,
                 description: str,
                 parameters: dict = {},
                 require_confirmation:bool = False,
                 require_persistence:bool = False
                 ):
        self.tool = tool
        self.description = description
        self.parameters = parameters
        self.require_confirmation = require_confirmation
        self.require_persistence = require_persistence


    def get_tool(self):
        return self.tool
    def get_description(self):
        return self.description
    def get_parameters(self):
        return self.parameters
    def get_require_confirmation(self):
        return self.require_confirmation
    def get_require_persistence(self):
        return self.require_persistence


class Tools:
    """
    使用此类来管理你的工具，可以注册、查询、调用等功能
    """
    tools:list[Tool] = [] # 工具列表
    tools_schemas:list[dict]# 工具的JSON Schema 用于快速传递给大模型
    tools_functions:dict[str, callable] # 工具名称对应的函数
    tools_names:list[str] # 工具名称列表
    tools_parameters:list[dict] # 工具参数列表
    require_confirmations:dict[str,bool] # 是否需要确认执行的标识符
    require_persistences:dict[str,bool]   # 是否需要持久化的标识符
    disable_tools:dict[str,dict] # 禁用的工具列表
    tools_executor:ToolsExecutor

    # 工具集合操作
    def add_tools(self, tools: "Tools") -> None:
        self += tools

    def __iadd__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()
        self._add_tools_from_other_tools(other, self)
        return self

    def __add__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()

        combined = Tools()
        # 先复制当前实例的内容
        combined.tools_schemas = self.tools_schemas.copy()
        combined.tools_functions = self.tools_functions.copy()
        combined.tools_names = self.tools_names.copy()
        combined.tools_parameters = self.tools_parameters.copy()
        # test
        combined.tools_tool = self.tools_tool.copy()


        # 遍历另一个实例的工具
        self._add_tools_from_other_tools(other, combined)

        return combined

    def _add_tools_from_other_tools(self, other:'Tools', combined:'Tools'):
        for tool_dict in other.tools_schemas:
            tool_name = tool_dict["function"]["name"]
            if tool_name not in combined.tools_names:
                combined.tools_schemas.append(tool_dict)
                combined.tools_names.append(tool_name)
                # 获取对应参数（用 name 对应索引）
                try:
                    index = other.tools_names.index(tool_name)
                    combined.tools_parameters.append(other.tools_parameters[index])
                except (ValueError, IndexError):
                    # 如果找不到对应参数，就用空或默认值
                    combined.tools_parameters.append({})
                combined.tools_functions[tool_name] = other.tools_functions.get(tool_name)
                # test
                if tool_name in other.tools_tool:
                    combined.tools_tool[tool_name] = other.tools_tool[tool_name]

    # 打印工具列表
    def __str__(self):
        result = "工具列表:\n"
        for tool_dict in self.tools_schemas:
            tool_name = tool_dict["function"]["name"]
            result += f"  {tool_name}\n"
            result += f"    说明: {tool_dict['function']['description']}\n"
            result += f"    参数: {tool_dict['function']['parameters']}\n"
            result += f"    ─\n"
        return result
    
    def __init__(self,tools_executor:ToolsExecutor=ToolsExecutor()):
        """
        使用此类来管理你的工具，可以注册、查询、调用等功能
        可以使用一些自带的工具来调试
        Args:
            tools_executor (ToolsExecutor): 工具执行器，默认实现了一个执行器
        """
        self.tools = [] # 工具列表
        self.tools_schemas = [] # 工具的JSON Schema
        self.tools_functions = {} # 工具名称对应的函数
        self.tools_tool:dict[str,Tool] = {} # name对应的Tool实例
        self.tools_names = [] # 工具名称列表
        self.tools_parameters = [] # 工具参数列表
        self.disable_tools = {} # 禁用的工具列表
        self.tools_executor = tools_executor


    # 注册工具部分代码
    def register_no_function(self,
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
        self.tools_names.append(name)
        # 将参数信息添加到tools_parameters_dict中
        self.tools_parameters.append(
            {
                "name": name,
                "parameters":[f"{k}:{v['type']}" for k,v in parameters.items()] 
            }
        )
        # 将工具信息添加到tools列表中
        self.tools_schemas.append({
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


    def unregister(self, name: str):
        """
        注销工具
        Args:
            name (str): 工具名称
        """
        if name not in self.tools_names:
            raise ToolNotFound(name)
        index = self.tools_names.index(name)
        del self.tools_schemas[index]
        del self.tools_names[index]
        del self.tools_parameters[index]
        return True

    def register(self,description:str=None,require_confirmation:bool=False,require_persistence:bool=False):
        """
        注册一个工具，装饰器
        Args:
            tool (callable): 工具函数
            description (str): 工具描述
            post_handler (callable, optional): 工具执行后的处理函数，用于处理工具返回的结果
        """
        def decorator(func):
            self.register_tool(func,description,require_confirmation=require_confirmation,require_persistence=require_persistence)
            return func
        return decorator

    def register_tool(self,tool:callable,description:str=None,require_confirmation:bool=False,require_persistence:bool=False)->dict:
        """
        注册工具并进行类型检查
        
        Args:
            tool (callable): 工具函数
            description (str, optional): 工具描述
            
        Returns:
            dict: 注册的工具信息
        """
        name = tool.__name__
        if name in self.tools_names:
            return
        
        
        properties = {}
        parameters = inspect.signature(tool).parameters
        required_parameters = [p for p in parameters if parameters[p].default is inspect.Parameter.empty]
        p_doc = parse_docstring(tool.__doc__)
        parameters = self._get_parameters(name, parameters, required_parameters, p_doc, properties)
        description = description if description is not None else tool.__doc__.strip()
        _tool = Tool(
            tool=tool,
            description=description,
            parameters=parameters,
            require_confirmation=require_confirmation,
            require_persistence=require_persistence,

        )
        self.tools.append(_tool)
        self.tools_tool.update({name: _tool})
        self.set_functon_to_tool(tool, name)
        self._update_tools_name_list(name)


        self._update_tools(description, name, parameters)

        return self.get_tools()[-1]
    def disable_tool(self, tool_name: str) -> bool:
        """
        禁用工具，只会在工具列表中移除该工具，但不会删除工具函数，依然存在于工具列表中，只是暂时不被大模型所知道
        Args:
            tool_name (str): 工具名称
        Returns:
            bool: 是否成功禁用工具
        """
        if tool_name not in self.disable_tools:
            for i, t in enumerate(self.tools_schemas):
                if t["function"]["name"] == tool_name:
                    self.disable_tools[tool_name] = t
                    del self.tools_schemas[i]
                    return True
        return False
        
    def enable_tool(self, tool_name: str):
        """
        启用工具，将禁用的工具重新添加到工具列表中
        Args:
            tool_name (str): 工具名称
        """
        if tool_name in self.disable_tools:
            self.tools_schemas.append(self.disable_tools.pop(tool_name))
            return True
        return False
        

    def set_functon_to_tool(self, tool, name):
        self.tools_functions[name] = tool

    def _update_tools_name_list(self, name):
        self.tools_names.append(name)


    def _update_tools(self, description, name, parameters):
        self.tools_schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        })

    def _get_parameters(self, name, parameters, required_parameters, p_doc, properties):
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
    

    # 工具执行代码
    def execute(self,_tool_calls,_mcp_client=None,timeout=60,events=None)->any:
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
        _tool_result = self.tools_executor.execute(
            _tool_calls,
            self,
            _mcp_client,
            timeout,
            events
        )
        return _tool_result

    async def aexecute(self,_tool_calls,_mcp_client=None,timeout = 60,events =None)->any:
        """
        工具执行的异步方法
        """
        return await self.tools_executor.aexecute(_tool_calls,self,_mcp_client,timeout,events)
    

    # 获取工具信息
    def get_require_confirmations(self,name:str):
        return self.tools_tool[name].get_require_confirmation()
    def get_tools_for_llm(self) -> list:
        """
        获取适用于大语言模型的工具格式列表
        
        Returns:
            list: 大语言模型可用的工具列表，符合OpenAI工具调用格式
        """
        from ...utils.type_mapper import convert_tools_for_llm
        return convert_tools_for_llm(self)
    
    def get_tool_info(self,tool_name:str)->dict:
        """
        获取工具的信息
        Args:
            tool_name (str): 工具名称
        Returns:
            dict: 工具的信息
        """
        for tool_dict in self.tools_schemas:
            if tool_dict["function"]["name"] == tool_name:
                return tool_dict
        return None

    def get_tool(self,name:str)->callable:
        if name not in self.tools_names:
            return None  
        return self.tools_functions.get(name,None)
    
    def check_tools(self,name:str)->bool:
        """
        检查工具是否存在
        Args:
            name (str): 工具名称
        Returns:
            bool: 工具是否存在
        """
        return (name in self.tools_names)
    
    def get_tools(self)->list:
        """返回工具"""
        return self.tools_schemas
