"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：腾讯混元（Hunyuan）API接口类，支持腾讯混元系列模型

混元模型特点：
- 腾讯自研大语言模型
- 多模态能力强
- 中文理解优秀
- 与腾讯云生态集成
"""

from .BaseAPI import BaseAPI

class Hunyuan(BaseAPI):
    """
    腾讯混元API类，用于调用腾讯混元系列模型
    
    支持的模型：
    - hunyuan-pro: 专业版模型
    - hunyuan-standard: 标准版模型
    - hunyuan-lite: 轻量版模型
    - hunyuan-turbo: 高速版模型
    
    环境变量配置：
    - TENCENT_SECRET_ID: 腾讯云Secret ID
    - TENCENT_SECRET_KEY: 腾讯云Secret Key
    - TENCENT_BASE_URL: API基础URL
    - TENCENT_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "TENCENT_SECRET_KEY"
    BASE_URL = "https://hunyuan.tencentcloudapi.com/"
    
    def __init__(self, api_key: str = None, model: str = "hunyuan-pro", base_url: str = None):
        """
        初始化腾讯混元API客户端
        
        Args:
            api_key (str, optional): 腾讯云API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "hunyuan-pro"
            base_url (str, optional): API基础URL. 默认腾讯云地址
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 