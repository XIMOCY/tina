"""
编写者：王出日
日期：2026，1，24
版本 0.5.0
描述：工具类，采用挂载式架构，支持递归搜集。
包含：
Tools类：用于管理大模型的工具，包括注册、查询、调用等功能
"""

from __future__ import annotations

import inspect
import re
from typing import Callable, List, Dict
from .executor import ToolsExecutor
from ...utils.doc_parser import parse_docstring
from ...core.error import ToolNotFound, ToolsAddError, ToolAlreadyExists, ToolsNotNamed
from ...utils.type_mapper import convert_tools_for_llm


class Tool:
    name: str
    metadata: dict
    tool: Callable
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

    def __init__(
        self,
        tool: Callable,
        name: str,
        description: str,
        metadata: dict = {},
        parameters: dict = {},
        required_parameters: list = [],
        require_confirmation: bool = False,
        require_persistence: bool = False,
        return_image: bool = False,
        return_audio: bool = False,
        return_url: bool = False,
        schema: dict = {},
        belongs_to: str = None,
    ):
        self.tool = tool
        self.name = name
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
        self.metadata = metadata

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
    _direct_tools: List[Tool]
    _sub_bundles: List["Tools"]
    tools_executor: ToolsExecutor

    def __init__(
        self,
        tools_executor: ToolsExecutor = ToolsExecutor(),
        name: str = None,
        metadata: dict = None,
    ):
        """
        创建一个工具集对象
        Args:
            tools_executor (ToolsExecutor): 工具执行器对象
            name (str): 工具包名称 默认为空 当你需要分发你的工具包时 建议填写
            metadata (dict): 描述工具包的元数据
        """
        self._direct_tools = []
        self._sub_bundles = []
        self.disable_tools = {}
        self.tools_executor = tools_executor
        self.instance_name = name
        self.metadata = metadata

    @property
    def tools(self) -> List[Tool]:
        """递归搜集所有本级及子包的工具对象"""
        all_t = self._direct_tools.copy()
        for bundle in self._sub_bundles:
            all_t.extend(bundle.tools)
        return all_t

    @property
    def tools_names(self) -> List[str]:
        """动态生成当前所有工具的名称列表"""
        return [t.name for t in self.tools]

    @property
    def tools_schemas(self) -> List[Dict]:
        """动态生成当前所有工具的 JSON Schema 列表"""
        return [t.schema for t in self.tools if t.name not in self.disable_tools]

    def _check(self, other):
        if not isinstance(other, Tools):
            raise ToolsAddError()
        if not self.instance_name or not other.instance_name:
            raise ToolsNotNamed()

    def __iadd__(self, other: "Tools"):
        self._check(other)
        if other not in self._sub_bundles:
            # 检查同名冲突，保护命名空间
            conflicts = set(self.tools_names) & set(other.tools_names)
            if conflicts:
                raise ToolAlreadyExists(f"挂载失败：工具 {conflicts} 已存在。")
            self._sub_bundles.append(other)
        return self

    def __isub__(self, other: "Tools"):
        self._check(other)
        if other in self._sub_bundles:
            self._sub_bundles.remove(other)
        return self

    def __add__(self, other: "Tools"):
        self._check(other)
        combined = Tools(
            self.tools_executor, name=self.instance_name, metadata=self.metadata
        )
        combined += self
        combined += other
        return combined

    def __sub__(self, other: "Tools"):
        self._check(other)
        result = Tools(self.tools_executor, name=self.instance_name)
        result += self
        result -= other
        return result

    def add_tools(self, tools: "Tools" | list["Tools"]):
        """
        添加工具包
        Args:
            tools (Tools): 工具包对象
        """
        if type(tools) is list:
            for tool in tools:
                self += tool
            return

        self += tools

    def sub_tools(self, tools: "Tools" | list["Tools"]):
        """
        减去工具包
        Args:
            tools (Tools): 减去工具包对象
        """
        if type(tools) is list:
            for tool in tools:
                self -= tool
            return
        self -= tools

    # --- 注册管理 ---

    def register(
        self,
        description: str = None,
        require_confirmation: bool = False,
        require_persistence: bool = False,
        return_image: bool = False,
        return_audio: bool = False,
        return_url: bool = False,
    ):
        """
        注册一个工具，只需要打上这个装饰器即可
        会自动解析你的注释
        @[你实例化的名称].register()
        Args:
            description (str): 工具的描述
            require_confirmation (bool): 是否需要用户确认
            require_persistence (bool): 是否需要持久化运行
            return_image (bool): 是否返回图片 多模态Agent适用 会自动地把工具的图片提交给模型
            return_audio (bool): 是否返回音频 多模态Agent适用 会自动地把工具的音频提交给模型
            return_url (bool): 是否返回 URL 多模态Agent适用 会自动地把URL提交给模型
        """

        def decorator(func):
            self.register_tool(
                func,
                description,
                require_confirmation=require_confirmation,
                require_persistence=require_persistence,
                return_image=return_image,
                return_audio=return_audio,
                return_url=return_url,
            )
            return func

        return decorator

    def register_tool(
        self,
        tool: Callable,
        description: str = None,
        require_confirmation: bool = False,
        require_persistence: bool = False,
        return_image: bool = False,
        return_audio: bool = False,
        return_url: bool = False,
    ) -> dict:
        """
        注册一个工具
        会自动解析你的注释
        [你实例化的名称].register_tool(tool = )
        Args:
            description (str): 工具的描述
            require_confirmation (bool): 是否需要用户确认
            require_persistence (bool): 是否需要持久化运行
            return_image (bool): 是否返回图片 多模态Agent适用 会自动地把工具的图片提交给模型
            return_audio (bool): 是否返回音频 多模态Agent适用 会自动地把工具的音频提交给模型
            return_url (bool): 是否返回 URL 多模态Agent适用 会自动地把URL提交给模型
        """
        original_name = tool.__name__
        logic_name = (
            f"{self.instance_name}_{original_name}"
            if self.instance_name
            else original_name
        )

        if logic_name in [t.name for t in self._direct_tools]:
            return self.get_tool_info(logic_name)

        # 参数与文档解析
        parameters_sig = inspect.signature(tool).parameters
        required_parameters = [
            p
            for p in parameters_sig
            if parameters_sig[p].default is inspect.Parameter.empty
        ]
        p_doc = parse_docstring(tool.__doc__)

        properties = {}
        from ...utils.type_mapper import TypeMapper

        for p_name, p in parameters_sig.items():
            param_type = (
                p.annotation if p.annotation != inspect.Parameter.empty else str
            )
            json_schema = TypeMapper.map_type(param_type)
            properties[p_name] = {
                "type": json_schema["type"],
                "description": p_doc[0].get(p_name, ""),
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
                    "properties": properties,
                },
            },
        }

        _tool = Tool(
            tool=tool,
            name=logic_name,
            metadata=self.metadata,
            description=description,
            parameters=properties,
            required_parameters=required_parameters,
            require_confirmation=require_confirmation,
            require_persistence=require_persistence,
            return_image=return_image,
            return_audio=return_audio,
            return_url=return_url,
            schema=schema,
            belongs_to=self.instance_name,
        )
        self._direct_tools.append(_tool)
        return schema

    def register_no_function(
        self, name: str, description: str, required_parameters: list, parameters: dict
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
        _logic_name = f"{self.instance_name}_{name}" if self.instance_name else name
        _shcema = {
            "type": "function",
            "function": {
                "name": _logic_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "required": required_parameters,
                    "properties": parameters,
                },
            },
        }
        _tool = Tool(
            tool=None,
            description=description,
            parameters=parameters,
            required_parameters=required_parameters,
            name=_logic_name,
            schema=_shcema,
            belongs_to=self.instance_name,
        )
        self._direct_tools.append(_tool)

    def unregister(self, name: str):
        """
        注销一个工具
        Args:
            name (str): 工具名称
        """
        for i, t in enumerate(self._direct_tools):
            if t.name == name:
                self._direct_tools.pop(i)
                return True
        raise ToolNotFound(name)

    def _get_description(self, tool, description):
        doc_content = tool.__doc__.strip() if tool.__doc__ else ""
        description_part = re.sub(
            r"\s*Args:\s*.*?(?=\n\s*\w+:|$)", "", doc_content, flags=re.DOTALL
        )
        description_part = description_part.strip()
        return description if description is not None else description_part

    def execute(self, _tool_calls, _mcp_client=None, timeout=60, events=None) -> any:
        """
        执行工具 可以直接传递Tool_Calls列表
        Args:
            _tool_calls (list): 工具调用列表
            _mcp_client (MCPClient): MCP客户端
            timeout (int): 超时时间（秒）, 默认60秒
        """
        return self.tools_executor.execute(
            _tool_calls, self, _mcp_client, timeout, events
        )

    async def aexecute(
        self, _tool_calls, _mcp_client=None, timeout=60, events=None
    ) -> any:
        return await self.tools_executor.aexecute(
            _tool_calls, self, _mcp_client, timeout, events
        )

    def _get_tool_by_name(self, name: str) -> Tool:
        for t in self.tools:
            if t.name == name:
                return t
        raise ToolNotFound(name)

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
        """
        获取所有工具的schema
        """
        return self.tools_schemas

    def __repr__(self):
        name_str = f"'{self.instance_name}'" if self.instance_name else "Unnamed"
        return f"<Tools {name_str}, direct={len(self._direct_tools)}, sub={len(self._sub_bundles)}>"

    def __str__(self):
        header = f"工具集: [{self.instance_name or '未命名'}]"
        metadata = self.metadata if self.metadata else "无"
        line = "=" * 40
        result = f"\n{header}\n{metadata}\n{line}\n"
        all_tools = self.tools
        if not all_tools:
            return result + " (当前工具集为空)\n"
        for tool in all_tools:
            result += f"▶ 名称: {tool.name}\n"
            result += f"   归属: [{tool.belongs_to or '直接注册'}]\n"
            result += f"   描述: {tool.description}\n"
            result += f"   {'-' * 20}\n"
        return result
