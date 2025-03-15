from .api import BaseAPI

class DeepSeek(BaseAPI):
    API_ENV_VAR_NAME = "DEEPSEEK_API_KEY"  # 重写API key环境变量名称
    BASE_URL = "https://api.deepseek.com/v1"  # 重写base_url

    def __init__(self, api_key: str = None, model: str = "deepseek-chat", base_url: str = None):
        super().__init__(api_key, model, base_url)
