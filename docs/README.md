# tina 文档中心

欢迎来到 tina 的完整文档!

## 📚 API 参考文档

### 核心模块

- **[LLM API](./api/llm.md)** - 大语言模型调用
  - 统一的 API 接口
  - 流式/非流式输出
  - 多轮对话管理
  - 完整的参数控制

- **[Tools API](./api/tools.md)** - 工具系统
  - 注释即描述
  - 装饰器注册
  - 同步/异步工具
  - 工具集管理

- **[Agent API](./api/agent.md)** - 智能体
  - 自动工具调用
  - 消息历史管理
  - 工具控制
  - 推理模型支持

- **[MCP API](./api/mcp.md)** - 模型上下文协议
  - 一键集成 MCP 服务器
  - 自动工具发现
  - 常用服务器配置

## 🚀 快速开始

### 安装

```bash
# 基础安装
pip install tina-python

# 包含 MCP 支持
pip install tina-python[mcp]
```

### 5分钟上手

**1. 调用大模型**

```python
from tina.llm import BaseAPI

llm = BaseAPI()
result = llm.predict(input_text="你好")
print(result["content"])
```

**2. 注册工具**

```python
from tina import Tools

tools = Tools()

@tools.register()
def get_weather(city: str):
    """
    获取城市天气
    Args:
        city: 城市名称
    """
    return f"{city}今天晴,25度"
```

**3. 创建 Agent**

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

llm = BaseAPI()
tools = Tools()

@tools.register()
def get_time():
    """获取当前时间"""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

agent = Agent(llm=llm, tools=tools)

for chunk in agent.predict("现在几点?"):
    print(chunk.get("content", ""), end="")
```

**4. 使用 MCP**

```python
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

agent = Agent(llm=llm, tools=tools, mcp=mcp)
```

## 📖 学习路径

### 初学者

1. **[LLM API](./api/llm.md)** - 了解如何调用大模型
2. **[Tools API](./api/tools.md)** - 学习工具注册
3. **[Agent API](./api/agent.md)** - 创建你的第一个智能体

### 进阶用户

1. **[MCP API](./api/mcp.md)** - 集成外部服务
2. **[Agent API - 高级](./api/agent.md#进阶技巧)** - 自定义 Agent 行为
3. **[Tools API - 高级](./api/tools.md#进阶技巧)** - 动态工具生成

### 高级用户

1. **[高级用法指南](./advanced.md)** - 深入定制 tina
   - 自定义 ContextManager (记忆管理)
   - 自定义 AgentRuntime (ReAct、CoT 等推理模式)
   - 自定义 ToolsExecutor (超时、重试、日志)
   - 完整的扩展示例

## 💡 示例代码

### 常见场景

**天气查询 Agent**

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

tools = Tools()

@tools.register()
def get_weather(city: str):
    """获取天气 Args: city: 城市名"""
    return f"{city}今天晴,25度"

agent = Agent(llm=BaseAPI(), tools=tools)

for chunk in agent.predict("北京天气怎么样?"):
    print(chunk.get("content", ""), end="")
```

**网页自动化 Agent**

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

mcp = MCPClient()
mcp.add_server("playwright", {
    "type": "stdio",
    "command": "npx",
    "args": ["@playwright/mcp@latest"]
})

agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是浏览器自动化助手"
)

for chunk in agent.predict("打开百度搜索天气"):
    print(chunk.get("content", ""), end="")
```

**数据分析 Agent**

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

tools = Tools()

@tools.register()
def analyze_data(data: list):
    """分析数据 Args: data: 数据列表"""
    return {
        "count": len(data),
        "sum": sum(data),
        "avg": sum(data) / len(data)
    }

agent = Agent(
    llm=BaseAPI(),
    tools=tools,
    system_prompt="你是数据分析师"
)

for chunk in agent.predict("分析这组数据: [1,2,3,4,5]"):
    print(chunk.get("content", ""), end="")
```

## 🔧 环境配置

创建 `tina.env` 文件:

```env
LLM_API_KEY=your-api-key
BASE_URL=https://api.openai.com/v1/chat/completions
MODEL_NAME=gpt-3.5-turbo
MAX_INPUT=8000
```

## 🤝 获取帮助

- 📖 **文档问题?** 查看各 API 文档的"常见问题"章节
- 🐛 **发现 Bug?** 提交 Issue
- 💬 **使用问题?** 运行内置的 Tina 助手:
  ```python
  from tina import Tina
  Tina().run()
  ```

## 🔗 相关资源

- [返回主 README](../README.md)
- [MCP 官方文档](https://modelcontextprotocol.io)
- [魔塔 MCP 广场](https://www.modelscope.cn/mcp)

---

**Made with ❤️ by QiQi in 🌟 XIMO**
