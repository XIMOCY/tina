"""
编写者：王出日
日期：2024，12，13
版本？

将llama-cpp-python封装为需要的接口
llama.cpp Github地址：https://github.com/ggerganov/llama.cpphttps://github.com/ggerganov/llama.cpp
llama-cpp-python Github地址：https://github.com/abetlen/llama-cpp-python
llama类基于llama-cpp-python实现
使用更简单的语言描述让开发者更快的上手
qwen模型网址：https://github.com/QwenLM/Qwenhttps://github.com/QwenLM/Qwen
"""
import os
from typing import Union,Generator
from tina.core.error import TinaError, ModelPathNotGiven

supported_model_interface_engine = {"llama_cpp", "tina_model_interface_engine"}


class LocalModel:
    def init(self):
        pass
    def predict(self, input_text: str = None, sys_prompt: str = '你的工作非常的出色！', messages: list = None,
                temperature: float = 0.3, top_p: float = 0.9, top_k: int = 0, min_p: float = 0,
                stream=False, format: str = 'text', json_format: str = '{}', tools: list = []) -> Union[dict, Generator]:
        """
        输入文本，生成文本，predict是ai为我取的名字
        Args:
            input_text: 输入文本
            sys_prompt: 系统prompt，默认为"你的工作非常的出色！"，就算是ai，让他们工作也需要鼓励！
            messages: 输入消息列表，格式为[{"role":"system","content":"系统提示"},{"role":"user","content":"用户输入"}]
            temperature: 控制生成文本的随机性，默认0.3
            top_p: 控制生成文本的多样性，默认0.9
            top_k: 控制生成文本的多样性，默认0
            min_p: 控制生成文本的多样性，默认0
            stream: 是否流式输出，默认False
            format: 输出格式，默认为text，可选json
            json_format: json格式，默认为{}
        """
        raise NotImplementedError("请使用子类实现predict方法")
    def chat(self, temperature=0.3):
        """
        聊天模式，输入文本，生成文本，用于控制台调试
        Args:
            temperature: 控制生成文本的随机性，默认0.3
        """
        raise NotImplementedError("请使用子类实现chat方法")
        

class llama(LocalModel):
    def __init__(self,
                 path:str=None,
                 device:str='gpu',
                 context_length:int=512,
                 GPU_n:int=-1,
                 verbose:bool=False
                 ):
        """
        初始化tina类
        Args:
            path: 模型路径
            device: cpu或gpu
            context_length: 最大上下文长度，默认为512
            GPU_n: 指定需要负载到GPU的模型层数，-1表示全部层负载到GPU的（不清楚模型内部实现不要动，在使用GPU是默认为-1）
            verbose: 是否打印日志，默认不打印
        """
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("请安装llama-cpp-python库！")
        self.context_length = context_length
        self._call = "LOCAL"
        
        # 防止出现设备参数错误
        if os.path.exists(path):
            if not os.path.isfile(path):
                raise ValueError("path(模型路径)必须是一个文件！")
        else:
            raise ValueError("path(模型路径)不存在！")
        device_dict = {
            'cpu': 'cpu',
            'gpu': 'gpu',
            'CPU': 'cpu',
            'GPU': 'gpu',
            'cuda': 'gpu',
            'CUDA': 'gpu'
        }
        if device not in device_dict:
            raise ValueError("device(设备)只能为cpu或gpu，对应参数为'cpu'或'gpu'")
        if device == 'cpu': # cpu模式
            self.model = Llama(path,verbose=verbose,n_ctx=context_length)
        else: # gpu模式
            self.model = Llama(path,n_gpu_layers=GPU_n,n_ctx=context_length,verbose=verbose)

    def predict(self,
                input_text:str = None,
                sys_prompt:str='你的工作非常的出色！',
                messages:list = None,
                temperature:float=0.3,
                top_p:float = 0.9,
                top_k:int = 0,
                min_p:float = 0,
                stream =False,
                format:str='text',
                json_format:str='{}',
                tools:list=[]
                ) -> Union[dict,Generator]:
        """
        输入文本，生成文本，predict是ai为我取的名字
        Args:
            input_text: 输入文本
            sys_prompt: 系统prompt，默认为"你的工作非常的出色！"，就算是ai，让他们工作也需要鼓励！
            messages: 输入消息列表，格式为[{"role":"system","content":"系统提示"},{"role":"user","content":"用户输入"}]
            temperature: 控制生成文本的随机性，默认0.3
            top_p: 控制生成文本的多样性，默认0.9
            top_k: 控制生成文本的多样性，默认0
            min_p: 控制生成文本的多样性，默认0
            stream: 是否流式输出，默认False
            format: 输出格式，默认为text，可选json
            json_format: json格式，默认为{}
        """
        format_dict = {
            'text': 'text',
            'json': 'json_object'
        }
        
        if format not in format_dict:
            raise ValueError("format(输出格式)只能为两种，一种为text，另一种为json，对应参数为'text'和'json'")
        if format == 'text' and json_format!= '{}':
            raise ValueError("json_format参数只对json格式有效！")
        if format == 'json' and json_format == '{}':
            raise ValueError("指定参数为json格式时，json_format参数不能为空！")
        
        format = format_dict[format]

        if messages != None and input_text == None:
            if json_format != '{}':
                messages.append({"role":"system","content":f"请按照{json_format}格式输出消息！"})
            return self.completion(
                                   messages = messages,
                                   temperature = temperature,
                                   top_p = top_p,
                                   top_k = top_k,
                                   min_p = min_p,
                                   stream = stream,
                                   tools=tools
                                   )
        elif messages != None and input_text != None:
            raise ValueError("messages参数不能与input_text或sys_prompt参数同时使用！")
        else:
            return self.completion(input_text = input_text,
                                   sys_prompt = sys_prompt, 
                                   temperature = temperature,
                                   top_p = top_p,
                                   top_k = top_k,
                                   min_p = min_p,
                                   stream = stream,
                                   tools=tools)

    def completion(self, 
                   messages = None,
                   input_text = "",
                   sys_prompt = "", 
                   temperature = 0.3, 
                   top_p= 0.9, 
                   top_k= 0, 
                   min_p= 0, 
                   format = 'text',
                   stream=False,
                   tools=[]
                   )-> Union[dict,Generator]:
        """
        封装了llama-cpp-python的create_chat_completion方法
        Args:
            input_text: 输入文本
            sys_prompt: 系统prompt
            temperature: 控制生成文本的随机性，默认0.3
            top_p: 控制生成文本的多样性
            top_k: 控制生成文本的多样性
            min_p: 控制生成文本的多样性
            stream: 是否流式输出
            tools: 工具列表
        Returns:
            输出文本
        """
        if messages is not None:
            completions = self.model.create_chat_completion(
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                response_format={"type": format},
                stream=stream,
                tools=tools                
            )
        else:
            completions=self.model.create_chat_completion(
                messages=[
                    {"role":"system","content":"你是一个中文大语言模型助手"},
                    {"role":"system","content":sys_prompt},
                    {"role":"user","content":input_text}
                ],
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                response_format={"type": format},
                stream=stream,
                tools=tools
            )

        if not stream:
            return completions['choices'][0]['message']
        else:
            return completions
            


 
    def chat(self,temperature=0.3):
        """
        聊天模式，输入文本，生成文本，用于控制台调试
            Args:
                temperature: 控制生成文本的随机性，默认0.3
        """
        print("正在使用命令行测试大模型\n\n")
        messages = []
        while True:
            input_text = input("\n>>> user：")
            if input_text == "#exit":
                print("结束聊天\n\n")
                break
            messages.append({"role":"user","content":input_text})
            result = self.predict(
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            
            message = self.stream(result)
            messages.append({"role":"assistant","content":message})

            
    def stream(self, completions):
        """
        自己写的一个流式输出方法
            Args:
                completions: 生成的文本
        """
        message = ''
        for chunk in completions:
            delta = chunk["choices"][0]["delta"]
            if 'role' in delta:
                print(f">>> {delta['role']}:", end='', flush=True)
            elif 'content' in delta:
                message += delta['content']
                print(delta['content'], end='', flush=True)
        return message
                
    
if __name__ == '__main__':
    llm = llama(
        path="c:/model/qwen2.5-3b-instruct-q4_k_m.gguf",
        context_length=2024,
    )
    llm.chat()