"""
编写者：王出日
日期：2024，12，13
版本？

将llama-cpp-python封装为需要的接口
llama.cpp Github地址：https://github.com/ggerganov/llama.cpphttps://github.com/ggerganov/llama.cpp
llama-cpp-python Github地址：https://github.com/abetlen/llama-cpp-python
tina类基于llama-cpp-python实现
使用更简单的语言描述让开发者更快的上手
tina是基于开源的qwen2.5-7b模型微调而来
qwen模型网址：https://github.com/QwenLM/Qwenhttps://github.com/QwenLM/Qwen
"""
import os
from typing import Union,Generator



class llama:
    def __init__(self,
                 path:str=os.path.join(os.path.dirname(__file__),'model','qwen2.5-7b-instruct-q4_k_m.gguf'),
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
        from llama_cpp import Llama
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
        messages = ''
        print(self.predict("用户开始聊天，问好一句吧！")['content'],temperature)
        while True:
            input_text = input("\nuser:")
            messages += "用户输入:"+input_text + '\n'
            if input_text == "#exit":
                break
            massage = self.stream(
                self.predict(input_text,
                sys_prompt=f"之前的你与用户交流的记忆：{messages}\n",
                stream=True,
                temperature=temperature)
                )
            messages += "模型输出:"+massage + '\n'
            if(len(messages)>100000):
                messages = messages[-100000:]
            
    def stream(self, completions):
        """
        自己写的一个流式输出方法
            Args:
                completions: 生成的文本
        """
        messages = ''
        for chunk in completions:
            delta = chunk["choices"][0]["delta"]
            if 'role' in delta:
                messages += delta['role'] + ': '
                print(delta['role'], end=': ', flush=True)
            elif 'content' in delta:
                messages += delta['content']
                print(delta['content'], end='', flush=True)
        return messages
                
    # def parser(self, completions):
    #     """
    #     解析生成的文本
    #         Args:
    #             completions: 生成的文本
    #     """
    #     messages = ''
    #     for chunk in completions:
    #         delta = chunk["choices"][0]["delta"]
    #         if 'role' in delta:
    #             messages += delta['role'] + ': '
                
    #         elif 'content' in delta:
    #             messages += delta['content']
                
    #     return messages

        

if __name__ == '__main__':
    test_text = """
    柳夭在学校呆了一天，她一直在看书，我在想，我该怎么帮她。
张波在晚自习下课的时候，自然地靠在了我的旁边，他也和我一样装模做样的看着楼下的人群。
”我也想帮她，你说我们该怎么办？”
我诧异地看着他，他神秘地笑了笑。
“你看上去怎么好像什么都知道？”
我把事情告诉了他，他略有所思，我们安静了一会，他才问我，问题的关键是什么？
她的妈妈回来了，她的家人供她读书，不再提起嫁人的事...
他说，这些是关键吗？这是解决问题的方法。
“心冇，你知道为什么你会感觉自己做不到吗？因为你只是一个普通的高中生，你还没有插足别人家庭，帮别人家庭做主的能力，方法有很多，你却选择了一个自己最不可能做的到的。”
“我们要让她感受到关爱，我们可以有很多方法，你不是会画画吗？”
“我可以送一副画给她。”
“重要的不是画，而是你有把她当作朋友的那一份心。”
张波凝视着我，我好像知道我该怎么办了。
“我需要你的帮助，张波。”
上了这么久的学，好像我第一次发自内心的笑了。
张波的意思是，让她感觉自己又被真的在意，不是因为她是一个女生，一个生育工具。
我和他说，希望张好可以知道这件事，让她们女生寝室的多关注她一下。实际上，那天晚自习下课，老班把张好和她们寝室的女生悄悄地叫到办公室了。
我在办公室门口忐忑地走着，思考了许久之后，我鼓起勇气朝着被女生围住地老班走去。
10双眼睛盯着我，都是一副我是来干什么地看着我。
“你有什么事吗？”老班温柔地说。
我将柳夭的故事说了出来，她们先是怀疑，然后说，为什么她不直接和她们说，而是要直接出去哭呢，她为什么会觉得她们不会理解她呢？
“因为你们不是她，你们过的生活和她的不一样。”
“那你理解吗？”她们有些咄咄逼人。
“好了，同学们，心冇也是好心，他没有恶意”，老班停止了这场争议，她们安静了下来，一个个偷偷的扯了扯各自的衣袖。
“老班，我们知道怎么做了。”张好终于说话了，而且看了看我，女生们一连串的出去了，我从窗户外看向我们班，我能看见她趴在墙上看着这里。
老班微笑的看着我。
“她家确实有点特殊啊”，老班说，“虽然在之前很常见，没想到我又遇见了。”
“老班，为什么要这么说?”我是第一次和老班开口吧，开口还是不自然，或者对老师有种权威的害怕，老班的笑容很和谐，甚至有种不靠谱的感觉。
“她爷爷奶奶就他爸一个儿子，其他都是女儿，这样重男轻女挺正常，谁希望自家断种呢？”
“老班...我觉得不应该这么想...”
老班拍了拍我的肩。
“在你们这一代，也许就不一样了。”
老班的眼睛眯上一条缝，让我也放松了不少。
“老班，她妈妈去哪里了？”
“不知道，我也在想办法联系她，不过我不知道。”
“老班，她现在没有人管她了。”
“谁说的，我没有这么说哦。”
老班还是笑着，不过我已经知道了老班的意思，老班是一个好人，我想的问题，实际上他也想过了。
“谢谢老班。”
我朝着老班笑了笑，就走了。
张波在走廊上看着我，柳夭已经不在走廊上了，他和我一起走进了教室，一张纸条在我的桌子上。
“今天晚上可以吗？”
“你们俩好像在约会啊。”张波双手交叉在头后面，我没有过这种想法。
“你在说什么啊？”我小声地回应他，写下一个“好”字，回头看向她，她低着头在看书了"""
    llm = tina(device='gpu',context_length=20480,verbose=False)
    output = llm.predict(
                input_text=test_text,
                sys_prompt="总结文本",
                temperature=0.3,
                top_p=0.9,
                top_k=0,
                min_p=0,
                stream=False,
                format='text',
            )
    print(output['content'])
    # response_format={
    #     "type": "json_object",
    # },