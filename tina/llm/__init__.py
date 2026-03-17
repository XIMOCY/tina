from .ollama_api import OllamaAPI
from .base_api import BaseAPI, BaseMultimodalAPI

__all__ = [
    # 基础类
    "BaseAPI",
    "BaseMultimodalAPI",
    # 原有模型
    "OllamaAPI",
]
