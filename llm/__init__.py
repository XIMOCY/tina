from .local_model_llama_cpp import LocalModelUsingLlamaCpp

from .BaseAPI import BaseAPI, BaseMultimodalAPI



__all__ = [
    # 基础类
    "BaseAPI", "BaseMultimodalAPI",
    
    # 原有模型
    "local_model_llama_cpp",
]