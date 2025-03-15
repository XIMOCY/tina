# 如何安装tina
## 使用wheel文件
目前没有放在PyPi上，想要安装请在发行版里面下载对应的wheel，然后发在想要安装的环境中，输入下面的指令
```bash
pip install tina[下载的完整的名字]
```
## 源代码
tina需要以下依赖：
```
diskcache==5.6.3
faiss-cpu==1.9.0.post1
Jinja2==3.1.5
lxml==5.3.0
MarkupSafe==3.0.2
numpy==2.2.1
packaging==24.2
PyPDF2==3.0.1
python-docx==1.1.2
如果使用API方式使用大模型
httpx
如果使用本地方式
llama-cpp-python
```
```bash
cd [源代码文件夹]
pip install -r requirements.txt
```
如果你需要本地使用大模型
```bash
pip install llama-cpp-python
```
# tina是什么?
tina是一个简单的基于大模型的工具调用智能体库，作为我在大二时候一个Python与大模型应用的练习项目，有部分代码是AI参与，我来修改完成的，代码目前的质量不高，可以骂轻点么，维护期长请原谅，目前还要读书，，，

一开始是自己想实现一个本地的知识库，后面发现大模型原来可以调用工具，，，

`注意：tina只包含了少量基本工具和对应的RAG查询工具，不包括其他工具，只是说，我可以让你方便的给大模型部署工具，你更多需要考虑工具怎么实现`

比如你写了一个函数，使用Tools类的方法就可以将工具信息提交之后，设置一个智能体就可以使用了，具体请看下面的吧

她包含以下内容：

### 1.简单的调用大模型
只需要实例化一个大模型对象，即可通过设定方法的参数即可；
### 2.记忆机制
内部通过记忆分类和重要性评分来对你和大模型的所有交流进行记忆，具有短期记忆和长期记忆
### 3.工具调用机制
你只需要写好工具的Python代码，并在注册工具的时候写好源文件路径，大模型就可以调用；
### 4.简单的RAG实现
可以对PDF，doxc，md和TXT等多种文本进行读取，同时对文本进行简单的清洗，分段和向量化；
### 5.设定Agent
设定一个工具调用的智能体，同时包括记忆，只需要将上面的大模型，工具和一个提示词对象实例化，通过参数设定实例化agent即可，调用和大模型一样简单
### 6.模块化设计
这意味着以上的功能你都可以拆开来用，不一定是智能体，还可以是类似下面这样的工作流：\
RAG->LLM->LLM...

她也可以叫 llama-tool-call-agent，在一开始，她是一个本地使用llama.cpp部署模型和RAG的小工具

# 一.从一个tina开始接触
tina中的Tina是一个在控制台实现的Agent,用到了tina里面的所有功能（可能？）
```python
from tina import Tina
from tina.LLM.llama import llama
#Tina需要一个LLM来驱动
#本地模型如下
llm = llama(
    path="[模型路径]",
    context_length=10000#根据你的模型来
)
#API如下，这里拿Qwen做演示
llm = Qwen(
    api_key =""#或者设置环境变量
)
my_tina = Tina(
    path="[Tina会在运行的时候产生文件，选择一个文件夹路径来保存]",
    LLM = llm
)
#使用run来启动
my_tina.run()
```
当你成功启动后，可以看到下面这样的页面
```console
(・∀・)  tina by QiQi in 🌟 XIMO


😊 欢迎使用tina，你可以输入#help来查看帮助
🤔 退出对话："#exit"
📤 文件上传："#file"

😀 当出现"tina正在记忆信息时..."请不要打断


( • ̀ω•́ ) >>>User:
```
Tina是利用了tina库的基础功能来构建的一个软件，基于Python\
她的功能有：\
1.**记忆**：你和她之间的重要交流会被记忆，你的信息，你的指令她也会记得\
2.**工具调用**：\
在实例化my_tina时指定Tina的tools参数，tools是一个列表，符合工具调用的JSON \
3.**操作计算机和RAG**\
本质也是工具调用，但是我给你们提供了便捷的方法，在Tina中指定isSystemTool为True和isRAG为True，
就可以使用tina自带的系统工具和RAG接口，由大模型自己调用\
RAG功能需要向量化模型，参考后面的RAG与向量化
# 我的实现
你可以参考一下我的用法
```python
#wcrtools在后面
from tina import Tina
from tina.LLM.Qwen import Qwen
tools=[
    {
        "name":"outputToMarkdown",
        "description":"使用该工具可以将输出导出到md文件中",
        "required_parameters":["name","content"],
        "parameters":{
            "name":{"type":"str","description":"文件名，不需要带后缀名"},
            "content":{"type":"str","description":"文件内容"}
        },
        "path":"D:/development/project/TCG/outputToMarkdown.py"
    },
    {
        "name":"smile",
        "description":"如果你感觉开心的话调用它可以微笑哦",
        "required_parameters":[],
        "parameters":{},
        "path":"D:/development/project/TCG/action.py"
    },
    {
        "name":"angry",
        "description":"如果你感觉不开心可以生气一下",
        "required_parameters":[],
        "parameters":{},
        "path":"D:/development/project/TCG/action.py"
    },
    {
        "name":"sad",
        "description":"如果你感觉很难过可以哭一会儿",
        "required_parameters":[],
        "parameters":{},
        "path":"D:/development/project/TCG/action.py"
    },
    {
        "name":"shy",
        "description":"如果你感觉害羞会脸红",
        "required_parameters":[],
        "parameters":{},
        "path":"D:/development/project/TCG/action.py"
    }
]
llm = Qwen()
my_tina = Tina(path='d:/',
                LLM=llm,
                embeding_model="C:/model/m3e_base.gguf",
                tools=tools,
                toolsLib=r"D:\development\project\TCG\wcrtools.py",
                isSystem=True,
                isRAG=True,
                is_tool_call_permission=False
)
my_tina.run()
```
wcrtools 不一定好用哦
```python
import webbrowser
import requests
from bs4 import BeautifulSoup
import requests
import os
import subprocess
import threading

def writeCode(filename, code):
    """
    将代码写入文件并返回文件路径，如果文件已存在，则覆盖原文件
    Args:
        filename: 文件名
        code: 代码内容
    """
    path = os.path.join(os.getcwd(), filename)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(code)
    return path

def readCode(filename):
    """
    读取文件内容,仅限于当前目录下的文件
    Args:
        filename: 文件名
    """
    path = os.path.join(os.getcwd(), filename)
    with open(filename, 'r') as f:
        code = f.read()
    return code

def deleteCode(filename):
    """
    删除文件
    Args:
        filename: 文件名
    """
    path = os.path.join(os.getcwd(), filename)
    os.remove(path)
    return path


def runCode(filename):
    """
    运行代码，并在命令行中显示输出结果,仅限于当前目录下的文件
    Args:
        filename: 文件名
    """
    path = os.path.join(os.getcwd(), filename)
    try:
        args = ['python', path]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if out:
            print(out.decode('utf-8'))
            return out.decode('utf-8')
        if err:
            print(err.decode('utf-8'))
            return err.decode('utf-8')
    except Exception as e:
        print(str(e))
        return str(e)
def runCodeNotOpenTerminal(code):
    """
    运行代码，并在命令行中显示输出结果,不打开新的命令行窗口
    Args:
        code: 代码内容
    """
    try:
        eval_thread = threading.Thread(target=eval, args=(code,))
        eval_thread.start()
        result = eval_thread.join()
        return result
    except Exception as e:
        return str(e)

def openBzhan():
    """
    帮助用户快速打开Bilibili网页来摸鱼
    """
    webbrowser.open("https://www.bilibili.com/")
    print("Bilibili opened")
    return "Bilibili opened!"

def openBrowserSearch(text):
    """
    帮助用户快速在浏览器中搜索指定内容，不会打开浏览器，搜索结果用户看不到，请你总结或者挑选合适的结果，使用openURL()函数打开网址
    Args:
        text: 搜索内容
    Returns:
        输出搜索结果
    """
    # 发送搜索请求
    search_url = f"https://www.bing.com/search?q={text}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(search_url, headers=headers)
    
    # 解析搜索结果
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []

    # 提取标题和链接 (根据Bing实际结构调整选择器)
    for item in soup.select('li.b_algo h2 a'):
        title = item.get_text()
        url = item.get('href')
        content = getURLContent(url)
        if content == -1:
            results.append(f"{title}\n{url}\n请求失败")
        elif content == -2:
            results.append(f"{title}\n{url}\n解析失败")
        else:
            results.append(f"{title}\n{url}\n{content}")
    
    output = "帮你搜索了：\n" + "\n\n".join(results)
    return output
def openURL(url):
    """
    帮助用户快速打开指定网址
    Args:
        url: 网址
    Returns:
        输出打开结果
    """
    webbrowser.open(url)
    print(f"{url} opened")
    return f"{url} opened!"


def getURLContent(url):
    """
    根据URL获取网页主要内容
    Args:
        url: 网址
    Returns:
        网页主要内容, 若失败返回-1或-2
    """
    try:
        # 设置请求头模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 发送HTTP请求
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查请求状态
        
        # 解析HTML内容
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尝试多种常见内容标签提取
        for tag in ['article', 'div.main-content', 'section', 'div.content']:
            elements = soup.select(tag)
            if elements:
                return "\n\n".join([e.get_text(strip=True) for e in elements])
        
        # 备用方案：提取段落组合
        paragraphs = soup.find_all('p')
        if paragraphs:
            return "\n".join([p.get_text(strip=True) for p in paragraphs])
            
        return "未找到明确的内容区域"
        
    except requests.exceptions.RequestException:
        return -1  # 网络请求失败，返回错误码-1
    except Exception:
        return -2  # 其他处理异常，返回错误码-2






```
# 二.实例化一个大模型
模型可以使用本地或者Api的形式的调用，本地使用llama.cpp的GGUF格式的模型，Api使用openai格式兼容的模型
## 1.本地的调用：
在tina.LLM.llama查看\
本质是将llama-cpp-python封装成我需要的格式
看看下面的示例：
```python
from tina.LLM.llama import llama
#为了不和Llama冲突，首字母没有大写
llm = llama(
    path:str=#"gguf模型路径",
    context_length:int=#模型的最大上下文,
    device:str = #"设备，有CPU和GPU",
    GPU_n:int = #指定需要负载到GPU的模型层数，-1表示全部层负载到GPU的（不清楚模型内部实现不要动，在使用GPU是默认为-1）,
    verbose:bool=#打印llama.cpp读取模型时的日志
)
```
使用上面的代码即可初始化你的本地模型，只需要将GGUF模型路径赋值给path变量。
### llm.predict()方法使用
```python
llm.predict()#使用该方法可以让大模型产生输出，参数可以通过调用查看
#predict()中input_text和messages参数是冲突的，后者是为了方便自己构造消息传递给大模型
```
##### 一般用法如下
```python
#result返回一个字典
result = llm.predict(
    input_text="你好？",
    #sys_prompt = "你是一个人工智能助手",
)
print(result)
#输出：{"role":"assi",""content":"你好，我是。。。"}，可以通过result["content"]获得内容
```
##### 流式输出如下
```python
#指定stream为True，这个时候result为生成器
result = llm.predict(
    input_text="你好？",
    #sys_prompt = "你是一个人工智能助手",
    stream=True
)
for chunk in result:
    print(chunk,end="")
#输出：你好.....
```
## 2.api调用
以下用Qwen来演示
```python
from tina.LLM.Qwen import Qwen
qwen = Qwen(
    #api_key = "你的api_key",
)
#我们都不怎么推荐你直接将api_key写在代码里，容易泄漏
```
当你实例化时，Qwen内会从环境变量里面通过QWEN_API_KEY来获取你的api key
剩下的方法和本地使用模型的一致\
目前有Qwen，DeepSeek
# 三.工具注册
## 先实例化Tools类
```python 
from tina.core.tools import Tools
tools = Tools()
```
## 单个工具注册
```python
#格式如下
tools.register(
    name="工具的名字",
    description="工具功能的描述",
    required_parameters=["必须要填的参数名称",...],
    parameters={"字典类型"},
    path="工具代码的路径"
)
# parameters (dict): 参数的详细信息，所有的参数都要有类型和描述
#     格式：
#         {
#         "参数名": {
#                 "type": "参数类型",
#                 "description": "参数描述"
#             }
#         }

#示例
tools.register(
    name="query",
    description = "在文档里面查询",
    required_parameters=["query_text"],
    parameters={
        "query_text":{
            "type":"str",
            "description":"查询的信息"
        },
        "n":{
            "type":"int",
            "description":"返回的结果数"
        }
    },
    path="d:/test/query.py"#路径要自己传递，不要用我的哦
)
```
## 多个工具注册
```python
SystemTools = [
    {
        "name": "getTime",
        "description": "获取当前时间",
        "required_parameters": [],
        "parameters": {},
        "path": "d:/test/systemTools.py"
    },
    {
        "name": "shotdownSystem",
        "description": "该工具会关闭计算机",
        "required_parameters": [],
        "parameters": {},
        "path": "d:/test/systemTools.py"
    },
    {
        "name":"getSoftwareList",
        "description":"获取系统软件列表",
        "required_parameters":[],
        "parameters":{},
        "path":"d:/test/systemTools.py"
    },
    {
        "name":"getSystemInfo",
        "description":"获取系统信息",
        "required_parameters":[],
        "parameters":{},
        "path":"d:/test/systemTools.py"
    }
]

tools.multiregister(SystemTools)
```
从py文件载入工具
```python
from tina.core.tools import Tools
tools = Tools.loadToolsFromPyFile([Py文件路径])#这是一个静态方法，返回一个Tools实例
```

工具类负责工具的管理，它有方法来获取工具的名字，路径，和参数验证，但是一般用不到，这些方法会在智能体和智能体执行器里面被使用
# 四.设置一个智能体
tina里面的智能体和大模型的区别在于
智能体拥有记忆和工具，同时内部会执行工具获取结果，而大模型是一个简单的输入输出使用。\
**Agent不是自动运行的，你需要自己设计事件来使用Agent的方法**
```python
#调用文件夹管理器，这是为了不让tina产生的文件不乱跑
from tina.core.manage import TinaFolderManager

TinaFolderManager.init(“你想把文件放在哪里？”)

from tina.LLM.llama import llama
from tina.core.tools import Tools
from tina.core.prompt import Prompt

from tina.Agent import Agent

#也可以使用api方式调用
llm = llama(
    path:str=#"gguf模型路径",
    context_length:int=#模型的最大上下文,
    device:str = #"设备，有CPU和GPU",
    GPU_n:int = #指定需要负载到GPU的模型层数，-1表示全部层负载到GPU的（不清楚模型内部实现不要动，在使用GPU是默认为-1）,
    verbose:bool=#打印llama.cpp读取模型时的日志
)
tools = Tools()
prompt = Prompt()
#将上面的示例以参数的方式传递给Agent
agent = Agent(
    LLM = llm,
    tools = tools,
    prompt = prompt
)
```
上面就是简单的实例化一个智能体，目前它只有记忆，工具需要你自己设计，或者在tools实例化时指定参数
```python
tools = Tools(
    isSystemTool=True,#启用系统工具
    isRAG=True,#启用RAG的接口
)
```
虽然我叫作智能体，但是目前还是和RL中的智能体有区别，目前她还无法感知环境，不过我已经在environment.py里面做好了多智能体和环境感知的准备
## Agent的方法
### predict()方法
实际上，你可以像使用LLM一样使用Agent.\
最基础获取输出，和LLM一样的方法还是predict()方法
```python
...
result = agent.predict(input_text="你好？")
#agent.predict()默认流式输出
for chunk in result:
    print(chunk,end="")
...
```
```python
predict(
    input_text:str,#输入文本
    temperature:float,
    top_p:float,
    min_p:float,
    stream:bool=False,#是否流式输出
)
```
虽然和LLM的方法一致，但是不一样的是，当存在工具并且LLM调用它时，Agent会执行完工具后,将结果提交给LLM，再次递归调用predict()产生输出。
### readFile()方法
读取文件并提交到LLM的消息列表
```python
agent.readFile(path="文件路径")
```
Agent会在内部评估文件的大小，如果超过上下文，则会根据LLM的最大上下文的一半读取文件
### remember()方法
记忆信息
```python
agent.remember()#无参调用，会主动记忆消息，然后存在文件里面，下次启动的时候还会记得之前的内容
agent.remember(message="你好，我是tina")#手动记忆信息，当有你需要手动记忆的东西的时候，可以调用该方法
``` 
### forget()方法
遗忘信息
```python
agent.forget()#无参调用，会直接清空当前对话的消息列表
agent.forget(importance=1)#会遗忘importance小于1的记忆，importance的范围为1-5
```
# 五.RAG与文档向量化
RAG是检索信息增强技术，使用该功能可以在你的文档中进行搜索相关的文档片段
## 文档向量化-docToVec()函数
docToVec()函数可以将文档转换为向量，并保存为索引文件和分段文件，方便后续的检索。
```python
from tina.core.manage import TinaFolderManager
#因为文档向量化后会产生一份索引文件和分段文件，所以需要指定一个文件夹路径，不然就会乱跑
TinaFolderManager.init(“你想把文件放在哪里？”)
from tina.RAG.Embedding.docToVec import docToVec
#docToVec只是一个函数
docToVec(
    file_path="文档文件夹的路径",
    model_path="向量模型路径",
    dimesion=768,#向量维度
    n = 500,#分段的每段字数
    isCopyToTinaFolder=True,#是否把原文件复制到tina的文件夹
)
```
## 在文档里搜索-query()函数
query()函数可以检索文档向量化后的索引文件，并返回相关的文档片段。
```python
#在之前使用过docToVec()之后才可以使用
...
from tina.RAG.query.query import query
result = query(
    query_text="你好，我是tina",
    n=5,#返回的结果数
)
```
## 使用向量模型-Embedding()类
Embedding()类可以创建一个向量模型对象
```python
from tina.RAG.Embedding.embedding import Embedding
embedding = Embedding(
    model_path="向量模型路径"
)
```
该类的使用，暂时不过多展示，因为这方面的代码我写的还不够完善😳，后续会逐步完善。
