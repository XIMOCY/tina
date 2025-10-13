# 如何安装tina

```bash
pip install tina-python
```
如果需要使用MCP服务(MCP即模型上下文协议)
```bash
pip install tina-python[mcp]
```
## 源代码
tina需要以下依赖：
```
最基础的依赖：
httpx
dotenv
使用MCP服务：
mcp-python
```
```bash
cd [源代码文件夹]
pip install -r requirements.txt
```
如果你需要本地使用大模型,目前不建议通过下面的使用本地大模型
```bash
pip install llama-cpp-python
```
- [介绍](#tina是什么)
- [快速开始](#一从一个tina开始接触)
# tina是什么?
tina是一个简单的基于大模型的工具调用智能体库，

一开始使用的OpenAI SDK，后面想要扩展功能的时候使用了LangChain 发现我想要的功能介于这两种之间
有的时候也许我只想要调用一个大模型获得一个输出，用不着其他的很多功能，而且使用方式不是很符合我的直觉，所以我自己用httpx自己封装了一个简单的库

你可以用它来做一个快速的大模型应用的原型验证，当然她只是我一个大学的兴趣使然开发的一个产物，做我练习python的作品，如果追求稳定请去使用langchain等成熟的框架哦
```python
#简单的调用大模型来翻译一个句子
from tina.llm import BaseAPI

llm = BaseAPI(
    api_key="填写你自己的api",
    base_url="你选择的API提供商",
    model="模型名称"
)
result = llm.predict(
    input_text = "帮我翻译一下这句话：Hello tina",
    sys_prompt = "你是一位专业的翻译家...",
)
print(result)
```
```python
#尝试一下大模型调用工具的能力
from tina import Agent,Tools
from tina.llm import BaseAPI
tools = Tools()
llm = BaseAPI(
    api_key="填写你自己的api",
    base_url="你选择的API提供商",
    model="模型名称"
)
agent = Agent(
    LLM = llm,
    tools = tools,
)

result = agent.predict(
    input_text = "现在几点了",
)

for i in result:
    print(i,end="")

```
```python
# 尝试一下MCP
# 魔塔的MCP广场 https://www.modelscope.cn/mcp
from tina import Agent,Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

bing_search_mcp = {
  "mcpServers": {
    "fetch": {
      "type": "sse",
      "url": "https://mcp.api-inference.modelscope.cn/sse/xxxxxxxxxxxx"
    }
  }
}
# 实例化一个MCP服务器并且添加一个服务
MCP = MCPClient()
MCP.addServer(
    server_id="bing_search",#这个是自己取的id
    config=bing_search_mcp["mcpServers"]["fetch"]
)

llm = BaseAPI(
    api_key="填写你自己的api",
    base_url="你选择的API提供商",
    model="模型名称"
)
tools = Tools()

agent = Agent(
    llm=llm,
    tools=tools,
    mcp=MCP
)# MCP的工具会被大模型主动的调用
result = agent.predict(
    input_text= "查询一下苹果公司",
)
for i in result:
    print(i,end="")
```

`注意：tina只包含了少量基本工具，不包括其他工具，只是说，我可以让你方便的给大模型部署工具来玩，你更多需要考虑工具怎么实现`

比如你写了一个函数，使用Tools类的方法就可以将工具信息提交之后，设置一个智能体就可以使用了，具体请看下面的吧

她包含以下内容：

### 1.简单的调用大模型
只需要实例化一个大模型对象，即可通过设定方法的参数即可；
### 2.工具调用机制
你只需要写好工具的Python代码，然后通过Tools的方法注册工具，自动运行和解析
### 3.设定Agent
设定一个工具调用的智能体，只需要将上面的大模型，工具和一个提示词对象实例化，通过参数设定实例化agent即可，调用和大模型一样简单
### 4.模块化设计
这意味着以上的功能你都可以拆开来用，选择你喜欢的部分进行


# 一.从一个tina开始接触
tina中的Tina是一个在控制台实现的Agent,作为tina的AI说明书，她默认携带了完整的readme，你可以直接问她关于tina框架怎么使用的事
```python
from tina import Tina
my_tina = Tina()
#使用run来启动
my_tina.run()
```
当你成功启动后，可以看到下面这样的页面
```console
(´▽`ʃ♡ƪ)"  tina by QiQi in 🌟 XIMO


😊 欢迎使用tina，你可以输入#help来查看帮助
🤔 退出对话："#exit"


( • ̀ω•́ ) >>>User:
```
她可以回答关于tina框架的问题，同时也是一个比较全能的智能体

# 二.实例化一个大模型
模型可以使用本地或者Api的形式的调用，本地使用llama.cpp的GGUF格式的模型，Api使用openai格式兼容的模型
## 1.本地的调用：
在tina.LLM.llama查看
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
输出解释：
```
大模型的输出会被解析为下面的字典格式
下面是最基本的输出，这两个键会一直存在，不管有没有值
{
    "role":"assistant",#字符串
    "content":"",#字符串
}
下面是只有获取到相关的输出才会返回的键
{
    "reasoning_content":""#如果使用推理模型，推理的内容会在这里，字符串
    "tool_name":#出现了工具名称才会返回。字符串
    "tool_calls":#出现了完整的工具调用才会出现，字典
}
tool_calls的格式如下
{
    "index": index,
    "function": {"arguments": ""},
    "type": "",
    "id": ""
}
```
API需要的参数，比如api_key base_url和model_name，在开发环境下推荐使用.env文件

下面是个.env文件的示例，实例化的大模型类会默认读取当前终端目录下的`tina.env`文件：
```
LLM_API_KEY=""
BASE_URL="" //注意，我不会默认添加/chat/completions 如果查询到是openai格式的，请手动添加/chat/completions
MODEL_NAME = ""
MAX_INPUT = 8000 #最大的输入字符数
```
除了直接使用BaseAPI，还可以使用一些我设置好的大模型类比如Qwen，继承自BaseAPI，它默认设置了的阿里云的Base_url和qwen-plus

以下用Qwen来演示
```python
from tina.llm import Qwen
qwen = Qwen(
    #api_key = "你的api_key",
    #env_path = ""#如果你的.env路径不在当前当前终端目录下，可以自行设计
)
```

# 三.工具注册
目前的工具仅支持py代码，可以通过mcp来扩展工具或者自己写工具执行器来完成任务
## 先实例化Tools类
```python 
from tina import Tools
tools = Tools()
```
## 了解Google风格的注释
在后面的工具注册中你会发现自己不需要填写参数类型和描述，  
这是因为我会解析你的注释，并自动生成参数类型和描述  
如果还需要再一次填写参数类型和描述的话很麻烦，我主张注释即描述，这样可以一次写好  
下面的是Google风格的注释
```python
def query(text:str) -> str:
    """
    查询文档
    Args:
        text: str 查询的文本
    """
    return query(text)
```
## 单个工具注册
```python
#格式如下
tools.registerTool(
    name="工具的名字",
    description="工具功能的描述"
)


#示例
tools.registerTool(
    name="query",
    description = "在文档里面查询"
)

```
## 使用装饰器（新增的方法）
```python
@tools.register()
def add(a,b):
    """
    两个数字相加
    Args:
        a:int 数字a
        b:int 数字b
    """
    return a+b
@tools.register(post_handler=None) #可以设置工具结果的解析函数
```
## 注册不带功能实现的工具
```python
tools.registerNotWithFunction(
    name="工具名字",
    description="工具功能描述",
    required_parameters=[],
    parameters={}
)


# name (str): 函数的名称，一定要正确
# description (str): 函数的描述，可以详细描述函数的功能
# required_parameters (list): 一定要有输入的参数列表
# parameters (dict): 参数的详细信息，所有的参数都要有类型和描述
# 格式：
# {
#     "参数名": {
#         "type": "参数类型",
#         "description": "参数描述"
#             }
# }
```

工具类负责工具的管理，它有方法来获取工具的名字，路径，和参数验证，但是一般用不到，这些方法会在智能体和智能体执行器里面被使用
# 四.设置一个智能体
tina里面的智能体和大模型的区别在于
智能体拥有工具和外界交互，同时内部会执行工具获取结果，而大模型是一个简单的输入输出使用。
**Agent不是自动运行的，你需要自己设计事件来使用Agent的方法**
```python
from tina import Agent,Tools
from tina.llm import BaseAPI()
llm = BaseAPI()
tools = Tools()
agent = Agent(
    LLM =llm,
    tools = tools
)# 也可以设置参数isExecute=False 这样智能体不会执行工具，而只是解析工具调用然后返回，这样用户可以设计自己的工具执行器
```
上面就是简单的实例化一个智能体，目前它只有记忆，工具需要你自己设计，或者在tools实例化时指定参数来使用一些我内置的工具
```python
tools = Tools(
     useSystemTools=True,#一些自带的系统工具
     useTerminal=True,#可以向终端发送消息
     setGoal=True#Agent可以自己设置目标
)
```
## Agent的方法
### predict()方法
实际上，你可以像使用LLM一样使用Agent.  
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


