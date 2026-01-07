"""
编写者：王出日
日期：2025，5，20
版本 0.4.2
描述：使用httpx库实现的API调用类，包含了API请求、token管理、工具调用等功能

包含：
- BaseAPI: 基础API类，所有使用openai api访问大模型的类都继承自此类
- BaseAPI_multimodal: 多模态API类，继承自BaseAPI，增加了图片参数
"""
import base64
import httpx
import json
import os
from typing import AsyncGenerator, Union, Generator
from ..utils.envReader import EnvReader
from ..core.error import APIRequestFailed
from ..utils.output_parser import stream_generator_parser
from ..utils.multimodal_formatter import build_multimodal_message
from ..core import logger
from ..utils.timer import timer, stream_timer, async_stream_timer



class BaseAPI():
    """
    Base API类，所有使用api访问大模型的类都继承自此类
    使用OpenAI格式的API请求，并提供token管理和工具调用功能
    优化了API调用方式，支持流式响应，并提供JSON格式模板
    
    """
    API_ENV_VAR_NAME = "LLM_API_KEY"  # 默认的API key环境变量名称
    BASE_URL = ""  # 默认的base_url

    def __init__(self, 
                model: str=None,
                api_key: str = None,
                base_url: str = None,
                env_path:str = os.path.join(os.getcwd(), "tina.env"),
                name: str = None,
                role: str = "user"
                ):
        self.logger = logger
        self.env_reader = EnvReader(env_file=env_path)
        try:
            self.api_key = self.env_reader.getAPIKey() if api_key is None else api_key
            self.base_url = self.env_reader.getBaseUrl() if base_url is None else base_url
            self.model = self.env_reader.getModel() if model is None else model
        except KeyError:
            logger.error("BaseAPI - env内参数名称错误：请检查")
            raise ValueError("env内参数名称错误：请检查")

        if not self.api_key:
            self.logger.warning(f"BaseAPI - 未找到API key，请检查环境变量'{self.API_ENV_VAR_NAME}'和{env_path}")
            raise ValueError(f"API key并没有在环境变量'{self.API_ENV_VAR_NAME}'和{env_path}中找到，要么请你设置一下，要么输入api_key参数")
        if not self.base_url:
            self.logger.warning(f"BaseAPI - 未找到Base_url，请检查环境变量'BASE_URL'和{os.path.join(env_path, '.env')}")
            raise ValueError(f"Base_url并没有在环境变量'BASE_URL'和{os.path.join(env_path, '.env')}中找到，要么请你设置一下，要么输入base_url参数")
        if not self.model:
            self.logger.warning(f"BaseAPI - 未找到模型名称，请检查环境变量'MODEL_NAME'和{os.path.join(env_path, '.env')}")
            raise ValueError(f"模型名称并没有在环境变量'MODEL_NAME'和{os.path.join(env_path, '.env')}中找到，要么请你设置一下，要么输入model参数")
        
        self.MAX_INPUT = self.env_reader.getMaxInput() if not self.env_reader.getMaxInput() is None else 8000


        self.temperature = self.env_reader.getTemperature() if not self.env_reader.getTemperature() is None else 1.0
        self.logger.info(f"BaseAPI - 当前模型名称为：{self.model}，当前模型支持的最大输入长度为：{self.MAX_INPUT}，当前模型温度为：{self.temperature}")
        self.logger.debug(f"BaseAPI - BaseAPI初始化完成，base_url: {self.base_url}, model: {self.model}")

        self.tokens = 0
        self.token_list=[]

        self._name = name
        self._role = role

    @timer   
    def get_models(self) -> list:
        """返回支持的模型列表"""
        response = httpx.get(f"{self.base_url.rstrip('/chat/completions')}/models", headers=self._prepare_headers())
        if response.status_code != 200:
            rep = response.read()
            self.logger.error(f"BaseAPI.get_models - 请求失败了，状态码：{response.status_code}，错误信息：{json.loads(rep.decode('utf-8'))['error']['message']}")
            raise APIRequestFailed(
                url=f"{self.base_url.rstrip('/chat/completions')}/models",
                status_code=response.status_code,
                error_details=json.loads(rep.decode('utf-8'))["error"]["message"]
            )
        models = response.json().get("data", [])
        return {
            "current_model": self.model,
            "available_models": [model["id"] for model in models]
        }
        
    def get_tokens(self) -> int:
        """返回消耗的token数量"""
        return self.tokens

    def _prepare_messages(self, input_text: str = None,role:str="user", sys_prompt: str = '你的工作非常的出色！', messages: list = None) -> list:
        """准备消息列表的通用方法"""
        if messages is None:
            messages = []
            messages.append({"role": "system", "content": sys_prompt})
            # 处理消息列表
        if input_text:
            messages.append({"role": role, "content": input_text})
        return messages

    def _prepare_payload(self, messages: list, temperature: float, top_p: float, stream: bool, 
                        format: str = "text", json_format: str = '{}', tools: list = None, 
                        top_k: int = None, min_p: float = None, max_tokens: int = None,
                        presence_penalty: float = None, frequency_penalty: float = None,
                        **kwargs) -> dict:
        """准备请求负载的通用方法，智能过滤不支持的参数"""
        temperature = self.temperature if temperature is None else temperature
        
        # 请求参数
        format_dict = {
            'text': 'text',
            'json': 'json_object'
        }
        format = format_dict[format]
        
        # 基础参数（所有模型都支持）
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        
        # 可选参数（只有非None时才添加，保证兼容性）
        optional_params = {
            "top_k": top_k,
            "min_p": min_p,
            "max_tokens": max_tokens,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty
        }
        
        # 智能过滤：只添加非None的参数
        for param_name, param_value in optional_params.items():
            if param_value is not None:
                payload[param_name] = param_value
        
        if tools:
            payload["tools"] = tools
        
        # 扩展参数仍然支持
        payload.update(kwargs)
        return payload

    def _prepare_headers(self) -> dict:
        """准备请求头的通用方法"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    @timer
    def predict_no_stream(self,
                       input_text: str = None,
                       sys_prompt: str = '你的工作非常的出色！',
                       role: str = 'user',
                       messages: list = None,
                       temperature: float = 1.0,
                       top_p: float = 0.9,
                       top_k: int = None,
                       min_p: float = None,
                       max_tokens: int = None,
                       presence_penalty: float = None,
                       frequency_penalty: float = None,
                       format: str = "text",
                       json_format: str = '{}',
                       tools: list = None,
                       timeout: int = 180,
                       **kwargs) -> dict:
        """
        非流式API调用，直接返回完整响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        messages = self._prepare_messages(input_text, role,sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, False, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()

        
        response = httpx.post(f"{self.base_url}", json=payload, headers=headers, timeout=timeout)
        if response.status_code != 200:
            rep = response.read()
            raise APIRequestFailed(
                url=self.base_url,
                status_code=response.status_code,
                error_details=json.loads(rep.decode('utf-8'))["error"]["message"]
            )
        
        response_data = response.json()
        self.tokens += response_data.get("usage", {}).get("total_tokens", 0)
        
        result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}
        
        # 如果包含工具调用，添加 tool_calls
        if "tool_calls" in response_data["choices"][0]["message"]:
            tool_calls = response_data["choices"][0]["message"].get("tool_calls",[])

            # 修改为需要的格式，开发者可以**直接**将这个工具使用追加到消息列表
            if tool_calls:
                result["tool_calls"] = tool_calls
        
        return result


    
    @stream_timer
    def predict_stream(self,
                     input_text: str = None,
                     role: str = 'user',
                     sys_prompt: str = '你的工作非常的出色！',
                     messages: list = None,
                     temperature: float = 1.0,
                     top_p: float = 0.9,
                     top_k: int = None,
                     min_p: float = None,
                     max_tokens: int = None,
                     presence_penalty: float = None,
                     frequency_penalty: float = None,
                     format: str = "text",
                     json_format: str = '{}',
                     tools: list = None,
                     timeout: int = 180,
                     **kwargs) -> Generator[dict, None, None]:
        """
        流式API调用，返回生成器逐块返回响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        messages = self._prepare_messages(input_text, role,sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, True, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()

        return stream_generator_parser(self.base_url, payload, headers, timeout)
    
    def predict(self,
                input_text: str = None,
                role: str = "user",
                sys_prompt: str = '你的工作非常的出色！',
                messages: list = None,
                temperature: float = 1.0,
                top_p: float = 0.9,
                top_k: int = None,
                min_p: float = None,
                max_tokens: int = None,
                presence_penalty: float = None,
                frequency_penalty: float = None,
                stream: bool = False,
                format:str = "text",
                json_format:str = '{}',
                tools: list = None,
                timeout: int = 180,
                **kwargs) -> Union[dict, Generator[dict, None, None]]:
        """
        调用大语言模型执行预测任务，支持单次对话和多轮对话模式
        
        此方法作为统一入口，根据stream参数自动调用对应的专用方法：
        - stream=False: 调用 predictNoStream()
        - stream=True: 调用 predictStream()

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 格式为:
                [{"role": "system", "content": "..."}, 
                {"role": "user", "content": "..."}, 
                {"role": "assistant", "content": "..."}]. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 格式为:
                [{"name": "...", "description": "...", "parameters": {...}}]. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常

        Examples:
            ### 单次对话模式
            >>> predict(input_text="你好")
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}

            ### 多轮对话模式
            >>> messages = [{"role": "user", "content": "北京天气如何？"}]
            >>> predict(messages=messages, tools=[weather_tool])
            {"role": "assistant", "content": "", "tool_calls": [{"name": "get_weather", "arguments": {"location": "北京"}}]}
            
            ### 流式响应
            >>> for chunk in predict(input_text="讲个故事", stream=True):
            ...     print(chunk)
            
            ### 使用高级采样参数
            >>> result = predict(input_text="创意写作", top_k=50, min_p=0.1, max_tokens=1000)
        """
        if stream:
            return self.predict_stream(
                input_text=input_text,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
        else:
            return self.predict_no_stream(
                input_text=input_text,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )

    async def apredict(self,
                      input_text: str = None,
                      role: str = "user",
                      sys_prompt: str = '你的工作非常的出色！',
                      messages: list = None,
                      temperature: float = 1.0,
                      top_p: float = 0.9,
                      top_k: int = None,
                      min_p: float = None,
                      max_tokens: int = None,
                      presence_penalty: float = None,
                      frequency_penalty: float = None,
                      stream: bool = False,
                      format: str = "text",
                      json_format: str = '{}',
                      tools: list = None,
                      timeout: int = 180,
                      **kwargs) -> Union[dict, Generator[dict, None, None]]:
        """
        异步调用大语言模型执行预测任务，支持单次对话和多轮对话模式
        
        此方法作为异步入口，根据stream参数自动调用对应的专用方法：
        - stream=False: 调用 predictNoStream()
        - stream=True: 调用 predictStream()

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 格式为:
                [{"role": "system", "content": "..."}, 
                {"role": "user", "content": "..."}, 
                {"role": "assistant", "content": "..."}]. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 格式为:
                [{"name": "...", "description": "...", "parameters": {...}}]. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常

        Examples:
            ### 单次对话模式
            >>> result = await llm.apredict(input_text="你好")
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}

            ### 多轮对话模式
            >>> messages = [{"role": "user", "content": "北京天气如何？"}]
            >>> result = await llm.apredict(messages=messages, tools=[weather_tool])
            {"role": "assistant", "content": "", "tool_calls": [{"name": "get_weather", "arguments": {"location": "北京"}}]}
            
            ### 流式响应
            >>> async for chunk in llm.apredict(input_text="讲个故事", stream=True):
            ...     print(chunk)
            
            ### 使用高级采样参数
            >>> result = await llm.apredict(input_text="创意写作", top_k=50, min_p=0.1, max_tokens=1000)
        """
        if stream:
            return await self.apredict_stream(
                input_text=input_text,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
        else:
            # 异步非流式调用
            return await self.apredict_no_stream(
                input_text=input_text,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
        
    @async_stream_timer
    async def apredict_stream(self,
                                 input_text: str = None,
                                 role: str = "user",
                                 sys_prompt: str = '你的工作非常的出色！',
                                 messages: list = None,
                                 temperature: float = 1.0,
                                 top_p: float = 0.9,
                                 top_k: int = None,
                                 min_p: float = None,
                                 max_tokens: int = None,
                                 presence_penalty: float = None,
                                 frequency_penalty: float = None,
                                 format: str = "text",
                                 json_format: str = '{}',
                                 tools: list = None,
                                 timeout: int = 180,
                                 **kwargs) -> AsyncGenerator[dict, None]:
            
            messages = self._prepare_messages(input_text, role, sys_prompt, messages)
            payload = self._prepare_payload(
                messages, temperature, top_p, True, format, json_format, tools,
                top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
            )
            headers = self._prepare_headers()
            
            # 使用异步流式解析器
            from ..utils.output_parser import astream_generator_parser
            return astream_generator_parser(self.base_url, payload, headers, timeout)
    @timer
    async def apredict_no_stream(self,
                                 input_text: str = None,
                                 role: str = "user",
                                 sys_prompt: str = '你的工作非常的出色！',
                                 messages: list = None,
                                 temperature: float = 1.0,
                                 top_p: float = 0.9,
                                 top_k: int = None,
                                 min_p: float = None,
                                 max_tokens: int = None,
                                 presence_penalty: float = None,
                                 frequency_penalty: float = None,
                                 format: str = "text",
                                 json_format: str = '{}',
                                 tools: list = None,
                                 timeout: int = 180,
                                 **kwargs) -> dict:
        """
        异步非流式API调用，直接返回完整响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        import httpx
        from ..core.error import APIRequestFailed
        
        messages = self._prepare_messages(input_text, role, sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, False, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}", json=payload, headers=headers, timeout=timeout)
            if response.status_code != 200:
                rep = response.read()
                raise APIRequestFailed(
                    url=self.base_url,
                    status_code=response.status_code,
                    error_details=json.loads(rep.decode('utf-8'))["error"]["message"]
                )

            response_data = response.json()
            self.tokens += response_data.get("usage", {}).get("total_tokens", 0)

            result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}

            # 如果包含工具调用，添加 tool_calls
            if "tool_calls" in response_data["choices"][0]["message"]:
                tool_calls = response_data["choices"][0]["message"].get("tool_calls", [])
                # 修改为需要的格式，开发者可以**直接**将这个工具使用追加到消息列表
                if tool_calls:
                    result["tool_calls"] = tool_calls

            return result

class BaseMultimodalAPI(BaseAPI):
    """
    多模态API类，继承自BaseAPI
    扩展了对多图片（本地/URL）和多音频（本地）的支持
    """
    API_ENV_VAR_NAME = "LLM_API_KEY"
    BASE_URL = ""

    def __init__(self, model: str = None, api_key: str = None, base_url: str = None, env_path: str = None,name:str="None",role:str="user"):
        super().__init__(model=model, api_key=api_key, base_url=base_url, env_path=env_path,name=name,role=role)

   
    def _prepare_multimodal_messages(self,
                                     input_text: str = None, 
                                     input_image: Union[str, list[str]] = None, 
                                     input_audio: Union[str, list[str]] = None,
                                     input_url: Union[str, list[str]] = None,
                                     role: str = "user",
                                     sys_prompt: str = '你的工作非常出色！', 
                                     messages: list = None) -> list:
        """准备多模态消息列表，支持单/多文本、图片、音频"""
        if messages is None:
            messages = [{"role": "system", "content": sys_prompt}]
    
        user_message = build_multimodal_message(input_text, input_image, input_audio, input_url, role)
        messages.append(user_message)
        return messages


    # ========================== 同步接口 ==========================
    def predict(self,
                input_text: str = None,
                input_image: Union[str, list[str]] = None,
                input_audio: Union[str, list[str]] = None,
                input_url: Union[str, list[str]] = None,
                stream: bool = False,
                role: str = "user",
                sys_prompt: str = '你的工作非常出色！',
                messages: list = None,
                temperature: float = 1.0,
                top_p: float = 0.9,
                top_k: int = None,
                min_p: float = None,
                max_tokens: int = None,
                presence_penalty: float = None,
                frequency_penalty: float = None,
                format: str = "text",
                json_format: str = '{}',
                tools: list = None,
                timeout: int = 180,
                **kwargs
    ):
        """
        多模态预测接口，支持文本、图片、音频和URL输入
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息
        """
        if stream:
            return self.predict_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
        else:
            return self.predict_no_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
    
    def predict_no_stream(self,
                          input_text: str = None,
                          input_image: Union[str, list[str]] = None,
                          input_audio: Union[str, list[str]] = None,
                          input_url: Union[str, list[str]] = None,
                          role: str = "user",
                          sys_prompt: str = '你的工作非常出色！',
                          messages: list = None,
                          temperature: float = 1.0,
                          top_p: float = 0.9,
                          top_k: int = None,
                          min_p: float = None,
                          max_tokens: int = None,
                          presence_penalty: float = None,
                          frequency_penalty: float = None,
                          format: str = "text",
                          json_format: str = '{}',
                          tools: list = None,
                          timeout: int = 180,
                          **kwargs) -> dict:
        """
        同步非流式多模态API调用，直接返回完整响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text, input_image, input_audio, input_url, role, sys_prompt, messages
        )
        payload = self._prepare_payload(
            messages=prepared_messages, 
            temperature=temperature, 
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=False, 
            format=format,
            json_format=json_format,
            tools=tools, 
            **kwargs
        )
        
        response = httpx.post(self.base_url, json=payload, headers=self._prepare_headers(), timeout=timeout)
        if response.status_code != 200:
            raise APIRequestFailed(self.base_url, response.status_code, response.text)
        
        res_json = response.json()
        self.tokens += res_json.get("usage", {}).get("total_tokens", 0)
        
        msg = res_json["choices"][0]["message"]
        result = {"role": "assistant", "content": msg.get("content", "")}
        if "tool_calls" in msg:
            result["tool_calls"] = msg["tool_calls"]
        return result

    def predict_stream(self,
                       input_text: str = None,
                       input_image: Union[str, list[str]] = None,
                       input_audio: Union[str, list[str]] = None,
                       input_url: Union[str, list[str]] = None,
                       role: str = "user",
                       sys_prompt: str = '你的工作非常出色！',
                       messages: list = None,
                       temperature: float = 1.0,
                       top_p: float = 0.9,
                       top_k: int = None,
                       min_p: float = None,
                       max_tokens: int = None,
                       presence_penalty: float = None,
                       frequency_penalty: float = None,
                       format: str = "text",
                       json_format: str = '{}',
                       tools: list = None,
                       timeout: int = 180,
                       **kwargs) -> Generator[dict, None, None]:
        """
        同步流式多模态API调用，返回生成器逐块返回响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text, input_image, input_audio, input_url, role, sys_prompt, messages
        )
        payload = self._prepare_payload(
            messages=prepared_messages, 
            temperature=temperature, 
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=True, 
            format=format,
            json_format=json_format,
            tools=tools, 
            **kwargs
        )
        return stream_generator_parser(self.base_url, payload, self._prepare_headers(), timeout)

    # ========================== 异步接口 ==========================
    async def apredict(self,
                       input_text: str = None,
                       input_image: Union[str, list[str]] = None,
                       input_audio: Union[str, list[str]] = None,
                       input_url: Union[str, list[str]] = None,
                       stream: bool = False,
                       role: str = "user",
                       sys_prompt: str = '你的工作非常出色！',
                       messages: list = None,
                       temperature: float = 1.0,
                       top_p: float = 0.9,
                       top_k: int = None,
                       min_p: float = None,
                       max_tokens: int = None,
                       presence_penalty: float = None,
                       frequency_penalty: float = None,
                       format: str = "text",
                       json_format: str = '{}',
                       tools: list = None,
                       timeout: int = 180,
                       **kwargs):
        """
        异步多模态预测接口，支持文本、图片、音频和URL输入
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息
        """
        if stream:
            return await self.apredict_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
        else:
            return await self.apredict_no_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs
            )
    
    async def apredict_no_stream(self,
                                 input_text: str = None,
                                 input_image: Union[str, list[str]] = None,
                                 input_audio: Union[str, list[str]] = None,
                                 input_url: Union[str, list[str]] = None,
                                 role: str = "user",
                                 sys_prompt: str = '你的工作非常出色！',
                                 messages: list = None,
                                 temperature: float = 1.0,
                                 top_p: float = 0.9,
                                 top_k: int = None,
                                 min_p: float = None,
                                 max_tokens: int = None,
                                 presence_penalty: float = None,
                                 frequency_penalty: float = None,
                                 format: str = "text",
                                 json_format: str = '{}',
                                 tools: list = None,
                                 timeout: int = 180,
                                 **kwargs) -> dict:
        """
        异步非流式多模态API调用，直接返回完整响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text, input_image, input_audio, input_url, role, sys_prompt, messages
        )
        payload = self._prepare_payload(
            messages=prepared_messages, 
            temperature=temperature, 
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=False, 
            format=format,
            json_format=json_format,
            tools=tools, 
            **kwargs
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.base_url, json=payload, headers=self._prepare_headers(), timeout=timeout)
            if response.status_code != 200:
                raise APIRequestFailed(self.base_url, response.status_code, response.text)
            
            res_json = response.json()
            self.tokens += res_json.get("usage", {}).get("total_tokens", 0)
            
            msg = res_json["choices"][0]["message"]
            result = {"role": "assistant", "content": msg.get("content", "")}
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]
            return result

    async def apredict_stream(self,
                              input_text: str = None,
                              input_image: Union[str, list[str]] = None,
                              input_audio: Union[str, list[str]] = None,
                              input_url: Union[str, list[str]] = None,
                              role: str = "user",
                              sys_prompt: str = '你的工作非常出色！',
                              messages: list = None,
                              temperature: float = 1.0,
                              top_p: float = 0.9,
                              top_k: int = None,
                              min_p: float = None,
                              max_tokens: int = None,
                              presence_penalty: float = None,
                              frequency_penalty: float = None,
                              format: str = "text",
                              json_format: str = '{}',
                              tools: list = None,
                              timeout: int = 180,
                              **kwargs) -> AsyncGenerator[dict, None]:
        """
        异步流式多模态API调用，返回生成器逐块返回响应
        
        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值. 
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        from ..utils.output_parser import astream_generator_parser
        prepared_messages = self._prepare_multimodal_messages(
            input_text, input_image, input_audio, input_url, role, sys_prompt, messages
        )
        payload = self._prepare_payload(
            messages=prepared_messages, 
            temperature=temperature, 
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=True, 
            format=format,
            json_format=json_format,
            tools=tools, 
            **kwargs
        )
        return astream_generator_parser(self.base_url, payload, self._prepare_headers(), timeout)