"""
编写者：王出日
日期：2025，5，20
版本 0.5.0
描述：工具类，用于管理大模型的工具
包含：
Tools类：用于管理大模型的工具，包括注册、查询、调用等功能
"""
import inspect
import re
from .executor import ToolsExecutor
from ...utils.doc_parser import parse_docstring
from ...core.error import ToolNotFound, ToolsAddError,ToolAlreadyExists
from ...utils.type_mapper import convert_tools_for_llm

class Tool:
    name: str
    tool: callable
    description: str
    required_parameters: list
    parameters: dict
    require_confirmation: bool
    require_persistence: bool
    return_image: bool
    return_audio: bool
    return_url: bool
    schema: dict
    belongs_to: str

    def __init__(self,
                 tool: callable,
                 description: str,
                 parameters: dict = {},
                 required_parameters: list = [],
                 require_confirmation: bool = False,
                 require_persistence: bool = False,
                 return_image: bool = False,
                 return_audio: bool = False,
                 return_url: bool = False,
                 schema: dict = {},
                 belongs_to: str = None
                 ):
        self.tool = tool
        self.name = tool.__name__
        self.description = description
        self.parameters = parameters
        self.required_parameters = required_parameters
        self.require_confirmation = require_confirmation
        self.require_persistence = require_persistence
        self.return_image = return_image
        self.return_audio = return_audio
        self.return_url = return_url
        self.schema = schema
        self.belongs_to = belongs_to

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
    def execute(self, **kargs: dict) -> str:
        return self.tool(**kargs)
    def get_return_type(self):
        if self.return_image:
            return "image"
        if self.return_audio:
            return "audio"
        if self.return_url:
            return "url"
        return "text"
    def get_schema(self):
        return self.schema

class Tools:
    tools: list[Tool]
    tools_names: list[str]
    tools_schemas: list[dict]
    tools_executor: ToolsExecutor

    def __init__(self, tools_executor: ToolsExecutor = ToolsExecutor(), name: str = None):
        """
        创建一个工具集对象
        Args:
            tools_executor (ToolsExecutor): 工具执行器对象
            name (str): 工具包名称 默认为空 当你需要分发你的工具包时 建议填写
        """
        self.tools = [] 
        self.tools_names = [] 
        self.tools_schemas = [] 
        self.disable_tools = {} 
        self.tools_executor = tools_executor
        self.instance_name = name

    def _add_single_tool(self, tool_obj: Tool, source_instance_name: str):
        """
        内部方法：将单个工具对象添加到当前容器中
        """
        # 获取该工具在当前容器层级的显示名称（逻辑名称）
        logic_name = tool_obj.name
        
        # 核心修改：检测同名冲突
        if logic_name in self.tools_names:
            # 找到冲突的工具，抛出错误并提供建议
            error_msg = (
                f"检测到工具名称冲突: '{logic_name}' 已存在于当前工具集中。\n"
                f"冲突源来自工具包: '{source_instance_name if source_instance_name else '未命名包'}'。\n"
                f"建议解决方法: 在实例化 Tools 时设置 'name' 参数以启用自动命名空间（前缀），"
                f"例如: Tools(name='my_plugin')"
            )
            raise ToolAlreadyExists(error_msg)

        # 为了防止不同包之间的对象引用冲突，创建一个新的 Tool 实例进行属性封装
        new_tool = Tool(
            tool=tool_obj.tool,
            description=tool_obj.description,
            parameters=tool_obj.parameters,
            required_parameters=tool_obj.required_parameters,
            require_confirmation=tool_obj.require_confirmation,
            require_persistence=tool_obj.require_persistence,
            return_image=tool_obj.return_image,
            return_audio=tool_obj.return_audio,
            return_url=tool_obj.return_url,
            schema=tool_obj.schema.copy(),
            belongs_to=source_instance_name
        )
        
        # 同步逻辑名称
        new_tool.name = logic_name
        if "function" in new_tool.schema:
            new_tool.schema["function"]["name"] = logic_name

        self.tools.append(new_tool)
        self.tools_names.append(logic_name)
        self.tools_schemas.append(new_tool.schema)

    def add_tools(self, other: "Tools") -> None:
        self += other

    def __iadd__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError("只能与 Tools 类型的对象进行加法操作")
        for t in other.tools:
            self._add_single_tool(t, other.instance_name)
        return self

    def __add__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError("只能与 Tools 类型的对象进行加法操作")
        combined = Tools(self.tools_executor, name=self.instance_name)
        for t in self.tools:
            combined._add_single_tool(t, self.instance_name)
        for t in other.tools:
            combined._add_single_tool(t, other.instance_name)
        return combined

    def __sub__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()
        result = Tools(self.tools_executor, name=self.instance_name)
        # 减法基于原始函数对象判断
        other_funcs = {t.tool for t in other.tools}
        for t in self.tools:
            if t.tool not in other_funcs:
                result._add_single_tool(t, t.belongs_to)
        return result

    def __isub__(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()
        other_funcs = {t.tool for t in other.tools}
        for i in range(len(self.tools) - 1, -1, -1):
            if self.tools[i].tool in other_funcs:
                self.tools.pop(i)
                self.tools_names.pop(i)
                self.tools_schemas.pop(i)
        return self

    def register_no_function(self,
                name: str,
                description: str,
                required_parameters: list, 
                parameters: dict
            ):
        if not isinstance(name, str) or not name:
            raise ValueError("函数名称必须是非空字符串")
        
        # 注册无函数工具时应用前缀规则
        logic_name = name
        if self.instance_name:
            logic_name = f"{self.instance_name}_{name}"

        schema = {
            "type": "function",
            "function": {
                "name": logic_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "required": required_parameters,
                    "properties": parameters
                }
            }
        }
        _tool = Tool(
            tool=lambda **k: None,
            description=description,
            parameters=parameters,
            required_parameters=required_parameters,
            schema=schema
        )
        _tool.name = logic_name
        self.tools.append(_tool)
        self.tools_names.append(logic_name)
        self.tools_schemas.append(schema)

    def unregister(self, name: str):
        if name not in self.tools_names:
            raise ToolNotFound(name)
        index = self.tools_names.index(name)
        del self.tools_schemas[index]
        del self.tools_names[index]
        del self.tools[index]
        return True

    def register(self, description: str = None, require_confirmation: bool = False, require_persistence: bool = False, return_image: bool = False, return_audio: bool = False, return_url: bool = False):
        def decorator(func):
            self.register_tool(func, description, require_confirmation=require_confirmation, require_persistence=require_persistence, return_image=return_image, return_audio=return_audio, return_url=return_url)
            return func
        return decorator

    def register_tool(self, tool: callable, description: str = None, require_confirmation: bool = False, require_persistence: bool = False, return_image: bool = False, return_audio: bool = False, return_url: bool = False) -> dict:
        original_name = tool.__name__
        
        # 只有在 Tools(name="...") 显式命名时才强制加前缀
        logic_name = original_name
        if self.instance_name:
            logic_name = f"{self.instance_name}_{original_name}"

        if logic_name in self.tools_names:
            return self.get_tool_info(logic_name)
        
        parameters_sig = inspect.signature(tool).parameters
        required_parameters = [p for p in parameters_sig if parameters_sig[p].default is inspect.Parameter.empty]
        p_doc = parse_docstring(tool.__doc__)
        
        properties = {}
        from ...utils.type_mapper import TypeMapper
        for p_name, p in parameters_sig.items():
            param_type = p.annotation if p.annotation != inspect.Parameter.empty else str
            json_schema = TypeMapper.map_type(param_type)
            properties[p_name] = {
                "type": json_schema["type"], 
                "description": p_doc[0].get(p_name, "")
            }
            
        description = self._get_description(tool, description)
        schema = {
            "type": "function",
            "function": {
                "name": logic_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "required": required_parameters,
                    "properties": properties
                }
            }
        }
        
        _tool = Tool(
            tool=tool,
            description=description,
            parameters=properties,
            required_parameters=required_parameters,
            require_confirmation=require_confirmation,
            require_persistence=require_persistence,
            return_image=return_image,
            return_audio=return_audio,
            return_url=return_url,
            schema=schema,
            belongs_to=self.instance_name
        )
        _tool.name = logic_name
        
        self.tools.append(_tool)
        self.tools_names.append(logic_name)
        self.tools_schemas.append(schema)
        return schema

    def _get_description(self, tool, description):
        doc_content = tool.__doc__.strip() if tool.__doc__ else ""
        description_part = re.sub(r'\s*Args:\s*.*?(?=\n\s*\w+:|$)', '', doc_content, flags=re.DOTALL)
        description_part = description_part.strip()
        return description if description is not None else description_part

    def disable_tool(self, tool_name: str) -> bool:
        if tool_name not in self.disable_tools:
            for i, t in enumerate(self.tools_schemas):
                if t["function"]["name"] == tool_name:
                    self.disable_tools[tool_name] = t
                    del self.tools_schemas[i]
                    return True
        return False
        
    def enable_tool(self, tool_name: str):
        if tool_name in self.disable_tools:
            self.tools_schemas.append(self.disable_tools.pop(tool_name))
            return True
        return False

    def execute(self, _tool_calls, _mcp_client=None, timeout=60, events=None) -> any:
        return self.tools_executor.execute(_tool_calls, self, _mcp_client, timeout, events)

    async def aexecute(self, _tool_calls, _mcp_client=None, timeout=60, events=None) -> any:
        return await self.tools_executor.aexecute(_tool_calls, self, _mcp_client, timeout, events)

    def _get_tool_by_name(self, name: str) -> Tool:
        if name not in self.tools_names:
            raise ToolNotFound(name)
        return self.tools[self.tools_names.index(name)]

    def get_require_confirmations(self, name: str):
        return self._get_tool_by_name(name).require_confirmation
    
    def get_require_persistence(self, name: str):
        return self._get_tool_by_name(name).require_persistence
    
    def get_multimodal_type(self, name: str):
        return self._get_tool_by_name(name).get_return_type()
    
    def get_tools_for_llm(self) -> list:
        return convert_tools_for_llm(self)
    
    def get_tool_info(self, tool_name: str) -> dict:
        return self._get_tool_by_name(tool_name).schema

    def get_tool(self, name: str) -> callable:
        return self._get_tool_by_name(name).tool
    
    def check_tools(self, name: str) -> bool:
        if name not in self.tools_names:
            raise ToolNotFound(name)
        return True
    
    def get_tools(self) -> list:
        return self.tools_schemas