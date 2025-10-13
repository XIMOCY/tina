"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：OpenAI API接口类，支持OpenAI GPT系列模型

OpenAI模型特点：
- 业界标准的API格式
- 强大的通用能力
- 支持工具调用和JSON模式
- 丰富的模型选择
"""

from .BaseAPI import BaseAPI

class OpenAI(BaseAPI):
    """
    OpenAI API类，用于调用OpenAI GPT系列模型
    
    支持的模型：
    - gpt-4o: 最新最强多模态模型
    - gpt-4o-mini: 高性价比模型
    - gpt-4-turbo: 强大的文本模型
    - gpt-4: 经典强模型
    - gpt-3.5-turbo: 经济实用模型
    
    环境变量配置：
    - OPENAI_API_KEY: OpenAI API密钥
    - OPENAI_BASE_URL: API基础URL (默认: https://api.openai.com/v1)
    - OPENAI_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "OPENAI_API_KEY"
    BASE_URL = "https://api.openai.com/v1/chat/completions"
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini", base_url: str = None):
        """
        初始化OpenAI API客户端
        
        Args:
            api_key (str, optional): OpenAI API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "gpt-4o-mini"
            base_url (str, optional): API基础URL. 默认 "https://api.openai.com/v1/chat/completions"
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 