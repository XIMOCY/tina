"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：月之暗面Kimi API接口类，支持Moonshot Kimi系列模型

Kimi模型特点：
- 超长上下文（最高200万字符）
- 网络实时搜索能力
- 文档解析能力强
- 专注于长文本理解
"""

from .BaseAPI import BaseAPI

class Kimi(BaseAPI):
    """
    月之暗面Kimi API类，用于调用Moonshot Kimi系列模型
    
    支持的模型：
    - moonshot-v1-8k: 标准版本
    - moonshot-v1-32k: 长文本版本
    - moonshot-v1-128k: 超长文本版本
    
    环境变量配置：
    - MOONSHOT_API_KEY: Moonshot API密钥
    - MOONSHOT_BASE_URL: API基础URL (默认: https://api.moonshot.cn/v1)
    - MOONSHOT_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "MOONSHOT_API_KEY"
    BASE_URL = "https://api.moonshot.cn/v1/chat/completions"
    
    def __init__(self, api_key: str = None, model: str = "moonshot-v1-32k", base_url: str = None):
        """
        初始化Kimi API客户端
        
        Args:
            api_key (str, optional): Moonshot API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "moonshot-v1-32k"
            base_url (str, optional): API基础URL. 默认月之暗面官方地址
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 