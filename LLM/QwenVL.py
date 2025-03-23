import os
import logging
import httpx
import json
from typing import Union, Generator

class QwenVL:
    def __init__(self, api_key: str = None, model: str = "deepseek-chat", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"):
        self.base_url = base_url
        if api_key is None:
            self.api_key = os.environ.get("DASHSCOPE_API_KEY")
            if not self.api_key:
                raise ValueError("未找到环境变量DASHSCOPE_API_KEY，请设置或传入api_key参数")
        else:
            self.api_key = api_key
            print("建议将API_KEY保存在环境变量DASHSCOPE_API_KEY中")
        
        self.model = model
        self.token = 0
        self._call = "API"
        self.context_length = 32000

    def _encode_image(self, image_path: str) -> str:
        import base64
        """支持多种图片格式编码"""
        allowed_formats = ['.png', '.jpg', '.jpeg', '.webp']
        if not any(image_path.lower().endswith(ext) for ext in allowed_formats):
            raise ValueError(f"不支持的图片格式，仅支持{', '.join(allowed_formats)}")

        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
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
        
        # 自动构建消息逻辑
        if messages is None:
            # messages = [{"role": "system", "content": sys_prompt}]
            messages = []

            # 构建多模态消息
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

        # 其余原有代码保持不变
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            "tools": tools,
            # "extra_body":{"translation_options": { "source_lang": "auto","target_lang": "Persian"}}
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if not stream:
            response = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=timeout)
            response_data = response.json()
            self.token += response_data.get("usage", {}).get("total_tokens", 0)
            result = {"role": "assistant", "content": response_data["choices"][0]["message"]["content"]}
            if "tool_calls" in response_data["choices"][0]["message"]:
                result["tool_calls"] = response_data["choices"][0]["message"]["tool_calls"]
            return result

        def stream_generator():
            tool_calls_buffer = {}
            final_tool_calls = None
            received_ids = {}  # 用于保存每个index首次收到的ID
    
            with httpx.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=timeout) as response:
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
                                    final_tool_calls = [v for k,v in sorted(tool_calls_buffer.items())]

                        except json.JSONDecodeError:
                            continue
        
        return stream_generator()
    
# qwen = QwenVL(api_key="sk-efe077d106f4435f886debafc1a63064",base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",model="qwen-vl-plus")

# result = qwen.predict(
#             input_text="使用html描述文档格式",
#             input_image=r"D:\development\project\translatesByAI\屏幕截图 2025-02-23 123847.png",
#             stream=True,
# )
# c = ""
# for i in result:
#     print(i["content"],end="")
#     c += i["content"]
# result = qwen.predict(
#             input_text=c,
#             sys_prompt="翻译为波斯语",
#             # input_image=r"D:\development\project\translatesByAI\屏幕截图 2025-02-23 123847.png",
#             stream=True,
# )
# for i in result:
#     print(i["content"],end="")