from .local_model_llama_cpp import LocalModelUsingLlamaCpp

from .BaseAPI import BaseAPI, BaseAPI_multimodal



__all__ = [
    # 基础类
    "BaseAPI", "BaseAPI_multimodal",
    
    # 原有模型
    "local_model_llama_cpp",
]