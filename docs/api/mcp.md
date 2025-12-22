# MCP API 文档

## 概述

MCP (Model Context Protocol) 是一个标准化协议,用于连接 AI 应用与外部工具和数据源。tina 完美支持 MCP,可以一键集成任何 MCP 兼容的服务器。

🔗 [MCP 官方文档](https://modelcontextprotocol.io) | [魔塔 MCP 广场](https://www.modelscope.cn/mcp)

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

# 创建 MCP 客户端
mcp = MCPClient()

# 添加 Playwright MCP 服务(浏览器自动化)
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

# 创建 Agent,自动获得浏览器自动化能力
agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是浏览器自动化助手"
)

# 使用
for chunk in agent.predict("打开百度并搜索天气"):
    print(chunk.get("content", ""), end="")
```

## MCPClient 类

### 初始化

```python
from tina.mcp import MCPClient

mcp = MCPClient()
```

### add_server()

添加 MCP 服务器。

```python
mcp.add_server(
    server_id: str,
    config: dict
)
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| server_id | str | 服务器唯一标识 |
| config | dict | 服务器配置 |

#### 配置格式

**标准 stdio 类型:**

```python
config = {
    "type": "stdio",           # 类型: stdio
    "command": "npx",          # 命令
    "args": ["package@latest"] # 参数列表
}
```

**示例:**

```python
# Playwright - 浏览器自动化
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

# Filesystem - 文件系统访问
mcp.add_server(
    server_id="filesystem",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@latest", "/path/to/dir"]
    }
)

# GitHub - GitHub 集成
mcp.add_server(
    server_id="github",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-github@latest"]
    }
)
```

### remove_server()

删除 MCP 服务器。

```python
mcp.remove_server("playwright")
```

### get_server_info()

获取服务器信息。

```python
info = mcp.get_server_info("playwright")
print(info)
```

## 在 Agent 中使用

### 方式1: 初始化时传递

```python
mcp = MCPClient()
mcp.add_server("playwright", {...})

agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp  # 传递 MCP 客户端
)
```

### 方式2: 动态添加

```python
agent = Agent(llm=BaseAPI(), tools=Tools())

# 后续添加 MCP 服务器
agent.add_mcp_server(
    server_id="playwright",
    config={...}
)
```

### 方式3: 移除服务器

```python
# 移除不需要的 MCP 服务器
agent.remove_mcp_server("playwright")
```

## 常用 MCP 服务器

### 1. Playwright - 浏览器自动化

```python
mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)
```

**能力:**
- 打开网页
- 点击元素
- 填写表单
- 截图
- 执行 JavaScript

**使用示例:**

```python
agent = Agent(llm=BaseAPI(), tools=Tools(), mcp=mcp)

for chunk in agent.predict("打开百度,搜索'天气'"):
    print(chunk.get("content", ""), end="")
```

### 2. Filesystem - 文件系统

```python
mcp.add_server(
    server_id="filesystem",
    config={
        "type": "stdio",
        "command": "npx",
        "args": [
            "@modelcontextprotocol/server-filesystem@latest",
            "/Users/username/Documents"  # 允许访问的目录
        ]
    }
)
```

**能力:**
- 读取文件
- 写入文件
- 列出目录
- 搜索文件

### 3. GitHub

```python
mcp.add_server(
    server_id="github",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-github@latest"]
    }
)
```

**能力:**
- 搜索仓库
- 查看 Issue
- 创建 PR
- 查看代码

### 4. PostgreSQL

```python
mcp.add_server(
    server_id="postgres",
    config={
        "type": "stdio",
        "command": "npx",
        "args": [
            "@modelcontextprotocol/server-postgres@latest",
            "postgresql://user:pass@localhost/db"
        ]
    }
)
```

**能力:**
- 执行 SQL 查询
- 查看表结构
- 数据分析

### 5. Slack

```python
mcp.add_server(
    server_id="slack",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-slack@latest"]
    }
)
```

**能力:**
- 发送消息
- 读取频道
- 管理工作区

## 完整示例

### 示例1: 网页爬虫助手

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.mcp import MCPClient

# 添加浏览器和文件系统能力
mcp = MCPClient()

mcp.add_server(
    server_id="playwright",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }
)

mcp.add_server(
    server_id="filesystem",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@latest", "./data"]
    }
)

# 创建爬虫助手
agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是网页爬虫助手,可以浏览网页并保存数据到文件"
)

# 使用
for chunk in agent.predict("访问news.ycombinator.com,获取前10条新闻标题,保存到news.txt"):
    if "tool_name" in chunk:
        print(f"\n[{chunk['tool_name']}]", end=" ")
    else:
        print(chunk.get("content", ""), end="")
```

### 示例2: GitHub 助手

```python
mcp = MCPClient()

mcp.add_server(
    server_id="github",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-github@latest"]
    }
)

agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是GitHub助手,帮助管理仓库和代码"
)

for chunk in agent.predict("搜索最近流行的Python项目"):
    print(chunk.get("content", ""), end="")
```

### 示例3: 数据分析助手

```python
mcp = MCPClient()

# 添加数据库访问
mcp.add_server(
    server_id="postgres",
    config={
        "type": "stdio",
        "command": "npx",
        "args": [
            "@modelcontextprotocol/server-postgres@latest",
            "postgresql://user:pass@localhost/analytics"
        ]
    }
)

# 添加文件系统保存报告
mcp.add_server(
    server_id="filesystem",
    config={
        "type": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@latest", "./reports"]
    }
)

agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是数据分析师,可以查询数据库并生成报告"
)

for chunk in agent.predict("分析上周的销售数据,生成报告保存到sales_report.txt"):
    print(chunk.get("content", ""), end="")
```

### 示例4: 多功能办公助手

```python
mcp = MCPClient()

# 浏览器
mcp.add_server("playwright", {
    "type": "stdio",
    "command": "npx",
    "args": ["@playwright/mcp@latest"]
})

# 文件系统
mcp.add_server("filesystem", {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem@latest", "./workspace"]
})

# GitHub
mcp.add_server("github", {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-github@latest"]
})

# Slack
mcp.add_server("slack", {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-slack@latest"]
})

agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    mcp=mcp,
    system_prompt="你是全能办公助手"
)

# 复杂任务
for chunk in agent.predict(
    "查看GitHub上我的最新PR,如果有更新就发Slack通知团队,并记录到log.txt"
):
    print(chunk.get("content", ""), end="")
```

## MCP 工具自动发现

添加 MCP 服务器后,服务器提供的所有工具会自动被 Agent 发现和使用,无需手动注册。

```python
# MCP 服务器提供的工具自动可用
mcp.add_server("playwright", {...})

agent = Agent(llm=llm, tools=Tools(), mcp=mcp)

# Agent 自动知道可以使用浏览器相关工具
agent.predict("打开网页")  # 自动调用 Playwright 工具
```

## 最佳实践

### 1. 按需添加服务器

```python
# 不要一次添加所有服务器
# 根据任务需要添加

# 需要网页操作时
if task_type == "web":
    mcp.add_server("playwright", {...})

# 需要文件操作时
if task_type == "file":
    mcp.add_server("filesystem", {...})
```

### 2. 安全的文件系统访问

```python
# 限制文件系统访问范围
mcp.add_server("filesystem", {
    "type": "stdio",
    "command": "npx",
    "args": [
        "@modelcontextprotocol/server-filesystem@latest",
        "./safe_directory"  # 只允许访问特定目录
    ]
})
```

### 3. 环境变量管理敏感信息

```python
import os

# 数据库连接使用环境变量
db_url = os.getenv("DATABASE_URL")

mcp.add_server("postgres", {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-postgres@latest", db_url]
})
```

### 4. 动态管理服务器

```python
# 任务开始时添加
agent.add_mcp_server("playwright", {...})

# 执行任务
for chunk in agent.predict("浏览器任务"):
    print(chunk.get("content", ""), end="")

# 任务结束后移除(释放资源)
agent.remove_mcp_server("playwright")
```

## 常见问题

### Q: 如何安装 MCP 服务器?

A: 大多数 MCP 服务器都是 npm 包,使用 `npx` 自动下载:

```bash
# 不需要全局安装,npx 会自动处理
npx @playwright/mcp@latest
```

### Q: MCP 服务器启动失败?

A: 检查:
1. Node.js 是否已安装 (`node --version`)
2. npm/npx 是否可用
3. 配置中的路径是否正确
4. 是否有网络访问 npm registry

### Q: 如何查看 MCP 服务器提供的工具?

A:

```python
# 添加服务器后,工具会自动合并到 Agent
agent = Agent(llm=llm, tools=Tools(), mcp=mcp)

# 查看所有可用工具
tools_list = agent.get_tools()
for tool in tools_list:
    print(tool["function"]["name"])
```

### Q: 可以自己开发 MCP 服务器吗?

A: 可以! 参考 [MCP 官方文档](https://modelcontextprotocol.io) 学习如何开发自定义 MCP 服务器。

### Q: MCP vs 直接注册工具,有什么区别?

A:

| 特性 | 直接注册工具 | MCP |
|------|------------|-----|
| 使用场景 | 简单的 Python 函数 | 复杂的外部服务 |
| 实现 | Python 代码 | 独立进程 |
| 共享 | 项目内部 | 可跨项目/跨语言 |
| 标准化 | 自定义 | MCP 标准协议 |

## 更多资源

- [MCP 官方文档](https://modelcontextprotocol.io)
- [MCP GitHub](https://github.com/modelcontextprotocol)
- [魔塔 MCP 广场](https://www.modelscope.cn/mcp) - 中文 MCP 服务器集合
- [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers) - MCP 服务器列表

---

[返回文档首页](../) | [上一章: Agent API](./agent.md)
