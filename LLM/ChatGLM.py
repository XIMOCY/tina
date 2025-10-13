"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：智谱GLM API接口类，支持智谱AI GLM系列模型

GLM模型特点：
- 中文理解能力强
- 支持长文本处理
- 多模态支持（GLM-4V）
- 中国本土优化
"""

from .BaseAPI import BaseAPI

class ChatGLM(BaseAPI):
    """
    智谱GLM API类，用于调用智谱AI GLM系列模型
    
    支持的模型：
    - glm-4-plus: 最新最强模型
    - glm-4-0520: 稳定版本
    - glm-4: 标准版本
    - glm-4-air: 轻量版本
    - glm-4-airx: 超轻量版本
    - glm-4-flash: 快速版本
    
    环境变量配置：
    - ZHIPU_API_KEY: 智谱AI API密钥
    - ZHIPU_BASE_URL: API基础URL (默认: https://open.bigmodel.cn/api/paas/v4)
    - ZHIPU_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "ZHIPU_API_KEY"
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    def __init__(self, api_key: str = None, model: str = "glm-4-plus", base_url: str = None):
        """
        初始化智谱GLM API客户端
        
        Args:
            api_key (str, optional): 智谱AI API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "glm-4-plus"
            base_url (str, optional): API基础URL. 默认智谱AI官方地址
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url) 