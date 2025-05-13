"""
设定agent的环境
"""
import os
import platform
from .core.manage import TinaFolderManager
from .LLM import BaseAPI

class Environment:
    def __init__(self, path,api_config_path=None):
        
        TinaFolderManager.setEnv(path)
        self.global_llm = 

if __name__ == '__main__':
    env = Environment(r'D:\development\project\TCG\test')
    print(env.info)
