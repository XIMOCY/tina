"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：Ollama API接口类，支持本地运行的大语言模型

Ollama特点：
- 支持本地运行各种开源模型
- 无需API密钥，完全本地化
- 支持流式和非流式输出
- 模型管理简单便捷
- 支持多种开源模型（Llama, Mistral, CodeLlama等）
"""

from .BaseAPI import BaseAPI
import httpx
import json
from typing import Generator, Union
from ..core.error import APIRequestFailed

class Ollama(BaseAPI):
    """
    Ollama API类，用于调用本地运行的大语言模型
    
    支持的模型（需要先通过ollama pull下载）：
    - llama3.2: Meta最新Llama模型
    - llama3.1: Meta Llama 3.1系列
    - llama3: Meta Llama 3系列
    - llama2: Meta Llama 2系列
    - mistral: Mistral 7B模型
    - mixtral: Mistral 8x7B混合专家模型
    - codellama: Meta代码生成模型
    - phi3: Microsoft Phi-3模型
    - gemma: Google Gemma模型
    - qwen: 阿里通义千问模型
    - deepseek-coder: DeepSeek代码模型
    - codegemma: Google代码生成模型
    
    环境变量配置：
    - OLLAMA_HOST: Ollama服务地址 (默认: http://localhost:11434)
    - OLLAMA_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = None  # Ollama不需要API密钥
    BASE_URL = "http://localhost:11434/api/chat"
    
    def __init__(self, model: str = "llama3.2", base_url: str = None, host: str = None):
        """
        初始化Ollama API客户端
        
        Args:
            model (str, optional): 模型名称. 默认 "llama3.2"
            base_url (str, optional): API基础URL. 默认 "http://localhost:11434/api/chat"
            host (str, optional): Ollama服务主机地址. 默认 "http://localhost:11434"
        """
        # Ollama不需要API密钥，设置一个虚拟值避免父类报错
        self.api_key = "ollama-local"
        self.model = model
        
        # 处理host和base_url
        if host:
            self.base_url = f"{host}/api/chat"
        elif base_url:
            self.base_url = base_url
        else:
            self.base_url = self.BASE_URL
            
        # 设置环境读取器的必要属性
        from ..utils.envReader import EnvReader
        import os
        self.env_reader = EnvReader(env_file=os.path.join(os.getcwd(), ".env"))
        
        # 尝试从环境变量获取配置
        try:
            if not model:
                self.model = self.env_reader.getEnvValue("OLLAMA_MODEL") or "llama3.2"
            if not host and not base_url:
                ollama_host = self.env_reader.getEnvValue("OLLAMA_HOST")
                if ollama_host:
                    self.base_url = f"{ollama_host}/api/chat"
        except:
            pass
            
        self.MAX_INPUT = 8000
        self.temperature = 1.0
        self.token = 0
        self.token_list = []
        self._call = "Ollama"
        
    def _prepare_headers(self) -> dict:
        """准备Ollama请求头"""
        return {
            "Content-Type": "application/json"
        }
        
    def _prepare_ollama_messages(self, input_text: str = None, sys_prompt: str = '你的工作非常的出色！', 
                                messages: list = None) -> list:
        """
        准备Ollama格式的消息
        
        Ollama的消息格式与OpenAI基本相同，但有一些细微差别
        """
        if messages is None:
            messages = []
            if sys_prompt:
                messages.append({"role": "system", "content": sys_prompt})
            if input_text:
                messages.append({"role": "user", "content": input_text})
        return messages
        
    def _convert_tools_to_ollama_format(self, tools: list) -> list:
        """
        将工具格式转换为Ollama格式
        
        注意：Ollama的工具调用支持可能有限，这里提供基础转换
        """
        if not tools:
            return None
            
        ollama_tools = []
        for tool in tools:
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": tool["function"]["name"],
                    "description": tool["function"]["description"],
                    "parameters": tool.get("function", {}).get("parameters", {})
                }
            }
            ollama_tools.append(ollama_tool)
        return ollama_tools
        
    def predictNoStream(self,
                       input_text: str = None,
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
        Ollama专用的非流式预测方法
        """
        messages = self._prepare_ollama_messages(input_text, sys_prompt, messages)
        
        # Ollama API格式
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        # Ollama支持的参数
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k
        if max_tokens is not None:
            options["num_predict"] = max_tokens  # Ollama使用num_predict
            
        if options:
            payload["options"] = options
            
        # 工具调用支持（如果Ollama版本支持）
        if tools:
            ollama_tools = self._convert_tools_to_ollama_format(tools)
            if ollama_tools:
                payload["tools"] = ollama_tools
                
        # JSON格式支持
        if format == "json":
            payload["format"] = "json"
            
        payload.update(kwargs)
        headers = self._prepare_headers()
        
        try:
            response = httpx.post(self.base_url, json=payload, headers=headers, timeout=timeout)
            
            if response.status_code != 200:
                rep = response.read()
                try:
                    error_data = json.loads(rep.decode('utf-8'))
                    error_message = error_data.get("error", "Unknown Ollama error")
                except:
                    error_message = f"HTTP {response.status_code}: {rep.decode('utf-8') if rep else 'Unknown error'}"
                    
                raise APIRequestFailed(
                    url=self.base_url,
                    status_code=response.status_code,
                    error_details=error_message
                )
            
            response_data = response.json()
            
            # Ollama响应格式转换
            content = ""
            tool_calls = None
            
            if "message" in response_data:
                message = response_data["message"]
                content = message.get("content", "")
                
                # 检查工具调用
                if "tool_calls" in message:
                    tool_calls = {
                        "id": message["tool_calls"][0].get("id", "ollama_tool_call"),
                        "function": {
                            "name": message["tool_calls"][0]["function"]["name"],
                            "arguments": json.dumps(message["tool_calls"][0]["function"]["arguments"])
                        }
                    }
            
            result = {"role": "assistant", "content": content}
            if tool_calls:
                result["tool_calls"] = tool_calls
                
            # Ollama通常不返回token使用信息，使用估算
            if "eval_count" in response_data:
                self.token += response_data.get("prompt_eval_count", 0) + response_data.get("eval_count", 0)
                
            return result
            
        except httpx.ConnectError:
            raise APIRequestFailed(
                url=self.base_url,
                status_code=0,
                error_details="无法连接到Ollama服务。请确保Ollama正在运行并且地址正确。"
            )
        except httpx.TimeoutException:
            raise APIRequestFailed(
                url=self.base_url,
                status_code=0,
                error_details=f"请求超时（{timeout}秒）。模型可能正在加载中，请稍后重试。"
            )
        
    def predictStream(self,
                     input_text: str = None,
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
        Ollama专用的流式预测方法
        """
        messages = self._prepare_ollama_messages(input_text, sys_prompt, messages)
        
        # Ollama流式API格式
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }
        
        # Ollama支持的参数
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k
        if max_tokens is not None:
            options["num_predict"] = max_tokens
            
        if options:
            payload["options"] = options
            
        # 工具调用支持
        if tools:
            ollama_tools = self._convert_tools_to_ollama_format(tools)
            if ollama_tools:
                payload["tools"] = ollama_tools
                
        # JSON格式支持
        if format == "json":
            payload["format"] = "json"
            
        payload.update(kwargs)
        headers = self._prepare_headers()
        
        def stream_generator():
            try:
                with httpx.stream("POST", self.base_url, json=payload, headers=headers, timeout=timeout) as response:
                    if response.status_code != 200:
                        raise APIRequestFailed(
                            url=self.base_url,
                            status_code=response.status_code,
                            error_details=f"Ollama流式请求失败: HTTP {response.status_code}"
                        )
                        
                    accumulated_content = ""
                    tool_calls_buffer = None
                    
                    for line in response.iter_lines():
                        line = line.strip()
                        if not line:
                            continue
                            
                        try:
                            data = json.loads(line)
                            
                            if "message" in data:
                                message = data["message"]
                                
                                # 处理内容
                                if "content" in message:
                                    content = message["content"]
                                    if content:
                                        accumulated_content += content
                                        yield {"role": "assistant", "content": content}
                                
                                # 处理工具调用
                                if "tool_calls" in message:
                                    tool_call = message["tool_calls"][0]
                                    tool_calls_buffer = {
                                        "id": tool_call.get("id", "ollama_tool_call"),
                                        "function": {
                                            "name": tool_call["function"]["name"],
                                            "arguments": json.dumps(tool_call["function"]["arguments"])
                                        }
                                    }
                            
                            # 检查是否完成
                            if data.get("done", False):
                                if tool_calls_buffer:
                                    yield {
                                        "role": "assistant",
                                        "content": "",
                                        "tool_calls": [tool_calls_buffer],
                                        "id": tool_calls_buffer["id"]
                                    }
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
            except httpx.ConnectError:
                raise APIRequestFailed(
                    url=self.base_url,
                    status_code=0,
                    error_details="无法连接到Ollama服务。请确保Ollama正在运行并且地址正确。"
                )
            except httpx.TimeoutException:
                raise APIRequestFailed(
                    url=self.base_url,
                    status_code=0,
                    error_details=f"流式请求超时（{timeout}秒）。模型可能正在加载中，请稍后重试。"
                )
        
        return stream_generator()
        
    def check_model_available(self, model_name: str = None) -> bool:
        """
        检查模型是否可用
        
        Args:
            model_name: 要检查的模型名称，如果为None则检查当前模型
            
        Returns:
            bool: 模型是否可用
        """
        model_to_check = model_name or self.model
        
        try:
            # 获取可用模型列表
            tags_url = self.base_url.replace("/api/chat", "/api/tags")
            response = httpx.get(tags_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                available_models = [model["name"] for model in models]
                return model_to_check in available_models
            else:
                return False
                
        except Exception:
            return False
            
    def list_models(self) -> list:
        """
        获取Ollama中可用的模型列表
        
        Returns:
            list: 可用模型列表
        """
        try:
            tags_url = self.base_url.replace("/api/chat", "/api/tags")
            response = httpx.get(tags_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return [
                    {
                        "name": model["name"],
                        "size": model.get("size", 0),
                        "modified": model.get("modified_at", ""),
                        "digest": model.get("digest", "")
                    }
                    for model in models
                ]
            else:
                return []
                
        except Exception as e:
            print(f"获取模型列表失败: {e}")
            return []
            
    def pull_model(self, model_name: str) -> bool:
        """
        拉取新模型到Ollama
        
        Args:
            model_name: 要拉取的模型名称
            
        Returns:
            bool: 是否拉取成功
        """
        try:
            pull_url = self.base_url.replace("/api/chat", "/api/pull")
            payload = {"name": model_name}
            
            response = httpx.post(pull_url, json=payload, timeout=300)  # 拉取模型可能需要较长时间
            return response.status_code == 200
            
        except Exception as e:
            print(f"拉取模型失败: {e}")
            return False 