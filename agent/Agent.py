"""
编写者：王出日
日期：2024，12，1
版本 0.5.0
功能：Agent类，实现了智能体的功能。
包含：
Agent类：基础智能体类，默认支持API调用
AgentByLocalModel类：本地模型智能体类，继承自Agent
"""
from __future__ import annotations

from typing import List, Union, Generator, Iterator, Dict, Any, AsyncGenerator

from ..llm.BaseAPI import BaseAPI
from .core.tools import Tools
from ..mcp.Client import MCPClient
from .core.prompt import Prompt
from .core.context_manager import ContextManager
from .core.agent_runtime import ToolCallingAgentRuntime,BaseAgentRuntime
from .core.events import Events
from ..core.error import TinaError
from .core.parser import local_model_llama_cpp_parser 




class Agent:
    """
    基础智能体类，默认支持API调用方式
    默认实现了ToolCallingAgent
    """
    llm: BaseAPI
    tools: Tools  
    def __init__(self,
                  llm: BaseAPI, 
                  tools: Tools, 
                  system_prompt: str = None, 
                  execute_tool: bool = True, 
                  mcp: MCPClient = None,
                  context_manager:ContextManager=None,
                  agent_runtime: BaseAgentRuntime = None,
                  max_tool_loop:int = 30,
                  name:str="None"):
        """
        实例化一个Agent对象
        
        Args:
            LLM: tina.BaseAPI类型，调用的LLM对象
            tools: tina.Tools类型，工具集
            sys_prompt: str 系统提示词
            isExecute: bool 是否执行工具，默认为True，关闭后智能体不在执行工具并返回结果和大模型回复。
            MCP: tina.MCPClient类型，MCP客户端对象，如果不传入，则不进行MCP调用。
            context_length: int 最大上下文长度，超过该长度则删除旧消息，保留最近的消息。
            context_limit: int 上下文限制，使用大模型来总结你的上下文，数字为0时不触发
            max_tool_loop: int 最大工具调用次数，超过该次数则停止调用工具
            name: str 智能体名字，用于多Agent区分
        """
        # 智能体的名称
        self.name =name

        # 运行需要的实例
        self.llm = llm
        self.tools = tools
        self.tools_call_result = []
        self.tools_call = []
        self.is_execute = execute_tool
        self.mcp_client = mcp
        if context_manager is None:
            self.context_manager = ContextManager()
        else:
            self.context_manager = context_manager
        # 初始化MCP
        self._mcp_to_tools(mcp)
        self.events = Events()
        if system_prompt is not None:
            self.context_manager.set_system_message(system_prompt)
        else:
            self.context_manager.set_system_message(Prompt("tina").prompt)
        # 初始化消息，可以直接使用context_manager来修改messages
        self.messages = self.context_manager.get_messages()

        if agent_runtime is None:
            self.runtime = ToolCallingAgentRuntime(self.llm, self.tools, self.context_manager,self.events,max_tool_loop=max_tool_loop,mcp_client=mcp)
        else:
            self.runtime = agent_runtime
        
    # 事件管理（对外公开 Events 的装饰器接口）
    def before_tool_call(self):
        """
        在执行工具调用之 前  
        需要事件处理函数接受下面的参数：  
        tool_name: str,tool_arguments: dict,
        """
        return self.events.before_tool_call()

    def after_tool_call(self):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：  
        tool_name: str,tool_arguments: dict,tool_result: any
        """
        return self.events.after_tool_call()

    def before_tool_calls(self):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：  
        tool_calls: list[dict[str,str]]
        """
        return self.events.before_tool_calls()

    def after_tool_calls(self):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：  
        tool_calls: list[dict[str,str]]
        """
        return self.events.after_tool_calls()

    def before_user_instruction(self):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：  
        user_message: str
        """
        return self.events.before_user_instruction()

    def after_user_instruction(self):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：  
        user_message: str assistant_message: str
        """
        return self.events.after_user_instruction()

    def on_tool_confirmation(self):
        """
        如果一个工具被登记为需要验证才可以运行，请监听此事件  
        需要事件处理函数接受下面的参数：  
        tool_name: str tool_arguments: dict
        """
        return self.events.on_tool_confirmation()

    def _mcp_to_tools(self, MCP):
        """如果传入了MCP，则将MCP的工具集加入到当前的工具集中"""
        try:
            if MCP is not None:
                self.mcp_client = MCP
                _tools = self.mcp_client.to_tina_tools()
                self.tools = _tools + self.tools
                del _tools
        except Exception as e:
            raise e

    def disable_tool(self, tool_name: str) -> bool:
        """
        禁用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.disable_tool(tool_name)
    
    def enable_tool(self, tool_name: str) -> bool:
        """
        启用工具
        Args:
            tool_name:工具名称
        """
        return self.tools.enable_tool(tool_name)
    
    def get_messages(self) -> list:
        """
        获取当前Agent的消息列表
        Agent会在当前运行状态维护一个自己的消息列表，可以通过该方法获取
        """
        return self.messages
    def clear_messages(self) -> None:
        """
        清理当前Agent的消息列表，只保留前三个系统消息
        """
        self.context_manager.clear_messages()
    
    def get_tools(self) -> list:
        """
        获取当前Agent的工具列表
        """
        return self.tools.get_tools()
    
    def get_system_prompt(self) -> str:
        """
        获取当前Agent的提示词
        """
        return self.context_manager.get_system_message()
    
    def add_message(self, role: str = None, content: str = None) -> None:
        """
        添加消息
        """
        if role is None or content is None:
            raise TinaError("role和content参数不能为空")
        if role == "user":
            self.context_manager.add_user_message(content)
            return
        elif role == "assistant":
            self.context_manager.add_assistant_message(content)
            return
        
    def add_messages(self,messages: list[dict[str,str]] = None) -> None:
        """
        在当前的Agent添加新的消息
        Args:
            role:消息的角色，可以是"user"，"assistant"，"system"
            content:消息的内容
            messages:消息列表，可以一次性添加多个消息,格式为[{"role": "user", "content": "你好，我是用户"}]，注意如果传入了messages，则role和content参数将被忽略
        """
        self.messages = self.context_manager.add_messages(messages)


    def get_tools_call_result(self) -> list:
        """
        获取当前Agent的工具调用结果列表
        """
        return self.context_manager.get_tools_result()
    
    def get_tools_call(self) -> list:
        return self.context_manager.get_tool_calls()
    
    def add_mcp_server(self, server_id: str, config: Dict[str, Any], max_retries=3, timeout=90) -> bool:
        """
        添加MCP服务器
        Args:
            server_id:服务器ID
            config:服务器配置
            max_retries:最大重试次数
            timeout:超时时间
        """
        if self.mcp_client is not None:
            return self.mcp_client.add_server(server_id, config, max_retries, timeout)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")
        
    def remove_mcp_server(self, server_id: str) -> bool:
        """
        移除MCP服务器
        Args:
            server_id:服务器ID
        """
        if self.mcp_client is not None:
            return self.mcp_client.remove_server(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")

    def get_mcp_server_info(self, server_id: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        获取MCP服务器信息
        Args:
            server_id:服务器ID，如果不传入，则返回所有服务器信息
        """
        if self.mcp_client is not None:
            return self.mcp_client.get_server_info(server_id)
        else:
            raise ValueError("MCP客户端未初始化，请先初始化MCP客户端")
    
    def predict(self, 
                instruction: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                stream: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        调用agent进行生成文本回复，默认流式输出
        """
        if stream:
            return self.runtime.run_prediction_stream(
                instruction,
                temperature,
                top_p,
                top_k,
                min_p,
            )
        else:
            
            return self.runtime.run_prediction_no_stream(
                instruction,
                temperature,
                top_p,
                top_k,
                min_p,
            )


    async def apredict(
        self,
        instruction: str = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        top_k: int = 1,
        min_p: float = 0.0,
        stream: bool = True,
    ) -> Union[str, AsyncGenerator[Dict[str, Any], None]]:
        """
        异步版本的 predict，默认流式输出
        """
        if stream:
            return self.runtime.arun_prediction_stream(
                instruction,
                temperature,
                top_p,
                top_k,
                min_p,
            )
        else:
            return await self.runtime.arun_prediction_no_stream(
                instruction,
                temperature,
                top_p,
                top_k,
                min_p,
            )