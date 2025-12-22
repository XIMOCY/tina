# Agent API 文档

## 概述

`Agent` 是 tina 的智能体类,结合了 LLM 和 Tools,能够自动调用工具完成复杂任务。Agent 会自动维护消息历史和工具调用记录。

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

# 创建工具
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
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是一个有用的助手"
)

# 使用 Agent
for chunk in agent.predict("北京天气怎么样?"):
    print(chunk.get("content", ""), end="")
```

## Agent vs LLM

| 特性 | LLM | Agent |
|------|-----|-------|
| 工具调用 | 返回 tool_calls,需手动执行 | 自动执行工具 |
| 消息管理 | 需手动维护 | 自动维护 |
| 使用场景 | 简单对话 | 复杂任务,需要工具交互 |

## 初始化

```python
Agent(
    llm: BaseAPI,
    tools: Tools,
    system_prompt: str = None,
    execute_tool: bool = True,
    mcp: MCPClient = None,
    context_manager: ContextManager = None,
    agent_runtime: BaseAgentRuntime = None,
    max_tool_loop: int = 30,
    name: str = "None"
)
```

### 参数说明

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| llm | BaseAPI | 大语言模型实例 | 必需 |
| tools | Tools | 工具集实例 | 必需 |
| system_prompt | str | 系统提示词 | tina 默认 prompt |
| execute_tool | bool | 是否自动执行工具 | True |
| mcp | MCPClient | MCP 客户端实例 | None |
| context_manager | ContextManager | 上下文管理器(高级用法) | None |
| agent_runtime | BaseAgentRuntime | Agent运行时(高级用法) | None |
| max_tool_loop | int | 最大工具调用循环次数 | 30 |
| name | str | Agent名称,用于多Agent区分 | "None" |

### 示例

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

llm = BaseAPI()
tools = Tools()

# 最简单的 Agent
agent = Agent(llm=llm, tools=tools)

# 自定义系统提示词
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是一个专业的数据分析师"
)
```

## 核心方法

### predict()

执行预测任务,流式返回结果并自动执行工具。

```python
predict(
    instruction: str,
    temperature: float = 1.0,
    top_p: float = 0.9,
    top_k: int = None,
    min_p: float = None,
    stream: bool = True
) -> Generator[dict, None, None]
```

#### 参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| instruction | str | 用户指令 | 必需 |
| temperature | float | 采样温度 | 1.0 |
| top_p | float | 核采样参数 | 0.9 |
| top_k | int | Top-K采样 | None |
| min_p | float | Min-P采样 | None |
| stream | bool | 是否流式输出 | True |

#### 返回值

Agent 的输出比 LLM 更丰富,包含工具调用信息:

**1. 普通内容**

```python
{
    "role": "assistant",
    "content": "文本内容"
}
```

**2. 推理内容(推理模型)**

```python
{
    "role": "assistant",
    "content": "...",
    "reasoning_content": "推理过程"
}
```

**3. 工具名称(开始调用工具)**

```python
{
    "role": "assistant",
    "content": "",
    "tool_name": "get_weather"
}
```

**4. 工具参数(流式)**

```python
{
    "role": "assistant",
    "content": "",
    "tool_arguments": "{\"city\""  # 参数片段
}
```

**5. 完整工具调用**

```python
{
    "role": "assistant",
    "content": "",
    "tool_calls": [
        {
            "index": 0,
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": "{\"city\":\"北京\"}"
            },
            "id": "call_xxx"
        }
    ]
}
```

**6. 工具执行结果**

```python
{
    "role": "tool",
    "content": "北京今天晴,25度"
}
```

#### 使用示例

```python
# 基础使用
for chunk in agent.predict("现在几点?"):
    print(chunk.get("content", ""), end="")

# 监控工具调用
for chunk in agent.predict("北京天气怎么样?"):
    if "tool_name" in chunk:
        print(f"\n[调用工具: {chunk['tool_name']}]")
    elif "tool_calls" in chunk:
        print(f"\n[工具参数: {chunk['tool_calls']}]")
    elif chunk.get("role") == "tool":
        print(f"\n[工具结果: {chunk['content']}]")
    else:
        print(chunk.get("content", ""), end="")
```

### apredict()

异步版本的 `predict()`,参数相同。

```python
import asyncio

async def main():
    async for chunk in agent.apredict("你好"):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

## 消息管理方法

### get_messages()

获取当前消息历史。

```python
messages = agent.get_messages()
print(messages)
# [
#     {"role": "system", "content": "..."},
#     {"role": "user", "content": "..."},
#     {"role": "assistant", "content": "..."}
# ]
```

### add_message()

添加单条消息。

```python
agent.add_message(
    role="user",  # "user", "assistant", "system"
    content="这是一条消息"
)
```

**用途:**
- 手动注入系统指令
- 修改对话上下文
- 实现记忆功能

### add_messages()

批量添加消息。

```python
messages = [
    {"role": "user", "content": "消息1"},
    {"role": "assistant", "content": "回复1"}
]
agent.add_messages(messages)
```

### clear_messages()

清除所有消息(保留系统消息)。

```python
agent.clear_messages()
```

## 工具管理方法

### get_tools()

获取当前可用工具列表。

```python
tools_list = agent.get_tools()
print(tools_list)
```

### disable_tool()

禁用指定工具。

```python
# Agent 将无法使用 search 工具
agent.disable_tool("search")
```

**使用场景:**
- 某些场景下限制工具使用
- 动态控制 Agent 能力

### enable_tool()

重新启用已禁用的工具。

```python
agent.enable_tool("search")
```

### get_tools_call()

获取工具调用历史记录。

```python
calls = agent.get_tools_call()
# 返回所有 tool_calls 列表
```

### get_tools_call_results()

获取工具执行结果历史。

```python
results = agent.get_tools_call_results()
# 返回所有工具执行结果
```

## 系统方法

### get_system_prompt()

获取当前系统提示词。

```python
prompt = agent.get_system_prompt()
print(prompt)
```

## MCP 方法

### add_mcp_server()

添加 MCP 服务器。

```python
config = {
    "type": "stdio",
    "command": "npx",
    "args": ["@playwright/mcp@latest"]
}

agent.add_mcp_server(
    server_id="playwright",
    config=config
)
```

### remove_mcp_server()

删除 MCP 服务器。

```python
agent.remove_mcp_server("playwright")
```

### get_mcp_server_info()

获取 MCP 服务器信息。

```python
info = agent.get_mcp_server_info("playwright")
print(info)
```

## 完整示例

### 示例1: 天气助手

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

tools = Tools()

@tools.register()
def get_weather(city: str):
    """获取天气 Args: city: 城市名"""
    return f"{city}今天晴,25度"

@tools.register()
def get_forecast(city: str, days: int):
    """获取天气预报 Args: city: 城市名, days: 预报天数"""
    return f"{city}未来{days}天都是好天气"

llm = BaseAPI()
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是专业的气象助手"
)

print("=== 天气助手 ===")
for chunk in agent.predict("北京今天天气怎么样?未来3天呢?"):
    if "tool_name" in chunk:
        print(f"\n[使用工具: {chunk['tool_name']}]", flush=True)
    else:
        print(chunk.get("content", ""), end="", flush=True)
```

### 示例2: 多轮对话

```python
agent = Agent(llm=BaseAPI(), tools=Tools())

# 第一轮
print("用户: 推荐一部科幻电影")
for chunk in agent.predict("推荐一部科幻电影"):
    print(chunk.get("content", ""), end="")

# 第二轮(保持上下文)
print("\n\n用户: 它的导演是谁?")
for chunk in agent.predict("它的导演是谁?"):
    print(chunk.get("content", ""), end="")

# 查看历史
print("\n\n=== 对话历史 ===")
for msg in agent.get_messages():
    print(f"{msg['role']}: {msg['content'][:50]}...")
```

### 示例3: 动态控制工具

```python
tools = Tools()

@tools.register()
def sensitive_operation():
    """敏感操作"""
    return "执行了敏感操作"

@tools.register()
def safe_operation():
    """安全操作"""
    return "执行了安全操作"

agent = Agent(llm=BaseAPI(), tools=tools)

# 默认情况
agent.predict("执行一些操作")

# 禁用敏感工具
agent.disable_tool("sensitive_operation")
agent.predict("执行操作")  # 只会使用 safe_operation

# 重新启用
agent.enable_tool("sensitive_operation")
```

### 示例4: 工具链

```python
tools = Tools()

@tools.register()
def search_products(keyword: str):
    """搜索商品 Args: keyword: 关键词"""
    return f"找到商品: {keyword}手机"

@tools.register()
def get_price(product: str):
    """获取价格 Args: product: 商品名"""
    return f"{product}的价格是3999元"

@tools.register()
def compare_prices(product1: str, product2: str):
    """比较价格 Args: product1: 商品1, product2: 商品2"""
    return f"{product1}比{product2}便宜500元"

agent = Agent(llm=BaseAPI(), tools=tools)

# Agent 会自动形成工具调用链
for chunk in agent.predict("帮我搜索华为手机,看看价格,然后和小米比较一下"):
    if "tool_name" in chunk:
        print(f"\n[步骤: {chunk['tool_name']}]")
    elif chunk.get("role") == "tool":
        print(f"  结果: {chunk['content']}")
    else:
        print(chunk.get("content", ""), end="")
```

### 示例5: 异步 Agent

```python
import asyncio

async def main():
    tools = Tools()
    
    @tools.register()
    async def async_task(data: str):
        """异步任务 Args: data: 数据"""
        await asyncio.sleep(1)
        return f"处理完成: {data}"
    
    agent = Agent(llm=BaseAPI(), tools=tools)
    
    async for chunk in agent.apredict("处理一些数据"):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

## 最佳实践

### 1. 清晰的系统提示词

```python
system_prompt = """
你是一个专业的数据分析助手。

能力:
- 可以查询数据库
- 可以生成图表
- 可以进行统计分析

限制:
- 不要修改原始数据
- 所有操作需要用户确认
"""

agent = Agent(llm=llm, tools=tools, system_prompt=system_prompt)
```

### 2. 工具的合理组织

```python
# 按功能分组
data_tools = Tools()
viz_tools = Tools()

# 根据场景选择工具集
agent = Agent(llm=llm, tools=data_tools + viz_tools)
```

### 3. 监控工具调用

```python
tool_usage = []

for chunk in agent.predict("分析数据"):
    if "tool_name" in chunk:
        tool_usage.append(chunk["tool_name"])
        print(f"[使用工具 {len(tool_usage)}: {chunk['tool_name']}]")
    else:
        print(chunk.get("content", ""), end="")

print(f"\n共调用 {len(tool_usage)} 个工具: {tool_usage}")
```

### 4. 定期清理历史

```python
# 对话太长时清理
if len(agent.get_messages()) > 20:
    agent.clear_messages()
    agent.add_message("system", "之前的对话已清除,开始新对话")
```

### 5. 错误处理

```python
try:
    for chunk in agent.predict("执行任务"):
        print(chunk.get("content", ""), end="")
except Exception as e:
    print(f"\nAgent 执行失败: {e}")
    # 可以选择清理状态
    agent.clear_messages()
```

## 常见问题

### Q: Agent 不调用工具?

A: 检查:
1. 工具描述是否清晰
2. 系统提示词是否指导使用工具
3. 模型是否支持工具调用

```python
# 改进系统提示词
system_prompt = "你是助手,可以使用工具完成任务。遇到需要实时信息时主动使用工具。"
```

### Q: Agent 重复调用工具?

A: 工具返回值要清晰,让模型知道任务完成:

```python
@tools.register()
def get_time():
    """获取时间"""
    from datetime import datetime
    # 明确的返回
    return f"当前时间是: {datetime.now()}"
    # 而不是只返回时间戳
```

### Q: 如何限制工具调用次数?

A: 手动控制:

```python
max_calls = 3
call_count = 0

for chunk in agent.predict("执行任务"):
    if "tool_calls" in chunk:
        call_count += 1
        if call_count > max_calls:
            print("\n达到最大工具调用次数")
            break
```

### Q: 如何实现记忆功能?

A: 使用消息管理:

```python
# 保存对话到文件
import json

messages = agent.get_messages()
with open("memory.json", "w") as f:
    json.dump(messages, f)

# 恢复对话
with open("memory.json", "r") as f:
    messages = json.load(f)
agent.add_messages(messages)
```

## 进阶技巧

### 中间插入指令

```python
for chunk in agent.predict("分析数据"):
    if "tool_name" in chunk and chunk["tool_name"] == "dangerous_tool":
        # 插入警告
        agent.add_message("system", "警告: 这是敏感操作,请谨慎")
    print(chunk.get("content", ""), end="")
```

### 自定义工具执行逻辑

通过继承 Agent 类,可以自定义工具执行行为(高级用法,需查看源码)。

---

[返回文档首页](../) | [上一章: Tools API](./tools.md) | [下一章: MCP API](./mcp.md)
