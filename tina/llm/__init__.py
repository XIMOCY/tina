from .ollama_api import OllamaAPI
from .base_api import BaseAPI
from .base_multimodal_api import BaseMultimodalAPI

__all__ = [
    # 基础类
    "BaseAPI",
    "BaseMultimodalAPI",
    # 原有模型
    "OllamaAPI",
]
