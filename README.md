# tina

![tina logo](logo.svg)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

一个轻量、模块化的 AI 智能体框架，基于 OpenAI API 格式构建。

## 安装

```bash
# 基础安装（需要 Python >= 3.10）
pip install tina-python

# 如果需要使用 MCP（模型上下文协议）服务
pip install tina-python[mcp]

# 如果需要运行测试
pip install tina-python[test]
```

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

# 1. 实例化大模型（支持通过 tina.env 文件配置）
llm = BaseAPI(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-4o"
)

# 2. 创建工具集并注册工具
tools = Tools()

@tools.register()
def get_weather(city: str):
    """
    查询城市天气
    Args:
        city (str): 城市名称
    """
    return f"{city}今天天气晴朗，温度25°C"

# 3. 创建 Agent 并运行
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是一个有用的助手"
)

# 流式对话
result = agent.predict(instruction="今天的北京天气怎么样？", stream=True)
for chunk in result:
    print(chunk.content, end="", flush=True)
```

---

## 目录

- [tina 是什么](#tina-是什么)
- [特性概览](#特性概览)
- [一、LLM 层 —— 调用大模型](#一llm-层--调用大模型)
- [二、Tools 层 —— 工具注册与管理](#二tools-层--工具注册与管理)
- [三、Agent 层 —— 智能体](#三agent-层--智能体)
- [四、MCP 支持 —— 模型上下文协议](#四mcp-支持--模型上下文协议)
- [五、多模态支持](#五多模态支持)
- [六、快速开发工具](#六快速开发工具)

---

## tina 是什么

tina 是一个轻量、模块化的 AI 智能体框架，专注于让开发者以最少的代码实现大模型应用的原型验证。

**设计理念：**
- **简单直观**：不需要复杂的 Chain 或 Graph 概念，像调用函数一样使用大模型
- **模块化**：LLM、Tools、Agent 各层独立，可按需使用
- **轻量依赖**：核心仅依赖 `httpx` 和 `python-dotenv`
- **注释即描述**：通过 Google 风格的注释自动生成工具 JSON Schema

> tina 是我大学期间兴趣使然开发的练习作品，适合快速原型验证。如果需要生产级的稳定性，请使用 LangChain 等成熟框架。

## 特性概览

| 模块 | 功能 | 说明 |
|------|------|------|
| **BaseAPI** | API 调用 | 支持流式/非流式、工具调用、多种采样参数 |
| **BaseMultimodalAPI** | 多模态调用 | 支持图片、音频、URL 输入 |
| **Tools** | 工具管理 | 注册、合并、执行，自动生成 Schema |
| **Agent** | 智能体 | 自动维护对话、执行工具、事件回调 |
| **MultimodalAgent** | 多模态智能体 | 继承 Agent，支持多媒体输入与多模态工具 |
| **MCPClient** | MCP 集成 | 连接 MCP 服务器生态（stdio/SSE） |
| **ContextManager** | 上下文管理 | 滚动窗口策略，自动截断 |
| **AgentEvents** | 事件系统 | 贯穿 Agent 生命周期的回调钩子 |

---

## 一、LLM 层 —— 调用大模型

tina 使用 `httpx` 直接调用 OpenAI 格式的 API，不依赖 OpenAI SDK。

### 1.1 快速使用

```python
from tina.llm import BaseAPI

# 推荐：使用 tina.env 文件（自动从当前目录查找 .env 或 tina.env）
llm = BaseAPI()

# 或者：手动传入参数
llm = BaseAPI(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-4o"
)
```

`tina.env` 文件示例：
```env
LLM_API_KEY="your-api-key"
BASE_URL="https://api.openai.com/v1/chat/completions"
MODEL_NAME="gpt-4o"
```

> **注意**：`base_url` 需要包含完整的 `/chat/completions` 路由，tina 不会自动补充。

### 1.2 非流式调用

```python
result = llm.predict(
    input_text="帮我翻译这句话：Hello tina",
    sys_prompt="你是一位专业的翻译家",
    stream=False
)
print(result["content"])
```

### 1.3 流式调用

```python
result = llm.predict(
    input_text="讲一个故事",
    stream=True
)
for chunk in result:
    print(chunk["content"], end="")
```

### 1.4 多轮对话

```python
messages = [
    {"role": "system", "content": "你是一个有用的助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
]

result = llm.predict(
    input_text="北京天气怎么样？",  # 自动追加到 messages
    messages=messages,
    stream=True
)
```

### 1.5 异步调用

```python
result = await llm.apredict(
    input_text="你好",
    stream=False
)

# 异步流式
async for chunk in llm.apredict(input_text="讲个故事", stream=True):
    print(chunk["content"], end="")
```

### 1.6 predict 参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `input_text` | `str` | `None` | 用户输入文本 |
| `sys_prompt` | `str` | `"你的工作非常的出色！"` | 系统提示词 |
| `messages` | `list` | `None` | 历史消息列表 |
| `temperature` | `float` | `1.0` | 随机性 (0.0~1.0) |
| `top_p` | `float` | `0.9` | 核采样 |
| `top_k` | `int` | `None` | Top-K 采样 |
| `min_p` | `float` | `None` | 最小概率采样 |
| `max_tokens` | `int` | `None` | 最大生成 token 数 |
| `presence_penalty` | `float` | `None` | 存在惩罚 (-2.0~2.0) |
| `frequency_penalty` | `float` | `None` | 频率惩罚 (-2.0~2.0) |
| `stream` | `bool` | `False` | 是否流式输出 |
| `format` | `str` | `"text"` | 输出格式：`"text"` 或 `"json"` |
| `tools` | `list` | `None` | 工具列表 |
| `timeout` | `int` | `180` | 超时时间（秒） |

### 1.7 返回值格式

```python
# 非流式
{
    "role": "assistant",
    "content": "回复内容",
    # 推理模型时会出现
    "reasoning_content": "推理链...",
    # 有工具调用时会出现
    "tool_calls": [
        {
            "index": 0,
            "function": {"name": "...", "arguments": "{}"},
            "type": "function",
            "id": "call_xxx"
        }
    ]
}

# 流式：逐块返回，格式与非流式一致
```

### 1.8 获取可用模型列表

```python
# 仅适用于标准 OpenAI API
models = llm.get_models()
print(models["available_models"])
```

---

## 二、Tools 层 —— 工具注册与管理

`Tools` 是 tina 的工具管理核心，支持注册、查询、合并和执行。

### 2.1 创建工具集

```python
from tina import Tools

# 简单使用（不指定名称）
tools = Tools()

# 命名工具集（用于包管理和合并）
tools = Tools(name="my_tools", metadata={"author": "me"})
```

> 指定 `name` 后会给工具添加命名空间前缀（`{name}_{函数名}`），方便工具包合并时避免名称冲突。

### 2.2 注册工具

#### 装饰器方式（推荐）

```python
tools = Tools()

@tools.register()
def get_weather(city: str):
    """
    查询城市天气
    Args:
        city (str): 城市名称
    """
    return f"{city}今天天气晴朗"

@tools.register(
    description="手动描述（可选）",
    require_confirmation=True,  # 需要用户确认
    return_image=False,         # 多模态：返回图片
    return_audio=False,         # 多模态：返回音频
    return_url=False,           # 多模态：返回 URL
)
def delete_file(path: str):
    """删除文件（高危操作）"""
    ...
```

#### 方法方式

```python
def add(a: int, b: int):
    """两数相加"""
    return a + b

tools.register_tool(tool=add)
```

#### 注册不带功能实现的工具

```python
tools.register_no_function(
    name="search",
    description="搜索引擎",
    required_parameters=["query"],
    parameters={
        "query": {
            "type": "string",
            "description": "搜索关键词"
        }
    }
)
```

### 2.3 注销工具

```python
tools.unregister("get_weather")
```

### 2.4 工具包合并（命名空间隔离）

适用于分发和组合工具包：

```python
from tina import Tools

search_tools = Tools(name="search")
@search_tools.register()
def web(query: str):
    """网页搜索"""
    return f"搜索结果：{query}"

data_tools = Tools(name="data")
@data_tools.register()
def query(sql: str):
    """数据库查询"""
    return f"查询结果：{sql}"

# 合并工具包
all_tools = search_tools + data_tools
# 或
all_tools += data_tools

# 添加多个
all_tools.add_tools([search_tools, data_tools])

# 减掉工具包
all_tools -= search_tools
# 或
all_tools.sub_tools([search_tools])
```

### 2.5 执行工具

```python
tool_calls = [
    {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"city": "北京"}'
        }
    }
]
results = tools.execute(tool_calls)
# [
#   {"role": "tool", "tool_call_id": "call_123", "name": "get_weather", "content": "北京今天天气晴朗"}
# ]
```

### 2.6 工具查询

```python
# 获取所有工具 Schema
tools.get_tools()

# 获取单个工具信息
tools.get_tool_info("get_weather")

# 获取工具函数
func = tools.get_tool("get_weather")
result = func("上海")
```

### 2.7 在类中定义工具（最佳实践）

```python
class SearchService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.tools = Tools(name="search_service")
        self.tools.register_tool(self.web_search)

    def web_search(self, query: str):
        """
        互联网搜索
        Args:
            query (str): 搜索关键词
        """
        return f"搜索结果：{query}"

    def get_tools(self):
        return self.tools

# 使用
search = SearchService(api_key="xxx")
agent = Agent(llm=llm, tools=search.get_tools())
```

### 2.8 Google 风格注释解析

tina 会自动解析以下格式的注释生成 JSON Schema：

```python
def tool_func(param1: str, param2: int):
    """
    工具的描述（会被提取为 description）
    Args:
        param1 (str): 参数1的描述
        param2 (int): 参数2的描述
    Returns:
        str: 返回值描述
    Raises:
        ValueError: 异常描述
    """
```

---

## 三、Agent 层 —— 智能体

Agent = LLM + Tools + ContextManager，自动维护对话上下文并执行工具调用循环。

### 3.1 实例化 Agent

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

llm = BaseAPI()
tools = Tools()

agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是一个有用的助手",
    name="my_agent",          # 可选：Agent 名称
    mcp=None,                 # 可选：MCPClient 实例
    events=None,              # 可选：AgentEvents 实例
    context_manager=None,     # 可选：自定义 ContextManager
    agent_runtime=None,       # 可选：自定义 AgentRuntime
    max_tool_loop=30,         # 最大工具调用循环次数
    max_context_length=100000,# 最大上下文长度（字符）
    max_tool_result_length=6000, # 工具结果最大长度
)
```

### 3.2 使用 Agent 对话

```python
# 流式输出（默认）
result = agent.predict(instruction="今天北京天气怎么样？", stream=True)
for chunk in result:
    print(chunk.content, end="", flush=True)

# 非流式输出
result = agent.predict(instruction="你好", stream=False)
print(result.content)

# 异步流式
async for chunk in agent.apredict(instruction="你好"):
    print(chunk.content, end="")

# 异步非流式
result = await agent.apredict_no_stream(instruction="你好")
```

**predict 参数：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `instruction` | `str` | `None` | 用户指令 |
| `temperature` | `float` | `0.5` | 采样温度 |
| `top_p` | `float` | `0.9` | 核采样 |
| `top_k` | `int` | `1` | Top-K 采样 |
| `min_p` | `float` | `0.0` | 最小概率采样 |
| `stream` | `bool` | `True` | 是否流式输出 |

### 3.3 Agent 状态

```python
from tina import AgentState

# 获取当前状态
if agent.state == AgentState.IDLE:
    print("Agent 空闲中")
elif agent.state == AgentState.RESPONDING:
    print("Agent 正在输出")
elif agent.state == AgentState.THINKING:
    print("Agent 正在思考")
elif agent.state == AgentState.TOOL_CALLING:
    print("Agent 正在使用工具")
elif agent.state == AgentState.ON_TOOL_CONFIRM:
    print("Agent 等待工具确认")
elif agent.state == AgentState.ERROR:
    print("Agent 出错")
```

### 3.4 消息管理

```python
# 获取消息列表
messages = agent.get_messages()

# 清空消息（保留系统提示词）
agent.clear_messages()

# 获取系统提示词
prompt = agent.get_system_prompt()

# 设置系统提示词
agent.set_system_prompt("新的系统提示词")

# 添加单条消息
agent.add_message(role="user", content="你好")

# 添加消息列表
agent.add_messages([
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"}
])

# 获取工具调用信息
last_call = agent.get_last_tool_call()
last_result = agent.get_last_tool_result()
tool_calls = agent.get_tools_call()
tool_results = agent.get_tools_call_result()
```

### 3.5 事件回调（Event Hooks）

Agent 提供了丰富的生命周期事件：

```python
# 1. 用户指令处理前（可修改输入）
@agent.before_user_instruction()
def on_before_user(user_message: str):
    return f"【增强】{user_message}"  # 返回修改后的输入

# 2. 用户指令处理后
@agent.after_user_instruction()
def on_after_user(user_message: str, assistant_message: str):
    print(f"问：{user_message}")
    print(f"答：{assistant_message}")

# 3. 工具调用前（可修改参数）
@agent.before_tool_call()
def on_before_tool(tool_name: str, tool_arguments: dict):
    return tool_name, tool_arguments  # 必须返回两个参数

# 4. 工具调用后（可修改结果）
@agent.after_tool_call()
def on_after_tool(tool_name: str, tool_arguments: dict, tool_result: any):
    return tool_name, tool_arguments, tool_result  # 必须返回三个参数

# 5. 工具需要确认时
@agent.on_tool_confirmation()
def on_confirm(tool_name: str, tool_arguments: dict):
    return True    # 放行
    # return False  # 拦截
    # return (False, "自定义拒绝理由")  # 拦截并说明理由

# 6. 流式片段监听
@agent.on_stream_chunk()
def on_stream(chunk):
    print(chunk.content, end="", flush=True)

# 7. 工具序列监听
@agent.before_tool_calls()
def on_before_calls(tool_calls: list):
    print(f"模型准备调用 {len(tool_calls)} 个工具")

@agent.after_tool_calls()
def on_after_calls(tool_calls: list):
    print(f"工具调用完成")

# 8. 推理轮次结束
@agent.on_turn_end()
def on_turn_end():
    print("本轮推理完成")
```

> **注意**：
> - 事件处理函数可以是同步或异步的。异步函数仅在 `apredict` 时执行
> - 拦截型事件（before_xxx）如果有返回值，必须原样返回对应数量的参数

### 3.6 多 Agent 连接

```python
agent_a = Agent(llm=llm, tools=tools, name="agent_a")
agent_b = Agent(llm=llm, tools=tools, name="agent_b")

# 连接：共享消息列表
agent_a.connect_agent(agent_b)

# 断开连接
agent_a.disconnect_agent(agent_b)
```

### 3.7 自定义事件管理

```python
from tina import AgentEvents

events = AgentEvents()

@events.on_stream_chunk()
def on_stream(chunk):
    print(chunk.content, end="")

@events.on_turn_end()
def on_end():
    print("完成")

agent = Agent(
    llm=llm,
    tools=tools,
    events=events
)
```

### 3.8 输出格式（流式）

Agent 流式输出的每一帧是一个 `AgentResponse` 对象，包含以下可能的字段：

```python
# 1. 普通文本输出
AgentResponse(role="assistant", content="回复内容")

# 2. 推理模型输出
AgentResponse(role="assistant", content="", reasoning_content="推理链")

# 3. 工具调用通知
AgentResponse(role="assistant", content="", tool_name="get_weather")

# 4. 工具参数片段
AgentResponse(role="assistant", content="", tool_name="get_weather", tool_arguments='{"city": "北京"}')

# 5. 完整工具调用
AgentResponse(role="assistant", content="", tool_calls=[...])

# 6. 工具执行结果
AgentResponse(role="tool", content="工具返回结果", tool_name="get_weather")
```

---

## 四、MCP 支持 —— 模型上下文协议

tina 支持通过 MCP（Model Context Protocol）连接外部工具生态。

### 4.1 安装 MCP 依赖

```bash
pip install tina-python[mcp]
```

### 4.2 使用 MCP 客户端

```python
from tina.mcp import MCPClient

mcp = MCPClient()

# 添加 stdio 类型 MCP 服务
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

# 添加 SSE 类型 MCP 服务
mcp.add_server(
    server_id="my-service",
    config={
        "type": "sse",
        "url": "http://localhost:8080/sse"
    }
)
```

### 4.3 在 Agent 中使用 MCP

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

mcp = MCPClient()
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

llm = BaseAPI()
tools = Tools()

agent = Agent(
    llm=llm,
    tools=tools,
    mcp=mcp,
    system_prompt="你是一个浏览器自动化助手"
)

result = agent.predict(instruction="导航到 bing.com 并搜索 tina", stream=True)
for chunk in result:
    print(chunk.content, end="")
```

### 4.4 MCP 服务管理

```python
# 添加服务
agent.add_mcp_server("server_id", config)

# 移除服务
agent.remove_mcp_server("server_id")

# 获取服务信息
info = agent.get_mcp_server_info("server_id")

# 获取所有服务信息
all_info = agent.get_mcp_server_info()
```

### 4.5 MCP 工具转换

`MCPClient` 会自动将 MCP 工具转换为 Tina 工具格式，Agent 可直接调用。

---

## 五、多模态支持

### 5.1 多模态 LLM

```python
from tina.llm import BaseMultimodalAPI

mllm = BaseMultimodalAPI()

# 图片输入
result = mllm.predict(
    input_text="这张图里有什么？",
    input_image="path/to/image.jpg",
    stream=False
)

# 多图片 + 音频
result = mllm.predict(
    input_text="描述这些内容",
    input_image=["image1.jpg", "image2.png"],
    input_audio="audio.mp3",
)
```

### 5.2 多模态 Agent

```python
from tina import MultimodalAgent, Tools
from tina.llm import BaseMultimodalAPI

mllm = BaseMultimodalAPI()
tools = Tools()

magent = MultimodalAgent(
    llm=mllm,
    tools=tools
)

result = magent.predict(
    instruction="这张图显示了什么天气？",
    image="weather.jpg",
)
```

### 5.3 多模态工具

注册工具时指定返回类型，tina 会自动处理多媒体数据转换：

```python
@tools.register(return_image=True)
def capture_screenshot(url: str):
    """
    截取网页截图
    Args:
        url (str): 网页地址
    """
    return "screenshot.png"  # 自动转为 Base64 给模型

@tools.register(return_audio=True)
def text_to_speech(text: str):
    """
    文本转语音
    Args:
        text (str): 要朗读的文本
    """
    return "speech.mp3"

@tools.register(return_url=True)
def search_product(query: str):
    """
    搜索商品
    Args:
        query (str): 搜索词
    """
    return "https://example.com/product/123"

magent = MultimodalAgent(llm=mllm, tools=tools)
```

### 5.4 构建多模态消息

```python
from tina.utils import build_multimodal_message

message = build_multimodal_message(
    input_text="描述这张图",
    input_image="image.jpg",
    input_audio="audio.mp3",
    input_url="https://example.com/image.png",
    image_detail="high",  # 细节：low / high / auto
)
```

---


---

## 六、快速开发工具

tina 提供了一些开箱即用的工具函数和工具包，帮助你快速搭建应用。

### 6.1 系统工具包 `system_tools`

tina 自带一套系统工具包，包含文件操作、代码执行等常用功能：

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.utils.system_tools import system_tools

tools = Tools()
tools += system_tools  # 添加 tina 自带的系统工具包

agent = Agent(
    llm=BaseAPI(),
    tools=tools,
    system_prompt="你是一个系统助手，可以帮助我管理文件和执行代码"
)

result = agent.predict(instruction="帮我看看当前目录下有哪些文件", stream=True)
for chunk in result:
    print(chunk.content, end="")
```

**内置工具一览：**

| 工具名称 | 需要确认 | 功能说明 |
|---------|---------|---------|
| `get_time` | ❌ | 获取当前系统时间 |
| `list_dir` | ❌ | 列出目录下的文件和子目录 |
| `project_tree` | ❌ | 获取项目目录结构（类似 tree 命令） |
| `get_path` | ❌ | 获取文件/文件夹的绝对路径 |
| `read_code` | ❌ | 按字节范围读取文件内容片段 |
| `read_code_by_line` | ❌ | 按行读取代码片段 |
| `search_in_files` | ❌ | 在项目中搜索文本（支持正则） |
| `delay` | ❌ | 延时函数 |
| `make_dir` | ✅ | 创建目录 |
| `write_code` | ✅ | 写入文件内容（覆盖） |
| `append_code` | ✅ | 追加写入文件内容 |
| `delete_path` | ✅ | 删除文件或空目录 |
| `replace_code_by_lines` | ✅ | 按行范围替换代码块 |
| `terminal` | ✅ | 在终端运行指令 |
| `run_python` | ✅ | 执行一小段 Python 代码 |
| `shot_down_system` | ❌ | 关机（交互式确认） |

> `需要确认` 的工具在执行时会触发 `on_tool_confirmation` 事件，适合接入人工审批流程。

### 6.2 后台工作器 `AgentWorker`

`AgentWorker` 将 Agent 包装为异步后台服务，通过消息队列接收外部指令并持续处理：

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.utils import AgentWorker

llm = BaseAPI()
tools = Tools()
agent = Agent(llm=llm, tools=tools)

worker = AgentWorker(agent=agent, max_queue_size=20)

# 添加流式输出处理器
def on_chunk(chunk):
    print(chunk.content, end="", flush=True)

worker.add_stream_chunk_handler(on_chunk)

# 在其他协程中向工作器推送指令
import asyncio

async def main():
    # 启动工作器
    asyncio.create_task(worker.run())

    # 推送指令
    await worker.put("你好，请帮我查一下天气")
    await worker.put("现在几点了？")

    # 查看队列状态
    print(f"队列中待处理消息数: {worker.get_queue_size()}")

asyncio.run(main())
```

`AgentWorker` 还会将自身的 `put` 方法自动注册为 Agent 的工具，方便多 Agent 场景下互相调用。

### 6.3 终端交互控制台 `run_agent_in_cli`

快速启动一个 Agent 交互式终端，适合调试和测试：

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.utils.run_agent_in_cli import run_agent_in_cli

# 搭建你的 Agent
llm = BaseAPI()
tools = Tools()
agent = Agent(llm=llm, tools=tools)

# 一键启动交互终端
run_agent_in_cli(agent)
```

启动后可在终端直接与 Agent 对话，支持以下指令：

| 指令 | 功能 |
|------|------|
| `#context` | 查看当前对话上下文（消息列表） |
| `#clear` | 清屏 |
| `#exit` | 退出（或直接输入 `exit` / `quit`） |

### 6.4 多模态消息构建器 `build_multimodal_message`

用于灵活构建包含多模态内容的消息：

```python
from tina.utils import build_multimodal_message

message = build_multimodal_message(
    input_text="描述这张图片",
    input_image="path/to/image.jpg",
    input_audio="path/to/audio.mp3",
    input_url=["https://example.com/image1.png", "https://example.com/image2.png"],
    image_detail="high",  # low / high / auto
    role="user"
)
print(message)
# {"role": "user", "content": [{"type": "text", "text": "..."}, {"type": "image_url", ...}]}
```

---

## 附录

### 环境配置

tina 支持通过环境文件配置 API 信息，自动从当前目录查找 `.env` 或 `tina.env`：

```env
LLM_API_KEY="your-api-key"
BASE_URL="https://api.openai.com/v1/chat/completions"
MODEL_NAME="gpt-4o"
MAX_INPUT=8000
```

### 依赖说明

| 用途 | 依赖 |
|------|------|
| 核心功能 | `httpx`, `python-dotenv` |
| MCP 支持 | `mcp` (包名: `mcp-python`) |
| 测试 | `pytest`, `pytest-asyncio`, `pytest-cov` |

### 许可证

Apache License 2.0

### 贡献

欢迎提交 Issue 和 PR！项目地址：https://github.com/XIMOCY/tina