import json
from ...llm.BaseAPI import BaseAPI
from ...mcp import MCPClient
from .tools import Tools
from .context_manager import ContextManager
from typing import Generator

class BaseAgentRuntime():
    """
    Agent运行时环境，包含LLM、工具、系统提示等信息
    """
    llm: BaseAPI
    tools: Tools
    context_manager: ContextManager
    mcp_client: MCPClient

    
    def __init__(self, llm, tools, context_manager, mcp_client=None):
        self.llm = llm
        self.tools = tools
        self.context_manager = context_manager
        self.mcp_client = mcp_client

    def run_prediction_no_stream(self, instruction: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                ):
        """
        非流式的预测
        """
        self._instruction(instruction)

    def run_prediction_stream(self, instruction: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                ):
        """
        流式的预测
        """
        self._instruction(instruction)

    async def arun_prediction_no_stream(self, instruction: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                ):
        self._instruction(instruction)

    async def arun_prediction_stream(self, instruction: str = None,
                temperature: float = 0.5,
                top_p: float = 0.9,
                top_k: int = 1,
                min_p: float = 0.0,
                ):
        self._instruction(instruction)

    def _instruction(self, instruction):
        if instruction is not None:
            self.context_manager.add_user_message(instruction)
    def _execute_tool(self, _tool_calls)-> str:
        """执行工具调用并返回结果"""
        

         # 默认工具执行方式
        tool_result = self.tools.execute(_tool_calls,self.tools,self.mcp_client)
        self.context_manager.add_tool_calls_result(tool_result)
            
        return tool_result
    
    async def _aexecute_tool(self, _tool_calls) -> str:
        """异步执行工具调用并返回结果"""
        tool_result = await self.tools.aexecute(_tool_calls, self.tools,self.mcp_client)
        self.context_manager.add_tool_calls_result(tool_result)
        return tool_result
    
class ToolCallingAgentRuntime(BaseAgentRuntime):
    def __init__(self, 
                 llm: BaseAPI, 
                 tools: Tools, 
                 context_manager: ContextManager, 
                 max_tool_loop:int=30,
                 mcp_client: MCPClient = None):
        super().__init__(llm, tools, context_manager,mcp_client)
        self.max_tool_loop = max_tool_loop

       
    def run_prediction_no_stream(self, 
                                 instruction: str = None,
                                 temperature: float = 0.5,
                                 top_p: float = 0.9,
                                 top_k: int = 1,
                                 min_p: float = 0.0,
                                ) -> dict:
        super().run_prediction_no_stream(instruction,temperature,top_p,top_k,min_p)
        counter = 0
        while counter < self.max_tool_loop:  
            llm_result = self.llm.predict_no_stream(
                    messages=self.context_manager.get_messages(),
                    temperature=temperature,
                    tools=self.tools.get_tools_for_llm(),
                    top_p=top_p,
                )
            if "tool_calls" in llm_result:
                _tool_calls = llm_result["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                self._execute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.context_manager.add_assistant_message(llm_result["content"])
                return llm_result 
        if counter > self.max_tool_loop:  
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")
        

    def run_prediction_stream(self,
                                instruction = None,
                                temperature = 0.5,
                                top_p = 0.9, 
                                top_k = 1, 
                                min_p = 0) -> Generator[dict,None,None]:
        super().run_prediction_stream(instruction, temperature, top_p, top_k, min_p)
        counter = 0
        while counter < self.max_tool_loop:
            tool_called = False
            llm_response = self.llm.predict_stream(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p
            )
            content_parts:list = []
            reasoning_buffer:str =""
        
            for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    yield chunk

                elif "tool_calls" in chunk and chunk["id"] != '':
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []  
                    reasoning_buffer = "" 

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])
    
                    
                    results = self._execute_tool(chunk["tool_calls"])
                    for result in results:
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break
                
                elif "reasoning_content" in chunk:
                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}                
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        yield {"role": "assistant", "content": content}    

            whole_content = "".join(content_parts)
            if whole_content:
                self.context_manager.add_assistant_message(whole_content)

            if tool_called:
                continue
            break
            

        if counter > self.max_tool_loop:
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")
        

    async def arun_prediction_no_stream(self, 
                                        instruction = None, 
                                        temperature = 0.5, 
                                        top_p = 0.9, 
                                        top_k = 1, 
                                        min_p = 0):
        await super().arun_prediction_no_stream(instruction, temperature, top_p, top_k, min_p)
        counter = 0
        while counter < self.max_tool_loop:  
            llm_result = await self.llm.apredict(
                    messages=self.context_manager.get_messages(),
                    temperature=temperature,
                    tools=self.tools.get_tools_for_llm(),
                    top_p=top_p,
                )
            if "tool_calls" in llm_result:
                _tool_calls = llm_result["tool_calls"]
                self.context_manager.add_tool_calls(_tool_calls)
                self._execute_tool(_tool_calls)

                counter += 1

                continue
            else:
                self.context_manager.add_assistant_message(llm_result["content"])
                return llm_result 
        if counter > self.max_tool_loop:  
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")
    

    async def arun_prediction_stream(self, 
                                     instruction = None, 
                                     temperature = 0.5, 
                                     top_p = 0.9, 
                                     top_k = 1, 
                                     min_p = 0):
        await super().arun_prediction_stream(instruction, temperature, top_p, top_k, min_p)
        counter = 0
        while counter < self.max_tool_loop:
            tool_called = False
            llm_response = await self.llm.apredict(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                stream=True
            )
            content_parts:list = []
            reasoning_buffer:str =""
        
            async for chunk in llm_response:
                if chunk.get("content") is None:
                    chunk["content"] = ""

                if "tool_name" in chunk or "tool_arguments" in chunk:
                    yield chunk

                elif "tool_calls" in chunk and chunk["id"] != '':
                    whole_content = "".join(content_parts)

                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)

                    content_parts = []  
                    reasoning_buffer = "" 

                    self.context_manager.add_tool_calls(tool_calls=chunk["tool_calls"])
    
                    
                    results = await self._aexecute_tool(chunk["tool_calls"])
                    for result in results:
                        yield result

                    counter += 1
                    tool_called = True
                    # 进入下一轮循环
                    break
                
                elif "reasoning_content" in chunk:
                    reasoning_content = chunk.get("reasoning_content", "")
                    if reasoning_content:
                        reasoning_buffer += reasoning_content
                        yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}                
                else:
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        yield {"role": "assistant", "content": content}    

            whole_content = "".join(content_parts)
            if whole_content:
                self.context_manager.add_assistant_message(whole_content)

            if tool_called:
                continue
            break
            

        if counter > self.max_tool_loop:
            raise RuntimeError(f"超过了最大工具循环次数{self.max_tool_loop}")