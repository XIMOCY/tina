# tina

<div align="center">

**简单优雅的 Python AI Agent 框架**

一个介于 OpenAI SDK 和 LangChain 之间的轻量级智能体库

[安装](#-安装) • [快速开始](#-快速开始) • [文档](./docs/) • [示例](#-示例)

</div>

---

## ✨ 为什么选择 tina?

- 🎯 **恰到好处的抽象** - 比 OpenAI SDK 更灵活,比 LangChain 更简单
- 🛠️ **注释即工具** - 使用 Google 风格注释自动生成工具描述,无需重复定义
- 🔌 **完美支持 MCP** - 开箱即用的模型上下文协议支持
- 🧩 **模块化设计** - LLM、Tools、Agent 都可独立使用
- 🚀 **同步/异步双模式** - 同时支持同步和异步调用

## 📦 安装

```bash
# 基础安装
pip install tina-python

# 包含 MCP 支持
pip install tina-python[mcp]
```

## 🚀 快速开始

### 30秒上手 - 调用大模型

```python
from tina.llm import BaseAPI

llm = BaseAPI(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-3.5-turbo"
)

result = llm.predict(
    input_text="Hello tina!",
    sys_prompt="你是一位专业的翻译家"
)
print(result["content"])
```

### 1分钟进阶 - 给 Agent 添加工具

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

# 定义工具 - 注释即描述!
tools = Tools()

@tools.register()
def get_weather(city: str):
    """
    获取城市天气
    Args:
        city: 城市名称
    """
    return f"{city}今天晴,25度"

# 创建 Agent
llm = BaseAPI()
agent = Agent(llm=llm, tools=tools)

# 使用 Agent
for chunk in agent.predict("北京天气怎么样?"):
    print(chunk["content"], end="")
```

### 2分钟高级 - 使用 MCP 扩展能力

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

# 添加 MCP 服务器
mcp = MCPClient()
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

# Agent 自动获得浏览器自动化能力
agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是浏览器自动化助手"
)

for chunk in agent.predict("帮我打开百度"):
    print(chunk["content"], end="")
```

## 🎮 体验 Tina - AI 说明书

tina 自带了一个交互式 AI 助手,可以回答关于框架的问题:

```python
from tina import Tina

my_tina = Tina()
my_tina.run()
```

```console
(´▽`ʃ♡ƪ)"  tina by QiQi in 🌟 XIMO

😊 欢迎使用tina，你可以输入#help来查看帮助
🤔 退出对话："#exit"

( • ̀ω•́ ) >>>User: 如何注册工具?
```

## 📚 核心功能

### 🤖 LLM - 大模型调用

- 统一的 API 接口,支持任何 OpenAI 兼容的服务
- 流式/非流式输出
- 多轮对话管理
- 完整的参数控制(temperature、top_p、top_k 等)

👉 [查看 LLM 完整文档](./docs/api/llm.md)

### 🛠️ Tools - 工具系统

- **注释即描述** - 自动解析 Google 风格注释
- 装饰器注册 - `@tools.register()`
- 同步/异步工具支持
- 工具集合并与管理

👉 [查看 Tools 完整文档](./docs/api/tools.md)

### 🤖 Agent - 智能体

- 自动工具调用与执行
- 消息历史管理
- 工具启用/禁用控制
- 推理模型支持(reasoning_content)

👉 [查看 Agent 完整文档](./docs/api/agent.md)

### 🔌 MCP - 模型上下文协议

- 一键集成 MCP 服务器
- 自动工具发现
- 支持任何 MCP 兼容服务

👉 [查看 MCP 完整文档](./docs/api/mcp.md) • [魔塔 MCP 广场](https://www.modelscope.cn/mcp)

## 💡 示例

### 环境配置

推荐使用 `tina.env` 文件管理配置:

```env
LLM_API_KEY=sk-xxx
BASE_URL=https://api.openai.com/v1/chat/completions
MODEL_NAME=gpt-3.5-turbo
MAX_INPUT=8000
```

### 流式输出

```python
# LLM 流式输出
for chunk in llm.predict("讲个故事", stream=True):
    print(chunk["content"], end="")

# Agent 流式输出(默认)
for chunk in agent.predict("现在几点?"):
    if "tool_name" in chunk:
        print(f"\n[调用工具: {chunk['tool_name']}]")
    else:
        print(chunk["content"], end="")
```

### 工具注册的多种方式

```python
tools = Tools()

# 方式1: 装饰器(推荐)
@tools.register()
def search(query: str):
    """搜索网络
    Args:
        query: 搜索关键词
    """
    return f"搜索结果: {query}"

# 方式2: 手动注册
def calculate(expr: str):
    """计算数学表达式
    Args:
        expr: 数学表达式
    """
    return eval(expr)

tools.register_tool(calculate, description="计算器")

# 方式3: 添加系统工具集
from tina.utils.system_tools import system_tools
tools += system_tools
```

## 📖 完整文档

- [API 参考](./docs/)
  - [LLM API](./docs/api/llm.md) - 大模型调用详解
  - [Tools API](./docs/api/tools.md) - 工具系统详解
  - [Agent API](./docs/api/agent.md) - Agent 方法详解
  - [MCP API](./docs/api/mcp.md) - MCP 集成详解
- [示例代码](./docs/examples/) - 更多实战示例

## 🤝 贡献

tina 是一个学习项目,欢迎 Issue 和 PR!

## 📄 许可证

MIT License

## ⚠️ 注意事项

> tina 是个人兴趣项目,适合快速原型验证和学习使用。  
> 如需生产环境的稳定性,建议使用 LangChain 等成熟框架。

