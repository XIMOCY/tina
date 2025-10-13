"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：百度文心一言（ERNIE）API接口类，支持百度文心系列模型

文心模型特点：
- 百度自研大语言模型
- 中文能力强，知识丰富
- 支持多种专业领域
- 与百度生态深度集成
"""

from .BaseAPI import BaseAPI

class ERNIE(BaseAPI):
    """
    百度文心一言API类，用于调用百度文心系列模型
    
    支持的模型：
    - ernie-4.0-8k: 最新旗舰模型
    - ernie-4.0-8k-preview: 预览版模型
    - ernie-3.5-8k: 经典版本
    - ernie-3.5-8k-0613: 稳定版本
    - ernie-lite-8k: 轻量版本
    - ernie-speed-128k: 高速长文本版本
    - ernie-speed-8k: 高速版本
    
    环境变量配置：
    - QIANFAN_ACCESS_KEY: 千帆平台Access Key
    - QIANFAN_SECRET_KEY: 千帆平台Secret Key
    - QIANFAN_BASE_URL: API基础URL
    - QIANFAN_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "QIANFAN_ACCESS_KEY"
    BASE_URL = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
    
    def __init__(self, api_key: str = None, model: str = "ernie-4.0-8k", base_url: str = None):
        """
        初始化文心一言API客户端
        
        Args:
            api_key (str, optional): 百度API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "ernie-4.0-8k"
            base_url (str, optional): API基础URL. 默认百度千帆平台地址
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 