# Tools 工具包类
## Tools API文档
### 实例化Tools
```python
from tina import Tools
tools = Tools()
```
#### 参数

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`tools_executor`** | `ToolsExecutor` | `ToolsExecutor()` | **工具执行器**。负责实际调用函数。通常保持默认即可，除非你需要自定义工具的执行逻辑（如异步钩子、日志记录）。它默认支持并发5个工具运行 |
| **`name`** | `str` | `None` | **工具包名称**。该参数用在区分你工具包 |
| **`metadata`** | `dict` | `None` | **工具包元数据**。该参数用于描述工具包的元数据，例如作者、版本、依赖项等。 |


>请注意 只有在你设置了name参数时 才可以进行后面的合并和去除方法  
 这是为区分你是快速的脚本开发还是需要使用其他人的工具包 
 如果你是做脚本开发，只需要简单的使用Tools类就就可以了
 如果你需要使用别人提供的工具包，请在实例化你的工具包时指定name参数，防止其他人和你用了一样的工具名称
 当你实例化了指定了`name`参数，实际上是给你的工具添加了一个简单的命名空间，此外工具的名称也会变为：`{name}_{工具本来的名称}`

### 注册工具 @register 和 register_tool
#### 参数

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`description`** | `str` | `None` | **手动描述**。若不填，Tina 会自动读取函数文档字符串作为工具描述。 |
| **`require_confirmation`** | `bool` | `False` | **工具确认**。若为 `True`，Agent 在执行该工具前会触发`on_tool_confirmation`事件，并`暂停，等待人类用户的授权。适合“转账”、“删除文件”等高危操作。 |
| **`require_persistence`** | `bool` | `False` | **持久化运行**。标识该工具是否需要在特定环境下保持运行状态或具有副作用记录。 |
| **`return_image`** | `bool` | `False` | **图片回传**。针对多模态 Agent。若工具返回图片路径，Tina 会自动将图片转为 Base64 并喂给模型“观看”。 |
| **`return_audio`** | `bool` | `False` | **音频回传**。针对多模态 Agent。工具返回的音频数据会自动提交给支持音频分析的模型。 |
| **`return_url`** | `bool` | `False` | **URL 回传**。针对多模态 Agent。自动将工具返回的资源 URL 链接给模型进行进一步访问。 |


tina支持两种注册工具的方式：
#### 装饰器 @register
```python
from tina import Tools
tools = Tools()

@tools.register()
def remember(content: str):
    """
    让Agent记住一些你的信息
    注意，只有一下的信息是需要记忆的：
    1. 用户的个人信息，例如他是谁
    2. 用户的爱好
    3. 用户的履历
    Args:
        content (str): 记忆的内容
    """
    with open("remember.md", "a",encoding = "utf-8") as f:
        f.write(content)
    return "记住了"
```
在tina中，你不需要填写复杂的JSON schemas tina会自动地解析你的函数注释来生成函数的JSON schemas  
注释解析遵循Google风格的注释及以下的结构
```python
"""
函数的描述
Args:
    参数名 (参数类型): 参数的描述
    ...
Returns:
    返回值类型: 返回值的描述
Raises:
    异常类型: 异常的描述
```
tina会把Args之外的内容作为函数的描述  
同时解析你的Args，生成对应参数的JSON schemas
#### 方法 register_tool
该方法运行你注册一个工具
##### 额外参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`tool`** | `callable` | `None` | 工具函数 |
```python
from tina import Tools
tools = Tools()

def remember(content: str):
    """
    让Agent记住一些你的信息
    注意，只有一下的信息是需要记忆的：
    1. 用户的个人信息，例如他是谁
    2. 用户的爱好
    3. 用户的履历
    Args:
        content (str): 记忆的内容
    """
    with open("remember.md", "a",encoding = "utf-8") as f:
        f.write(content)
    return "记住了"
tools.register_tool(tool = remember)
```
### 注销工具 unregister
它允许你删除一个工具
```python
tools.unregister(name = "remember")
```
#### 参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`name`** | `str` | `None` | 工具的名称 |
### 获取工具列表的JSON schema get_tools get_tools_for_llm
它允许你获取工具列表的JSON schema  
和get_tools不一样的是 get_tools_for_llm会返回一个把参数名称更改为json对应的参数名称
```python
print(tools.get_tools())
print(tools.get_tools_for_llm())
```

### 工具包加法和减法 + += - -= 
在tina中允许你合并其他人的工具包通过+=等运算符  
当你的工具包已经存在了对应的工具包时，不会相加  
同时你尝试使用-=减去工具包时，如果对应的工具包不存在，不会产生作用
```python
from tina import Tools
a_tools = Tools(name="a")
b_tools = Tools(name="b")

# 合并工具包
a_tools = a_tools + b_tools
a_tools += b_tools
# 去掉工具包
a_tools = a_tools - b_tools
a_tools -= b_tools  
```
### 添加工具包 add_tools
在tina中允许你通过add_tools方法添加工具包  
该方法本质是在内部调用了+=运算符  
```python
from tina import Tools
a_tools = Tools(name="a")
b_tools = Tools(name="b")
c_tools = Tools(name="c")
a_tools.add_tools([b_tools,c_tools])
```
#### 参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`tools`** | `Tools | list[Tools]` | `None` | 允许你传入一个或者多个工具包 |
 
### 去除工具包 sub_tools
在tina中允许你通过sub_tools方法去除工具包
该方法本质是在内部调用了-=运算符
```python
from tina import Tools
a_tools = Tools(name="a")
b_tools = Tools(name="b")
c_tools = Tools(name="c")
a_tools.add_tools([b_tools,c_tools])
a_tools.sub_tools([b_tools])
```
#### 参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`tools`** | `Tools | list[Tools]` | `None` | 允许你传入一个或者多个工具包 |
### 执行tool_calls execute aexecute
它会执行tool_calls，并返回工具执行的结果
```python
from tina import Tools

tools = Tools()

@tools.register()
def get_weather(city: str):
    """获取天气"""
    return f"{city}今天多云。"

# 模拟模型返回的 tool_calls
tool_calls = [
    {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"city": "上海"}'
        }
    }
]

# 执行工具
results = tools.execute(tool_calls)

# results 会返回一个列表，包含了每条工具执行后的消息对象
# [{"role": "tool", "tool_call_id": "call_123", "name": "get_weather", "content": "上海今天多云。"}]
print(results)
```
#### 参数

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`_tool_calls`** | `list` | **必填** | 模型生成的工具调用列表。格式需符合 OpenAI 标准。 |
| **`_mcp_client`** | `MCPClient` | `None` | 可选。如果你使用了 Model Context Protocol (MCP) 扩展，可以在此传入客户端。 |
| **`timeout`** | `int` | `60` | 工具执行的超时时间（秒）。 |

#### 使用示例

```python
from tina import Tools

tools = Tools()

@tools.register()
def get_weather(city: str):
    """获取天气"""
    return f"{city}今天多云。"

# 模拟模型返回的 tool_calls
tool_calls = [
    {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"city": "上海"}'
        }
    }
]

# 执行工具
results = tools.execute(tool_calls)

# results 会返回一个列表，包含了每条工具执行后的消息对象
# [{"role": "tool", "tool_call_id": "call_123", "name": "get_weather", "content": "上海今天多云。"}]
print(results)

```
### 获取工具函数 get_tool
该方法可以根据名称获取对应的工具函数
```python
tool = tools.get_tool("get_weather")
result = tool("上海")
print(result)
```

#### 参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`name`** | `str` | `None` | 工具的名称 |
#### 返回值
callable
### 获取单个工具的JSON schema get_tool_info
该方法可以根据名称获取对应的工具的JSON schema
```python
tool_info = tools.get_tool_info("get_weather")
print(tool_info)
```
#### 参数
| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`name`** | `str` | `None` | 工具的名称 |
#### 返回值
dict
```python
{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取天气",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称"
                }
            },
            "required": ["city"]
        }
    }
}
```
 


## Tools 最佳实践
### 快速开发
在快速开发agent的场景，推荐使用装饰器来定义工具  
观察下面的示例，它注册了一个天气查询工具
```python
from tina import Tools
tools = Tools()
@tools.register()
def get_weather(city: str):
    """
    获取天气
    Args:
        city (str): 城市名称
    """
    return f"{city}今天多云。"
```
这样的开发模式推荐于快速开发的脚本场景，它只是调用接口，然后返回结果，不需要复杂的状态和私有变量管理。  
在后面的agent层，你只需要按照下面的方式，就可以让agent使用工具了
```python
from tina import Agent
from tina.llm import BaseAPI
agent = Agent(llm=BaseAPI(), tools=tools)
```
### 在类中定义工具
这是在复杂开发中，我最推荐的开发方式，它的样式如下
```python
from tina import Tools

class SearchEngine():
    def __init__(self, api_key: str):
        self.api_key = api_key  # 存储私有状态
        self.tools = Tools(name="search_service")
        self.tools.register_tool(self.web_search)

    def web_search(self, query: str):
        """
        在互联网上搜索信息
        Args:
            query (str): 搜索关键词
        """
        # 使用 self.api_key 进行鉴权调用
        return f"搜索结果：关于 {query} 的内容..."

    def get_tools(self):
        return self.tools
```
它符合下面的思路：
1. 我写了一个类，它的功能复杂状态多，但是职责单一，只负责某一个方面；
2. 我认为里面有些方法可以被我的agent所使用，那么我就将这些方法注册为工具；
3. 在使用的时候提供get_tools方法，将工具返回给agent使用。
然后你就可以这样来开发了：
```python
from tina import Agent
from tina.llm import BaseAPI

search_engine = SearchEngine(api_key="xxxx")
# 假设你是第一次实例化agent
agent = Agent(llm=BaseAPI(), tools=search_engine.get_tools())
# 如果你已经有了agent实例，那么你可以这样来使用
agent.tools.add_tools(search_engine.get_tools())
```
### 工具安全
在使用工具时，你需要考虑工具是否安全。  
```python
from tina import Tools

@tools.register(require_confirmation=True)
def write_file(file_path: str, content: str):
    ...
# 上面的代码在执行的时候会触发agent的回调事件
@agent.on_tool_confirmation()
def on_tool_confirmation(tool_name: str, tool_args: dict):
    """你需要在这里做一些确认工作，由你编写逻辑"""
    ...

```
