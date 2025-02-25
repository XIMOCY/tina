"""
Tina is in your Computer!
启动你的tina吧！
基于tina.Agent的智能体
自动执行tina的各种操作
"""
import threading
import os
import time

from tina.core.manage import TinaFolderManager
from tina.core.prompt import Prompt
from tina.core.tools import Tools
from tina.LLM.llama import llama
from tina.Agent import Agent

class Tina:
    def __init__(self, path:str = None, LLM=None, tools:list = None, stream:bool = True, isSystem:bool = False, isRAG:bool = False, is_tool_call_permission:bool=False):
        """
        初始化你的控制台tina
        Args:
            path:tina储存记忆，消息和你上传的文件的路径
            LLM:语言模型，目前只支持llama
            tools:你自定义的工具
            stream:是否实时输出结果
            isSystem:是否使用tina自带的系统工具
            isRAG:是否使用tina自带的RAG工具
            is_tool_call_permission:是否允许工具对系统做出危险操作
        """
        if path is None:
            path = os.path.dirname(__file__)
        if LLM is None:
            raise NotImplementedError("Tina现在还不支持自动加载模型呢，请实例化一个LLM后交给我吧")
        if tools is not None:
            self.Tools.multiregister(tools)
        TinaFolderManager.init(path)
        self.Tools = Tools(isSystemTools=isSystem, isRAG=isRAG)
        self.stream = stream
        self.Prompt = Prompt()
        self.agent = Agent(LLM, self.Tools, self.Prompt, is_tool_call_permission)
        
        self.fileUpload = False
        self.isChat = False
        self.isRemmember = False


        self.lock = threading.Lock()

    def run(self):
        run_thread = threading.Thread(target=self.run_lowerFace)
        remember_thread = threading.Thread(target=self.remembeing)
        run_thread.start()
        remember_thread.start()
        run_thread.join()
        remember_thread.join()

    def run_lowerFace(self):
        print('退出对话："#exit"\n文件上传："#file"\n')
        print('当出现"tina正在记忆信息时..."请不要打断\n')
        while True:
            user_input = input(">>>User:")
            if user_input == "#exit":
                print(">>>再见ヾ(￣▽￣)Bye~Bye~")
                break
            elif user_input == "#file":
                self.fileUpload = True
                print(">>>请上传文件（输入文件的URL或路径）")
                file_path = input(">>>File:")
                try:
                    self.agent.readFile(file_path)
                except Exception as e:
                    print(f"文件读取失败: {e}")
                self.fileUpload = False
            else:
                self.isChat = True
                result = self.agent.predict(user_input)
                if self.stream:
                    try:
                        for chunk in result:
                            print(chunk, end="", flush=True)
                    except TypeError:
                        print(result)  # 如果result不是可迭代的对象，直接打印
                else:
                    print(result["content"])
                self.isChat = False

    def remembeing(self):
        while True:
            time.sleep(300)
            if self.isChat is False:
                with self.lock:  # 使用with语句来锁定和释放锁
                    self.isRemmember = True
                    animation_thread = threading.Thread(target=self.show_remember_animation)
                    agent_remember_thread = threading.Thread(target=self.agent.remember)  # 修改：假设方法名为remember
                    animation_thread.start()
                    agent_remember_thread.start()
                    self.isRemmember = False
                    animation_thread.join()
                    agent_remember_thread.join()

    def show_remember_animation(self):
        messages = [
            '(≧∀≦)ゞ tina正在记忆信息',
            '(≧∀≦)ゞ tina正在记忆信息.',
            '(≧∀≦)ゞ tina正在记忆信息..',
            '(≧∀≦)ゞ tina正在记忆信息...'
        ]

        while self.isRemmember:
            for i in range(len(messages)):
                print("                     ", end='\r')
                print(messages[i], end='\r')  # 使用end='\r'将光标移回行首
                time.sleep(0.5)
        print("tina记忆完毕!")
