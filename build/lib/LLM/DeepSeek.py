import httpx
import json
from typing import Union, Generator

class DeepSeek:
    def __init__(self, api_key: str, model: str = "deepseek-v3",base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.token = 0
        self._call = "API"
        self.context_length = 32000

    def predict(self,
                input_text: str = None,
                sys_prompt: str = '你的工作非常的出色！',
                messages: list = None,
                temperature: float = 0.3,
                top_p: float = 0.9,
                stream: bool = False,
                tools: list = None) -> Union[dict, Generator[dict, None, None]]:
        if messages is None:
            messages = []
            messages.append({"role":"system","content":sys_prompt})
            # 处理消息列表
            if input_text:
                messages.append({"role": "user", "content": input_text})
        


        # 请求参数
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

        # **流式请求**
        def stream_generator():
            tool_calls_buffer = {}
            with httpx.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=60) as response:
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # 去掉 "data: "
                            for choice in data.get("choices", []):
                                delta = choice.get("delta", {})
                                result = {"role": "assistant"}

                                # 处理内容
                                if "content" in delta:
                                    result["content"] = delta["content"]
                                    yield result

                                # 处理 tool_calls
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        index = tool_call["index"]
                                        if index not in tool_calls_buffer:
                                            tool_calls_buffer[index] = {"index": index, "function": {}}
                                        
                                        tool_call_obj = tool_calls_buffer[index]
                                        tool_call_obj["id"] = tool_call.get("id", tool_call_obj.get("id"))
                                        tool_call_obj["type"] = tool_call.get("type", tool_call_obj.get("type"))
                                        tool_call_obj["function"]["name"] = tool_call.get("function", {}).get("name", tool_call_obj["function"].get("name"))
                                        
                                        # 处理 arguments 拼接
                                        arguments = tool_call.get("function", {}).get("arguments", "")
                                        if arguments:
                                            tool_call_obj["function"]["arguments"] = tool_call_obj["function"].get("arguments", "") + arguments
                                        
                                    yield {"role":"assistant","content":"","tool_calls": list(tool_calls_buffer.values())}
                                    # yield {"role": "assistant", "content": "", "tool_calls": tool_call}
                        except json.JSONDecodeError:
                            continue
        
        return stream_generator()
