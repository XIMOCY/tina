from .api import BaseAPI_multimodal

class QwenVL(BaseAPI_multimodal):
    API_ENV_VAR_NAME = "DASHSCOPE_API_KEY"
    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    def __init__(self, api_key: str = None, model: str = "qwen-vl-plus", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"):
        super().__init__(model=model, api_key=api_key, base_url=base_url)
    
