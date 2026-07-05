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

- [介绍](#tina是什么)
- [快速开始](#一从一个tina开始接触)
# tina是什么?
tina是一个简单的基于大模型的智能体库，

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
# 我们会提供一个默认的prompt来供你使用
system_prompt = "你是一个Agent，请灵活的使用工具来完成我的任务"
tools = Tools()
llm = BaseAPI(
    api_key="填写你自己的api",
    base_url="你选择的API提供商",
    model="模型名称"
)
agent = Agent(
    LLM = llm,
    tools = tools,
    system_prompt = system_prompt # 传递你的prompt
)

result = agent.predict(
    input_text = "现在几点了",
)

for i in result:
    print(i,end="")

```
```python
# 利用MCP来更好的扩展Agent的功能
# 魔塔的MCP广场 https://www.modelscope.cn/mcp
from tina import Agent,Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

# 实例化一个MCP服务器并且添加一个服务
mcp = MCPClient()
mcp.add_server(
    server_id="playwright", 
    config={
        "type":"stdio",
        "command":"npx",
        "args":["@playwright/mcp@latest"]
    }
)
system_prompt = "你是一个浏览器自动化助手"

llm = BaseAPI(
    api_key="填写你自己的api",
    base_url="你选择的API提供商",
    model="模型名称"
)
tools = Tools()

agent = Agent(
    llm=llm,
    tools=tools,
    mcp=MCP,
    system_prompt = system_prompt
)# MCP的工具会被大模型主动的调用
result = agent.predict(
    input_text= "导航去bing",
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
设定一个智能体，只需要将上面的大模型，工具实例化，通过参数设定实例化agent即可，和调用和大模型一样简单
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
## 1.本地模型使用
在0.5.0版本暂时移除了本地模型的使用，后期会通过llama.cpp进行本地模型调用
## 2.api调用
输出参数格式解释：
```
大模型的输出会被解析为下面的字典格式
下面是最基本的输出，这两个键会一直存在，不管有没有值
{
    "role":"assistant",#字符串
    "content":"",#字符串
}
下面是只有获取到相关的输出才会返回的键
{
    "reasoning_content":""#如果使用推理模型，推理的内容会在这里，str
    "tool_name":#出现了工具名称才会返回。str
    "tool_arguments":#出现了工具参数才会出现，str
    "tool_calls":#出现了完整的工具调用才会出现，list
}
tool_calls中每一项的格式如下
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

### predict() apredict()
predict()是同步方法  
apredict()是异步方法  
两者参数一致，只是调用方法不同
> 注意：使用同步的方法的时候，不可以注册异步的工具，但是apredict()方法可以同时注册同步工具和异步工具  
```python
from tina.llm import BaseAPI
llm = BaseAPI()

# 1. 单次对话，用于快速获得单次的大模型输出
# 非流式输出
result = llm.predict(
    input_text = "请帮我翻译这句话：Hello tina",
    sys_prompt = "你作为一个专业的翻译家",
    stream=False # 设置stream参数来获取非流式输出
)
# 通过"content"可以获取输出结果
print(result["content"])

# 流式输出
result = llm.predict(
    input_text = "请帮我翻译这句话：Hello tina",
    sys_prompt = "你作为一个专业的翻译家",
    stream=True 
)
# 返回的是生成器
for chunk in result:
    print(chunk["content"],end="")

# 2. 自己设置messages参数来设置对话上下文，实现多次对话
messages = [
    {"role": "system", "content": "你作为一个专业的翻译家"},
    {"role": "user", "content": "请帮我翻译这句话：Hello tina"}，
    {"role": "assistant", "content": "..."}，
    {"role": "user", "content": "请帮我翻译这句话：Hello anit"}，
]
result = llm.predict(
    input_text = "请帮我翻译这句话：Hello tina", # 这里使用input_text参数，会自动地帮你添加到messages中，等价于你自己append一个user消息
    messages = messages,
    stream=True
)
for chunk in result:
    print(chunk["content"],end="")
```

#### predict() 和 apredict() 方法详解

调用大语言模型执行预测任务，支持单次对话和多轮对话模式

此方法作为统一入口，根据stream参数自动调用对应的专用方法：
- stream=False: 调用 predict_no_stream()
- stream=True: 调用 predict_stream()

##### 参数说明

| 参数名 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| input_text | str, optional | 用户输入文本 | None |
| sys_prompt | str, optional | 系统提示词 | "你的工作非常的出色！" |
| messages | list, optional | 历史对话消息列表。格式为: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}] | None |
| temperature | float, optional | 生成文本的随机性参数 (0.0-1.0) | 1.0 |
| top_p | float, optional | 核采样参数 (0.0-1.0) | 0.9 |
| top_k | int, optional | Top-K采样参数，限制候选词汇数量。注意：不是所有模型都支持，不支持时会自动忽略 | None |
| min_p | float, optional | Min-P采样参数，设置最小概率阈值。注意：较新的采样方法，老模型可能不支持 | None |
| max_tokens | int, optional | 最大生成token数量 | None |
| presence_penalty | float, optional | 存在惩罚参数 (-2.0到2.0) | None |
| frequency_penalty | float, optional | 频率惩罚参数 (-2.0到2.0) | None |
| stream | bool, optional | 是否启用流式响应 | False |
| format | str, optional | 返回格式类型，"text"或"json" | "text" |
| json_format | str, optional | JSON格式模板 | 空字符串 |
| tools | list, optional | 工具调用列表。格式为: [{"name": "...", "description": "...", "parameters": {...}}] | None |
| timeout | int, optional | 请求超时时间(秒) | 180 |

##### 返回值

Union[dict, Generator[dict, None, None]]:
- 非流式模式返回字典格式：{"role": "assistant", "content": "...", "tool_calls": [...]}
- 流式模式返回生成器，逐块返回响应内容和/或工具调用信息

##### 异常处理

APIRequestFailed: 当API调用失败时抛出异常

##### 使用示例

###### 单次对话模式
```python
>>> predict(input_text="你好")
{"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
```

###### 多轮对话模式
```python
>>> messages = [{"role": "user", "content": "北京天气如何？"}]
>>> predict(messages=messages)
```
            
###### 流式响应
```python
>>> for chunk in predict(input_text="讲个故事", stream=True):
     print(chunk)
```
            
###### 使用高级采样参数
```python
>>> result = predict(input_text="创意写作", top_k=50, min_p=0.1, max_tokens=1000)
```


# 三.工具注册
工具的注册主要使用Tools来实现  
Tools是一个工具类，用于注册，管理和提供工具执行的上层api  
实例化的Tools我称为工具集  
建议开发者，实例化的工具集变量名称就是工具集的名称
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
## 单个工具注册：register_tool
```python
#格式如下
tools.register_tool(
    tool=工具函数,
    description="工具功能的描述"
)

#示例
async def query(text):
    """
    查询文档
    Args:
        text: str 搜索的文本
    """
    ...
    return result
# 同步和异步工具都可以注册
tools.register_tool(
    tool=query,
    description = "在文档里面查询"
)

```
## 使用装饰器（新增的方法）:@register()
```python
# 同步工具注册
@tools.register()
def add(a,b):
    """
    两个数字相加
    Args:
        a:int 数字a
        b:int 数字b
    """
    return a+b
# 异步工具注册
@tools.register()
async def query(text):
    """
    查询文档
    Args:
        text: str 搜索的文本
    """
    ...
    return result
```
## 注册不带功能实现的工具: register_no_function
```python
tools.register_no_function(
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
## 注销工具 unregister
从工具集中删除或者注销一个工具
```python
tools.unregister(tool_name)
```
## 添加工具集
你可以使用+ 和 += 来对工具集进行添加
```python
from tina.utils.system_tools import system_tools
from tina import Tools
tools = Tools()
tools += system_tools # 添加tina自带的系统工具包
# 也可以按照下面的格式
tools = tools + system_tools
```
## 执行工具 execute
只能执行有功能实现的工具
```python
from tina import Tools
tools = Tools()

@tools.register()
def hello(name: str):
    """
    描述
    Args:
        name (str): 名字
    """
    print("hello, %s" % name)
# 假设下面的是大模型返回的tool_calls
tool_calls = [
    {
        "index":0,
        "type": "function",
        "function": {
            "name": "hello"
            "arguments": "{\"name\":\"Tina\"}"
        }
        "id": "xxxxxxxxxxxxxxxxxxxx"
    }
]
# 直接传递tool_calls Tools会自己处理
tools.execute(
    tool_calls = tool_calls
)
```

# 四.设置一个Agent
tina里面的Agent和大模型的区别在于
Agent拥有工具和外界交互，同时内部会执行工具获取结果，而大模型是一个简单的输入输出使用。  
Agent会自动地维护messages和运行需要的状态  
**Agent不是自动运行的，你需要自己设计事件来使用Agent的方法**
```python
from tina import Agent,Tools
from tina.llm import BaseAPI
llm = BaseAPI()
tools = Tools()
system_prompt = "你是一个有用的Agent"
# Agent可以在只需要一个LLM和Tools的时候创建，这个时候系统会使用tina默认的prompt
agent = Agent(
    LLM =llm,
    tools = tools,
    system_prompt = system_prompt #该参数可选
)
```
## Agent的方法
### predict() 和 apredict()
实际上，你可以像使用LLM一样使用Agent.  
最基础获取输出，和LLM一样的方法还是predict()方法  
apredict()方法的参数和predict()一样，但是是异步方法
```
和LLM的输出一致，当Agent设置参数为非流式的时候，Agent会执行完工具再一次回复之后一次性输出，输出结果为：
{
    "role":"assistant",
    "content":"..."
}
如果是流式的输出，一下的内容会一直出现：
{
    "role":"assistant",
    "content":"..."
}
当出现了tool_name时，Agent会先返回工具名称，让开发者可以提前知道大模型使用了什么工具：
{
    "role":"assistant",
    "content":"...",
    "tool_name":"...",
}
接下来工具参数会以片段的方式一段一段的输出,注意，这并不意味着你需要收集这些片段，因为后面Agent会返回一个完整的tool_calls给你：
{
    "role":"assistant",
    "content":"...",
    "tool_arguments":"..."
}
当出现了完整的tool_calls时，Agent会直接返回一个完整的tool_calls：
{
    "role":"assistant",
    "content":"...",
    "tool_calls":[]
}
出现了tool_calls之后，Agent会自动地执行工具，然后返回下面的结果，角色会变为tool，内容是工具返回的结果：
{
    "role":"tool"
    "content":"...",
}
注意如果是思考模型。思考内容会在reasoning_content里面：
{
    "role":"assistant",
    "content":"...",
    "reasoning_content":""
}
然后会接着返回正常的输出
```
```python
...
result = agent.predict(instruction="你好？")
#agent.predict()默认流式输出
for chunk in result:
    print(chunk,end="")
...
```
```python
predict(
    instruction:str,#输入指令
    temperature:float,
    top_p:float,
    top_k:int,
    min_p:float,
    stream:bool=False,#是否流式输出
)
```
### disable_tool和enable_tool
该方法用于禁用或启用工具  
用于一些特殊情况直接禁用或启用工具  
```python
# 假设有一个search工具
agent.disable_tool("search") #这个时候Agent不会知道这个工具，但是它依然在工具集存在
agent.enable_tool("search") # 重新启用工具，Agent会重新知道这个工具
```
### 获取消息列表 get_messages
```python
# 返回当前agent的消息列表
agent.get_messages() 
```
### 清除消息 clear_messages
```python
# 会清空除了系统消息的所有消息
agent.clear_messages()
```
### 获取当前工具列表 get_tools
```python
# 获取当前agent可用的工具列表
agent.get_tools()
```
### 获取系统提示词 get_system_prompt
```python
agent.get_system_prompt()
```
### 添加消息 add_message
```python
# 添加消息，用于系统自动添加消息，也可以临时插入系统消息改变Agent的运行逻辑
agent.add_message(
    role="user",# 可以是user，assistant，system
    content="你好，这是用户消息"
)
```
### 添加消息列表 add_messages
```python
messages = [
    {"role": "user", "content": "你好，这是用户消息"},
    {"role": "assistant", "content": "你好，这是助手消息"},
    {"role": "system", "content": "你好，这是系统消息"},
]
agent.add_messages(
    messages
)
```
### 获取工具执行结果列表 get_tools_call_results
```python
tools_results = agent.get_tools_call_results()
```
### 获取工具调用记录 get_tools_call
```python
tools_call = agent.get_tools_call()
```
### 添加mcp服务器 add_mcp_server
```python
config={
    "type":"stdio",
    "command":"npx",
    "args":["@playwright/mcp@latest"]
}
agent.add_server(
    server_id="playwright", 
    config=config
)
```
### 删除mcp服务器 remove_mcp_server
```python
agent.remove_mcp_server("playwright")
```
### 获取mcp服务器信息 get_mcp_server_info
```python
agent.get_mcp_server_info("playwright")
```

# 五. 添加MCP服务器
## 实例化MCP客户端
```python
from tina.mcp import MCPClient

mcp = MCPClient()
# 添加playwright MCP服务，一个浏览器自动化工具
mcp.add_server(
    server_id="playwright", 
    config={
        "type":"stdio",
        "command":"npx",
        "args":["@playwright/mcp@latest"]
    }
)
from tina import Agent,Tools
from tina.llm import BaseAPI
llm = BaseAPI()
tools = Tools()
system_prompt = "你是一个浏览器自动化助手"
agent = Agent(
    llm = llm,
    tools = tools,
    system_prompt = system_prompt,
    mcp = mcp #可以直接传递mcp客户端实例
)

```