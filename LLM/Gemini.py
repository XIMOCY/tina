"""
Gemini API 实现类
基于BaseAPI，针对Gemini API的特点进行了定制
"""

import os
import json
import httpx
from typing import Union, Generator, List, Dict, Any, Optional
from ..llm.BaseAPI import BaseAPI
from ..utils.envReader import EnvReader
from ..core.error import APIRequestFailed
from ..utils.output_parser import stream_generator_parser


class GeminiAPI(BaseAPI):
    """
    Gemini API 类，继承自 BaseAPI
    专门用于与 Google Gemini API 进行交互
    """
    
    API_ENV_VAR_NAME = "GEMINI_API_KEY"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, 
                model: Optional[str] = None,
                api_key: Optional[str] = None,
                base_url: Optional[str] = None,
                env_path: str = os.path.join(os.getcwd(), "tina.env"),
                name: Optional[str] = None,
                role: str = "user"):
        """
        初始化 Gemini API 客户端
        
        Args:
            model (str, optional): 模型名称，如 "gemini-1.5-pro" 或 "gemini-1.5-flash"
            api_key (str, optional): API 密钥，如果不提供将从环境变量读取
            base_url (str, optional): API 基础 URL，如果不提供将使用默认值
            env_path (str): 环境变量文件路径
            name (str, optional): 模型名称
            role (str): 默认角色
        """
        # 设置默认值
        if base_url is None:
            base_url = self.BASE_URL
            
        super().__init__(model=model or "", api_key=api_key or "", base_url=base_url or "", 
                        env_path=env_path, name=name or "", role=role)
        
        # 覆盖 BaseAPI 的默认值以适应 Gemini API
        if not self.base_url:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            
        # 确保 URL 以 / 结尾，以便正确拼接
        if not self.base_url.endswith('/'):
            self.base_url += '/'
            
        # 检查 API 密钥格式
        if self.api_key and not self.api_key.startswith('AIza'):
            print("警告：Gemini API 密钥通常以 'AIza' 开头，请确认密钥格式正确")

    def _prepare_headers(self) -> dict:
        """
        准备请求头，Gemini 使用 API-Key 而不是 Bearer Token
        """
        return {
            "Content-Type": "application/json"
        }

    def _prepare_payload(self, messages: list, temperature: float, top_p: float, stream: bool,
                        format: str = "text", json_format: str = '{}', tools: Optional[list] = None,
                        top_k: Optional[int] = None, min_p: Optional[float] = None, max_tokens: Optional[int] = None,
                        presence_penalty: Optional[float] = None, frequency_penalty: Optional[float] = None,
                        **kwargs) -> dict:
        """
        准备请求负载，针对 Gemini API 格式进行调整
        """
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
            "max_tokens": max_tokens,
        }

        # 智能过滤：只添加非None的参数
        for param_name, param_value in optional_params.items():
            if param_value is not None:
                payload[param_name] = param_value

        # Gemini 不支持 min_p 和 frequency_penalty
        if min_p is not None:
            print("警告：Gemini API 不支持 min_p 参数")
        if frequency_penalty is not None:
            print("警告：Gemini API 不支持 frequency_penalty 参数")
        if presence_penalty is not None:
            print("警告：Gemini API 不支持 presence_penalty 参数")

        if tools:
            payload["tools"] = tools

        # 扩展参数仍然支持
        payload.update(kwargs)
        return payload

    def _build_api_url(self) -> str:
        """
        构建完整的 API URL，包含 API 密钥
        """
        # 确保 base_url 以 chat/completions 结尾
        base_endpoint = self.base_url.rstrip('/')
        if not base_endpoint.endswith('chat/completions'):
            base_endpoint = f"{base_endpoint}/chat/completions"
            
        return f"{base_endpoint}?key={self.api_key}"

    def predictNoStream(self,
                       input_text: Optional[str] = None,
                       sys_prompt: str = '你的工作非常的出色！',
                       role: str = 'user',
                       messages: Optional[list] = None,
                       temperature: float = 1.0,
                       top_p: float = 0.9,
                       top_k: Optional[int] = None,
                       min_p: Optional[float] = None,
                       max_tokens: Optional[int] = None,
                       presence_penalty: Optional[float] = None,
                       frequency_penalty: Optional[float] = None,
                       format: str = "text",
                       json_format: str = '{}',
                       tools: Optional[list] = None,
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
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        messages = self._prepare_messages(input_text or "", role, sys_prompt, messages or [])
        payload = self._prepare_payload(
            messages, temperature, top_p, False, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()
        api_url = self._build_api_url()

        response = httpx.post(api_url, json=payload, headers=headers, timeout=timeout)
        if response.status_code != 200:
            rep = response.read()
            try:
                error_details = json.loads(rep.decode('utf-8'))
            except json.JSONDecodeError:
                error_details = {"error": {"message": rep.decode('utf-8')}}
            
            raise APIRequestFailed(
                url=api_url,
                status_code=response.status_code,
                error_details=str(error_details)
            )

        response_data = response.json()
        self.token += response_data.get("usage", {}).get("total_tokens", 0)

        result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}

        # 如果包含工具调用，添加 tool_calls
        if "tool_calls" in response_data["choices"][0]["message"]:
            tool_calls = response_data["choices"][0]["message"].get("tool_calls", [])
            # 修改为需要的格式，开发者可以**直接**将这个工具使用追加到消息列表
            tool_calls = {
                "id": tool_calls[0]["id"],
                "function": tool_calls[0]["function"],
            }
            if tool_calls:
                result["tool_calls"] = tool_calls

        return result

    def predictStream(self,
                     input_text: Optional[str] = None,
                     role: str = 'user',
                     sys_prompt: str = '你的工作非常的出色！',
                     messages: Optional[list] = None,
                     temperature: float = 1.0,
                     top_p: float = 0.9,
                     top_k: Optional[int] = None,
                     min_p: Optional[float] = None,
                     max_tokens: Optional[int] = None,
                     presence_penalty: Optional[float] = None,
                     frequency_penalty: Optional[float] = None,
                     format: str = "text",
                     json_format: str = '{}',
                     tools: Optional[list] = None,
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
            top_k (int, optional): Top-K采样参数，限制候选词汇数量. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        messages = self._prepare_messages(input_text or "", role, sys_prompt, messages or [])
        payload = self._prepare_payload(
            messages, temperature, top_p, True, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()
        api_url = self._build_api_url()

        return stream_generator_parser(api_url, payload, headers, timeout)