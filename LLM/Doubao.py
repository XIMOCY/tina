"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：字节豆包（Doubao）API接口类，支持字节跳动豆包系列模型

豆包模型特点：
- 字节跳动自研大模型
- 中文优化，理解能力强
- 推理速度快
- 支持多种场景应用
"""

from .BaseAPI import BaseAPI

class Doubao(BaseAPI):
    """
    字节豆包API类，用于调用字节跳动豆包系列模型
    
    支持的模型：
    - doubao-pro-4k: 专业版模型
    - doubao-pro-32k: 长文本专业版
    - doubao-pro-128k: 超长文本专业版
    - doubao-lite-4k: 轻量版模型
    - doubao-lite-32k: 长文本轻量版
    - doubao-lite-128k: 超长文本轻量版
    
    环境变量配置：
    - ARK_API_KEY: 豆包API密钥
    - ARK_BASE_URL: API基础URL
    - ARK_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "ARK_API_KEY"
    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    
    def __init__(self, api_key: str = None, model: str = "doubao-pro-4k", base_url: str = None):
        """
        初始化豆包API客户端
        
        Args:
            api_key (str, optional): 豆包API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "doubao-pro-4k"
            base_url (str, optional): API基础URL. 默认火山引擎地址
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 