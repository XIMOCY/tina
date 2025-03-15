"""
Tina is in your Computer!
启动你的tina吧！
基于tina.Agent的智能体
自动执行tina的各种操作
"""
import threading
import os
import time
import random
from tina.core.manage import TinaFolderManager
from tina.core.prompt import Prompt
from tina.core.tools import Tools
from tina.RAG.Embedding.docToVec import docToVec
from tina.Agent import Agent

class Tina:
    def __init__(self, path:str = None, LLM=None, tools:type = None,toolsLib:str = None, stream:bool = True, timeout:int = 600,embeding_model:str = None,isSystem:bool = False, isRAG:bool = False, is_tool_call_permission:bool=False):
        """
        初始化你的控制台tina
        Args:
            path:tina储存记忆，消息和你上传的文件的路径
            LLM:语言模型，目前只支持llama
            tools:你自定义的工具
            toolsLib:你自定义的工具库，python文件路径
            stream:是否实时输出结果
            isSystem:是否使用tina自带的系统工具
            isRAG:是否使用tina自带的RAG工具
            is_tool_call_permission:是否允许工具对系统做出危险操作
        """
        if path is None:
            path = os.path.dirname(__file__)
        if LLM is None:
            raise NotImplementedError("Tina现在还不支持自动加载模型呢，请实例化一个LLM后交给我吧")
        if isRAG is True and embeding_model is None:
            raise ValueError("如果没有向量模型的话，tina没法使用RAG功能哦，使用参数embeding_model指定向量模型路径吧")
        TinaFolderManager.init(path)
        TinaFolderManager.setEmbedingModel(embeding_model)
        self.Tools = Tools(isSystemTools=isSystem, isRAG=isRAG)
        if tools is not None:
            self.Tools.multiregister(tools)
        if toolsLib is not None:
            self.Tools += Tools.loadToolsFromPyFile(toolsLib)
        self.stream = stream
        self.Prompt = Prompt()
        self.agent = Agent(LLM, self.Tools, self.Prompt, is_tool_call_permission)
        self.timeout = timeout
        self.isRAG = isRAG
        self.fileUpload = False
        self.isChat = False
        self.isRemember = False
        self.isExit = False
        self.lock = threading.Lock()

    def run(self,memory_timeout:int=600):
        self.show_start()
        with self.lock:  
            run_thread = threading.Thread(target=self.run_lowerFace)
            remember_thread = threading.Thread(target=self.remembeing,args=(self.timeout,))
            remember_thread.daemon = True
            run_thread.start()
            remember_thread.start()
            if self.isRemember:
                remember_thread.join()

    

    def run_lowerFace(self):
        while True:
            if self.isRemember is False:
                user_input = input("\n( • ̀ω•́ ) >>>User:\n")
                if user_input == "#exit":
                    self.exit()
                    break
                elif user_input == "#file":
                    self.file()
                elif user_input == "#help":
                    self.help()
                elif user_input == "#clear":
                    self.clear() 
                elif user_input == "#rag":
                    if self.isRAG is True:
                        self.rag()
                elif user_input.startswith("#rag -isCopy="):
                    if self.isRAG is True:
                        isCopy = user_input.split("=")[1]
                        if isCopy.lower() == "true":
                            self.rag(isCopy=True)
                        else:
                            self.rag()
                    else:
                        print("你没有开启RAG功能，在实例化的时候添加参数isRAG=True再来试试？")
                else:

                    self.chat(user_input)
            else:
                continue
    def rag(self,isCopy:bool = False):
        foler_path = input("📂 >>>文件夹路径：")
        try:
            docToVec(file_path=foler_path,isCopyToTinaFolder=isCopy)
            print("✅ 文档库建立成功！")
        except Exception as e:
            print(f"❌ 文档库建立失败: {e}")

    def exit(self):
        print("再见 ヾ(￣▽￣)Bye~Bye~")
        self.isExit = True
        self.remembeing(timeout=0)

    def remembeing(self,timeout=None):
        while True:
            if self.isChat is False and self.isRemember is False and self.isExit is False:
                if timeout is None:
                    time.sleep(self.timeout)
                else:
                    time.sleep(timeout)
                with self.lock:  # 使用with语句来锁定和释放锁
                    self.isRemember = True
                    animation_thread = threading.Thread(target=self.show_remember_animation)
                    agent_remember_thread = threading.Thread(target=self.agent.remember)
                    animation_thread.daemon = True
                    animation_thread.start()
                    agent_remember_thread.start()
                    agent_remember_thread.join()
                    self.isRemember = False
                    time.sleep(2)
            if self.isRemember is False:
                print("                                  ", end='\r')
                print("(ゝ∀･)⌒☆ tina记忆完毕!")
            if self.isExit:
                break
            print("\n>>>User:")

    def file(self):
        self.fileUpload = True
        print(">>>请上传文件（输入文件的URL或路径）")
        file_path = input("📂 >>>File:")
        try:
            self.agent.readFile(file_path)
            print("✅ 文件读取成功")
        except Exception as e:
            print(f"❌ 文件读取失败: {e}")
        self.fileUpload = False

    def help(self):
        print("📄 帮助文档：")
        print("🛠️ 系统控制台指令：")
        print("#exit: 退出对话,退出时，tina需要一段时间来记忆这次的对话，所以可能会占点时间哦")
        print("#file: 文件上传，tina可以读取本地文件并进行对话，读取过后，用户可以接着对话，文件内容会被包含在上文中")
        print("#help: 查看帮助，就是查看帮助文档啦")
        print("#rag: 建立文档库，tina可以将本地文件夹中的文档转换为向量并建立Faiss索引，这样你就可以使用RAG功能了，试试问她文档里面的有关信息吧")
        print("     参数：isCopy 是否将文件复制到一个Tina的专用文件夹，默认为True,用法：#rag -isCopy=True 该命令可以复制到Tina的专用文件夹")
        print("#clear: 清屏，当文字太多了的时候就用它吧")
        print("\n⚙️ 参数文档：")
        print("path: tina储存记忆，消息和你上传的文件的路径，可以认为叫做tina的家目录，tina运行产生的各种文件都将保存在这里")
        print("LLM: 语言模型，支持GGUF格式的模型，也支持API形式的模型，那是tina的大脑，没了可就理解不了你说的话了")
        print("tools: 你自定义的工具，python函数形式，可以是任何你想实现的功能，只要你写好了，tina就可以调用它来完成你想做的事情，注意指定python代码的路径哦")
        print("stream: 是否实时输出结果，如果是True，tina会实时输出对话结果，如果是False，tina会在对话结束后输出结果")
        print("timeout: tina记忆的超时时间，默认是600秒，如果用户一直不说话，tina会在这段时间后开始记忆")
        print("embeding_model: 向量模型路径，如果开启RAG功能，tina需要使用向量模型来建立文档库，你需要指定向量模型的路径")
        print("isSystem: 是否使用tina自带的系统工具，如果是True，tina会自动加载系统工具，你可以在这里添加你自己的系统工具")
        print("isRAG: 是否使用tina自带的RAG工具，如果是True，tina会自动加载RAG工具，你可以在这里添加你自己的RAG工具")

    def clear(self):
        self.show_start()

    def show_start(self):
        os.system("cls")
        self.show_random_animation()
        print("😊 欢迎使用tina，你可以输入#help来查看帮助")
        print('🤔 退出对话："#exit"\n📤 文件上传："#file"\n')
        print('😀 当出现"tina正在记忆信息时..."请不要打断\n')

    def chat(self, user_input):
        self.isChat = True
        result = self.agent.predict(input_text=user_input,stream=self.stream)
        if self.stream:
            print("\n(・∀・) >>>tina:")
            for chunk in result:
                print(chunk, end="", flush=True)
        else:
            print(result["content"])
        self.isChat = False

    def show_remember_animation(self):
        messages = [
            '(≧∀≦)ゞ  tina正在记忆信息',
            '(≧∀≦)ゞ  tina正在记忆信息.',
            '(≧∀≦)ゞ  tina正在记忆信息..',
            '(≧∀≦)ゞ  tina正在记忆信息...'
        ]

        while self.isRemember:
            for i in range(len(messages)):
                print("                                  ", end='\r')
                print(messages[i], end='\r')  # 使用end='\r'将光标移回行首
                time.sleep(0.5)

    def show_random_animation(self):
        animations = [
            '(￣▽￣) ',
            '(´▽`ʃ♡ƪ)" ',
            '(ゝ∀･)ﾉ ',
            '(ノ^∇^)ノ ',
            '(・∀・) ',
            '(∩^o^)⊃━☆ﾟ.*･｡ '
        ]
        animation = random.choice(animations)
        print(animation,"tina by QiQi in 🌟 XIMO\n\n")

