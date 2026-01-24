from .ollama_api import OllamaAPI
from .BaseAPI import BaseAPI, BaseMultimodalAPI



__all__ = [
    # 基础类
    "BaseAPI", "BaseMultimodalAPI",
    
    # 原有模型
    "OllamaAPI",
]