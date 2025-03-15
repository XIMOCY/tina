import httpx
import json
import os
from typing import Union, Generator


class BaseAPI():
    API_ENV_VAR_NAME = "API_KEY"  # 默认的API key环境变量名称
    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 默认的base_url

    def __init__(self, api_key: str = None, model: str = "qwen-plus", base_url: str = None):
        if api_key is None:
            try:
                self.api_key = os.environ.get(self.API_ENV_VAR_NAME)
            except KeyError:
                print(f"API key并没有在环境变量‘{self.API_ENV_VAR_NAME}’中找到，要么请你设置一下，要么输入api_key参数")
        else:
            print(f"我们建议你在环境变量中设置{self.API_ENV_VAR_NAME}，不要输入api_key参数哦")
            self.api_key = api_key
        
        self.base_url = base_url if base_url else self.BASE_URL
        self._call = "API"
        self.context_length = 32757
        self.model = model
        self.token = 0

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
            response = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=30)
            response_data = response.json()
            self.token += response_data.get("usage", {}).get("total_tokens", 0)
            
            result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}
            
            # 如果包含工具调用，添加 tool_calls
            tool_calls = response_data["choices"][0]["message"].get("tool_calls")
            if tool_calls:
                result["tool_calls"] = tool_calls
            
            return result

        def stream_generator():
            tool_calls_buffer = {}
            final_tool_calls = None
            received_ids = {}  # 用于保存每个index首次收到的ID
    
            with httpx.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=60) as response:
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            for choice in data.get("choices", []):
                                delta = choice.get("delta", {})
                                result = {"role": "assistant"}

                                # 处理普通内容
                                if "content" in delta:
                                    result["content"] = delta["content"]
                                    yield result

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
                                            if func.get("arguments") is None:
                                                continue
                                            current["function"]["arguments"] += func.get("arguments", "")
                            
                                    # 暂存当前状态
                                    final_tool_calls = [v for k, v in sorted(tool_calls_buffer.items())]

                        except json.JSONDecodeError:
                            continue

                # 流结束时处理最终工具调用
                if final_tool_calls:
                    yield {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": final_tool_calls,
                        "id": final_tool_calls[0]["id"] if final_tool_calls else ""
                    }

        return stream_generator()
