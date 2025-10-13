from .llama import llama
from .Qwen import Qwen
from .DeepSeek import DeepSeek
from .BaseAPI import BaseAPI, BaseAPI_multimodal
from .QwenVL import QwenVL

# 新增主流大模型厂商类
from .Claude import Claude
from .ClaudeVision import ClaudeVision
from .OpenAI import OpenAI
from .ChatGLM import ChatGLM
from .Doubao import Doubao
from .ERNIE import ERNIE
from .Kimi import Kimi
from .Hunyuan import Hunyuan

# 本地模型支持
from .Ollama import Ollama

__all__ = [
    # 基础类
    "BaseAPI", "BaseAPI_multimodal",
    
    # 原有模型
    "llama", "Qwen", "QwenVL", "DeepSeek",
    
    # 新增主流模型
    "Claude", "ClaudeVision",
    "OpenAI", 
    "ChatGLM",
    "Doubao",
    "ERNIE",
    "Kimi",
    "Hunyuan",
    
    # 本地模型
    "Ollama"
]