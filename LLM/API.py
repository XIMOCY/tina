"""
编写者：王出日
日期：2025，5，20
版本 0.4.2
描述：使用httpx库实现的API调用类，包含了API请求、token管理、工具调用等功能

包含：
- BaseAPI: 基础API类，所有使用api访问大模型的类都继承自此类
- BaseAPI_multimodal: 多模态API类，继承自BaseAPI，增加了图片参数
"""
import httpx
import json
import os
from typing import Union, Generator
from ..utils.envReader import load_env, get_env


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
                env_path:str = os.path.join(os.getcwd(), ".env"),
                ):
        load_env(env_path)
        try:
            self.api_key = get_env(self.API_ENV_VAR_NAME) if api_key is None else api_key
            self.base_url = get_env("BASE_URL") if base_url is None else base_url
            self.model = get_env("MODEL_NAME") if model is None else model
        except KeyError:
            pass
        if not self.api_key:
            raise ValueError(f"API key并没有在环境变量'{self.API_ENV_VAR_NAME}'和{env_path}中找到，要么请你设置一下，要么输入api_key参数")
        if not self.base_url:
            raise ValueError(f"Base_url并没有在环境变量'BASE_URL'和{os.path.join(env_path, ".env")}中找到，要么请你设置一下，要么输入base_url参数")
        if not self.model:
            raise ValueError(f"模型名称并没有在环境变量'MODEL_NAME'和{os.path.join(env_path, ".env")}中找到，要么请你设置一下，要么输入model参数")
        
        # if api_key is None:
        #     try:
        #         self.api_key = get_env(self.API_ENV_VAR_NAME)
        #     except KeyError:
        #         raise ValueError(f"API key并没有在环境变量'{self.API_ENV_VAR_NAME}'和{os.path.join(env_path, ".env")}中找到，要么请你设置一下，要么输入api_key参数")
        # else:
        #     print(f"我们建议你在环境变量中设置{self.API_ENV_VAR_NAME}，不要输入api_key参数哦")
        #     self.api_key = api_key
        
        self.MAX_INPUT = get_env("MAX_INPUT") if not get_env("MAX_INPUT") is None else 8000


        self.token = 0
        self.token_list=[]

        self._call = "API"

    def getTokens(self) -> int:
        """返回消耗的token数量"""
        return self.token

    def predict(self,
                input_text: str = None,
                sys_prompt: str = '你的工作非常的出色！',
                messages: list = None,
                temperature: float = 0.3,
                top_p: float = 0.9,
                stream: bool = False,
                format:str = "text",
                json_format:str = '{}',
                tools: list = None) -> Union[dict, Generator[dict, None, None]]:
        """
        调用大语言模型执行预测任务，支 持单次对话和多轮对话模式

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            sys_prompt (str, optional): 系统提示词. 默认为 "你的工作非常的出色！".
            messages (list, optional): 历史对话消息列表. 格式为:
                [{"role": "system", "content": "..."}, 
                {"role": "user", "content": "..."}, 
                {"role": "assistant", "content": "..."}]. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 0.3.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            format (str, optional): 返 回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工 具调用列表. 格式为:
                [{"name": "...", "description": "...", "parameters": {...}}]. 默认 None.

        Returns:
            dict: 
            - 非流式模式返回字典格式：
            - {"role": "assistant", "content": "...", "tool_calls": [...]}

            Generator[dict, None, None]]:
            - 流式模式返回生成器，逐块 返回响应内容和/或工具调用信息

        Raises:
            Exception: 当API调用失败时 抛出异常

        Examples:
            ### 单次对话模式
            >>> predict(input_text="你 好")
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}

            ### 多轮对话模式
            >>> messages = [{"role": "user", "content": "北京天气如何？"}]
            >>> predict(messages=messages, tools=[weather_tool])
            {"role": "assistant", "content": "", "tool_calls": [{"name": "get_weather", "arguments": {"location": "北京"}}]}
        """
        if messages is None:
            messages = []
            messages.append({"role": "system", "content": sys_prompt})
            # 处理消息列表
            if input_text:
                messages.append({"role": "user", "content": input_text})

        # 请求参数
        format_dict = {
            'text': 'text',
            'json': 'json_object'
        }
        format = format_dict[format]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            "tools": tools
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # **非流式请求**
        if not stream:
            response = httpx.post(f"{self.base_url}", json=payload, headers=headers, timeout=180)
            response_data = response.json()
            self.token += response_data.get("usage", {}).get("total_tokens", 0)
            
            result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}
            
            # 如果包含工具调用，添加 tool_calls
            if "tool_calls" in response_data["choices"][0]["message"]:
                tool_calls = response_data["choices"][0]["message"].get("tool_calls",[])
                # 修改为需要的格式，开发者可以直接将这个工具使用追加到消息列表
                tool_calls = {
                    "id":tool_calls[0]["id"],
                    "function":tool_calls[0]["function"],
                }
                if tool_calls:
                    result["tool_calls"] = tool_calls
            return result

        def stream_generator():
            tool_calls_buffer = {}
            final_tool_calls = None
            received_ids = {}  # 
            tool_name_sent = set()  # 记录已经发送过名称的工具索引
            reasoning_buffer = ""  # 缓存推理内容
    
            with httpx.stream("POST", f"{self.base_url}", json=payload, headers=headers, timeout=60) as response:
                try:
                    if response.status_code != 200:
                        raise Exception(f"请求失败了，状态码：{response.status_code}")
                except Exception as e:
                    rep = response.read()
                    yield {"role":"assistant", "content": str(e) + f"\n{rep.decode('utf-8')}"}
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            for choice in data.get("choices", []):
                                delta = choice.get("delta", {})

                                # 处理普通内容
                                if "content" in delta:
                                    content = delta.get("content", "")
                                    if content:  # 只有当内容非空时才发送
                                        yield {"role": "assistant", "content": content}
                                
                                # 处理推理模型的内容
                                if "reasoning_content" in delta:
                                    reasoning_content = delta.get("reasoning_content", "")
                                    if reasoning_content:  # 累积推理内容
                                        reasoning_buffer += reasoning_content
                                        yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}

                                # 处理工具调用
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        index = tool_call["index"]
                                
                                        # 初始化缓冲区
                                        if index not in tool_calls_buffer:
                                            tool_calls_buffer[index] = {
                                                "index": index,
                                                "function": {"arguments": ""},
                                                "type": "",
                                                "id": ""
                                            }
                                
                                        # 保留首次收到的ID
                                        if tool_call.get("id") and index not in received_ids:
                                            received_ids[index] = tool_call["id"]
                                
                                        # 更新字段（保留首次ID）
                                        current = tool_calls_buffer[index]
                                        current["id"] = received_ids.get(index, "")
                                        current["type"] = tool_call.get("type") or current["type"]
                                
                                        # 处理函数参数
                                        if tool_call.get("function"):
                                            func = tool_call["function"]
                                            current["function"]["name"] = func.get("name") or current["function"].get("name", "")
                                            
                                            # 如果这是第一次接收到工具名称且未发送过，会发送工具名称，在外部通过tool_name获取
                                            if current["function"].get("name") and index not in tool_name_sent:
                                                tool_name_sent.add(index)
                                                yield {
                                                    "role": "assistant",
                                                    "content": "",
                                                    "tool_name": current["function"]["name"]
                                                }
                                            
                                            if func.get("arguments") is None:
                                                continue
                                            current["function"]["arguments"] += func.get("arguments", "")
                            
                                    # 暂存当前状态
                                    final_tool_calls = [v for k, v in sorted(tool_calls_buffer.items())]

                        except json.JSONDecodeError:
                            continue

                # 第一次会发送工具名称，而后会将完整的工具调用语句发送
                if final_tool_calls:
                    yield {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": final_tool_calls,
                        "id": final_tool_calls[0]["id"] if final_tool_calls else ""
                    }

        return stream_generator()

    
class BaseAPI_multimodal(BaseAPI):
    API_ENV_VAR_NAME = ""  # 覆盖环境变量名
    BASE_URL = ""  # 设置基础URL

    def __init__(self, model: str , api_key: str = None, base_url: str = None):
        super().__init__(model=model, api_key=api_key, base_url=base_url)
    
    def _encode_image(self, image_path: str) -> str:
        import base64
        allowed_formats = ['.png', '.jpg', '.jpeg', '.webp']
        if not any(image_path.lower().endswith(ext) for ext in allowed_formats):
            raise ValueError(f"不支持的图片格式，仅支持{', '.join(allowed_formats)}")
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            import logging
            logging.error(f"图片读取失败: {str(e)}")
            raise
    
    def predict(self,
                input_text: str = None,
                input_image: str = None,  # 新增图片参数
                sys_prompt: str = '你的工作非常出色！',
                messages: list = None,
                temperature: float = 0.3,
                top_p: float = 0.9,
                stream: bool = False,
                tools: list = None,
                timeout: int = 60) -> Union[dict, Generator[dict, None, None]]:
        
        if messages is None:
            messages = [{"role": "system", "content": sys_prompt}]
            user_content = []
            if input_image:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{input_image.split('.')[-1]};base64,{self._encode_image(input_image)}"
                    }
                })
            if input_text:
                user_content.append({"type": "text", "text": input_text})

            if user_content:
                messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            "tools": tools,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if not stream:
            response = httpx.post(f"{self.base_url}", json=payload, headers=headers, timeout=timeout)
            response_data = response.json()
            self.token += response_data.get("usage", {}).get("total_tokens", 0)
            result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}
            if "tool_calls" in response_data["choices"][0]["message"]:
                result["tool_calls"] = response_data["choices"][0]["message"]["tool_calls"]
            return result

        def stream_generator():
            tool_calls_buffer = {}
            final_tool_calls = None
            received_ids = {}  
            tool_name_sent = set()  
            reasoning_buffer = ""  # 缓存推理内容

            with httpx.stream("POST", f"{self.base_url}", json=payload, headers=headers, timeout=timeout) as response:
                if response.status_code != 200:
                    raise Exception(f"请求失败了，状态码：{response.status_code}")
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            for choice in data.get("choices", []):
                                delta = choice.get("delta", {})

                                # 处理普通内容
                                if "content" in delta:
                                    content = delta.get("content", "")
                                    if content:  # 只有当内容非空时才发送
                                        yield {"role": "assistant", "content": content}
                                
                                # 处理推理内容
                                if "reasoning_content" in delta:
                                    reasoning_content = delta.get("reasoning_content", "")
                                    if reasoning_content:  # 累积推理内容
                                        reasoning_buffer += reasoning_content
                                        yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}

                                # 处理工具调用
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        index = tool_call["index"]
                                
                                        if index not in tool_calls_buffer:
                                            tool_calls_buffer[index] = {
                                                "index": index,
                                                "function": {"arguments": ""},
                                                "type": "",
                                                "id": ""
                                            }
                                
                                        if tool_call.get("id") and index not in received_ids:
                                            received_ids[index] = tool_call["id"]
                                
                                        current = tool_calls_buffer[index]
                                        current["id"] = received_ids.get(index, "")
                                        current["type"] = tool_call.get("type") or current["type"]
                                
                                        if tool_call.get("function"):
                                            func = tool_call["function"]
                                            current["function"]["name"] = func.get("name") or current["function"].get("name", "")
                                            
                                            if current["function"].get("name") and index not in tool_name_sent:
                                                tool_name_sent.add(index)
                                                yield {
                                                    "role": "assistant",
                                                    "content": "",
                                                    "tool_name": current["function"]["name"]
                                                }
                                            
                                            if func.get("arguments") is None:
                                                continue
                                            current["function"]["arguments"] += func.get("arguments", "")
                            
                                    final_tool_calls = [v for k,v in sorted(tool_calls_buffer.items())]

                        except json.JSONDecodeError:
                            continue
                
                if final_tool_calls:
                    yield {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": final_tool_calls,
                        "id": final_tool_calls[0]["id"] if final_tool_calls else ""
                    }
        
        return stream_generator()
