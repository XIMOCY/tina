from openai import OpenAI

from typing import Union, Generator
class Kimi():
    def __init__(self,api_key,model:str="moonshot-v1-auto"):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        self.model = model

    def predict(self,
                input_text: str = None,
                sys_prompt: str = '你的工作非常的出色！',
                messages: list = None,
                temperature: float = 0.3,
                top_p: float = 0.9,
                top_k: int = 0,
                min_p: float = 0,
                stream: bool = False,
                format: str = 'text',
                json_format: str = '{}',
                tools: list = []) -> Union[dict, Generator]:
    
        # 如果 input_text 不为空，则将其作为用户消息
        if input_text:
            user_message = {"role": "user", "content": input_text}
            messages = [user_message] if messages is None else messages + [user_message]
    
        # 如果 sys_prompt 不为空，则将其作为系统消息
        if sys_prompt:
            system_message = {"role": "system", "content": sys_prompt}
            messages = [system_message] if messages is None else messages + [system_message]
    
        # 调用 API 生成响应
        result = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            stream=stream,
            format=format,
            json_format=json_format,
            tools=tools
        )
        return result