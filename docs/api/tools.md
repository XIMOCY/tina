# Tools API 文档

## 概述

`Tools` 类是 tina 的工具管理系统,支持工具注册、管理和执行。核心特性是**注释即描述** - 自动解析 Google 风格注释生成工具定义。

## 快速开始

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

# 工具已注册,可供 Agent 使用
```

## 核心理念

### 注释即描述

tina 采用 Google 风格注释,自动提取工具信息:

```python
def function_name(param1: type1, param2: type2) -> return_type:
    """
    工具功能描述
    Args:
        param1: 参数1描述
        param2: 参数2描述
    """
    # 实现代码
    return result
```

**优势:**
- ✅ 一次编写,自动生成工具定义
- ✅ 代码即文档,工具信息始终同步
- ✅ 无需重复定义参数类型和描述

## 初始化

```python
from tina import Tools

# 基础初始化
tools = Tools()

# 高级:自定义工具执行器
from tina.agent.core.executor import ToolsExecutor
custom_executor = ToolsExecutor(parallel=True)
tools = Tools(tools_executor=custom_executor)
```

### 参数说明

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| tools_executor | ToolsExecutor | 工具执行器,控制工具如何执行 | ToolsExecutor(True) |

> 注意:大多数情况下使用默认的工具执行器即可,无需自定义。

## 工具注册方法

### 1. 装饰器注册(推荐)

最简洁的注册方式:

```python
@tools.register()
def add(a: int, b: int):
    """
    两个数字相加
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a + b
```

### 2. 手动注册

适合注册已有函数:

```python
def multiply(a: int, b: int):
    """
    两个数字相乘
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a * b

tools.register_tool(
    tool=multiply,
    description="计算两个数字的乘积"
)
```

### 3. 注册无实现工具

用于外部工具或占位符:

```python
tools.register_no_function(
    name="external_api",
    description="调用外部 API",
    required_parameters=["endpoint", "method"],
    parameters={
        "endpoint": {
            "type": "string",
            "description": "API 端点"
        },
        "method": {
            "type": "string",
            "description": "HTTP 方法"
        },
        "data": {
            "type": "object",
            "description": "请求数据"
        }
    }
)
```

## 同步与异步工具

### 同步工具

```python
@tools.register()
def sync_function(param: str):
    """
    同步工具示例
    Args:
        param: 参数描述
    """
    return f"处理: {param}"
```

### 异步工具

```python
@tools.register()
async def async_function(param: str):
    """
    异步工具示例
    Args:
        param: 参数描述
    """
    await asyncio.sleep(1)
    return f"异步处理: {param}"
```

**注意:**
- 使用 `llm.predict()` (同步方法)时,只能注册同步工具
- 使用 `llm.apredict()` (异步方法)时,可同时注册同步和异步工具

## 工具集管理

### 添加工具集

使用 `+` 或 `+=` 合并工具集:

```python
from tina.utils.system_tools import system_tools
from tina import Tools

my_tools = Tools()

@my_tools.register()
def custom_tool():
    """自定义工具"""
    pass

# 添加系统工具集
my_tools += system_tools

# 或
combined_tools = my_tools + system_tools
```

### 注销工具

```python
tools.unregister("tool_name")
```

## 工具执行

### execute() - 执行工具调用

```python
# 大模型返回的 tool_calls
tool_calls = [
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

# 执行工具
results = tools.execute(tool_calls=tool_calls)
print(results)  # ["北京今天晴,25度"]
```

**返回值:**

返回结果列表,按 `tool_calls` 的顺序:

```python
[
    "工具1执行结果",
    "工具2执行结果",
    ...
]
```

## 完整示例

### 示例1: 基础工具注册

```python
from tina import Tools

tools = Tools()

@tools.register()
def search_web(query: str):
    """
    搜索网络
    Args:
        query: 搜索关键词
    """
    # 实际实现可以调用搜索 API
    return f"搜索结果: {query}"

@tools.register()
def calculate(expression: str):
    """
    计算数学表达式
    Args:
        expression: 数学表达式,如 "2+2"
    """
    try:
        return str(eval(expression))
    except:
        return "计算错误"

@tools.register()
def get_time():
    """
    获取当前时间
    """
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

### 示例2: 异步工具

```python
import httpx

@tools.register()
async def fetch_url(url: str):
    """
    获取网页内容
    Args:
        url: 网页 URL
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text[:200]  # 返回前200字符
```

### 示例3: 复杂参数

```python
@tools.register()
def create_user(name: str, age: int, email: str, tags: list):
    """
    创建用户
    Args:
        name: 用户名
        age: 年龄
        email: 邮箱地址
        tags: 用户标签列表
    """
    user = {
        "name": name,
        "age": age,
        "email": email,
        "tags": tags
    }
    return f"创建用户成功: {user}"
```

### 示例4: 结合 Agent 使用

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

# 创建工具集
tools = Tools()

@tools.register()
def get_weather(city: str):
    """
    获取城市天气
    Args:
        city: 城市名称
    """
    return f"{city}今天晴朗,温度25度"

@tools.register()
def get_news(category: str):
    """
    获取新闻
    Args:
        category: 新闻分类,如 "科技"、"体育"
    """
    return f"{category}新闻: 今日头条..."

# 创建 Agent
llm = BaseAPI()
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt="你是一个有用的助手"
)

# Agent 会自动调用工具
for chunk in agent.predict("北京天气怎么样?"):
    if "tool_name" in chunk:
        print(f"\n[使用工具: {chunk['tool_name']}]")
    else:
        print(chunk.get("content", ""), end="")
```

## 工具定义格式

工具会被转换为 OpenAI 兼容的工具定义格式:

```python
{
    "type": "function",
    "function": {
        "name": "function_name",
        "description": "功能描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数1描述"
                },
                "param2": {
                    "type": "integer",
                    "description": "参数2描述"
                }
            },
            "required": ["param1"]
        }
    }
}
```

## 类型映射

Python 类型自动映射到 JSON Schema 类型:

| Python 类型 | JSON Schema 类型 |
|------------|-----------------|
| str | string |
| int | integer |
| float | number |
| bool | boolean |
| list | array |
| dict | object |

## 系统内置工具

tina 提供了一些内置工具:

```python
from tina.utils.system_tools import system_tools
```

内置工具包括:
- 时间相关工具
- 文件操作工具
- 其他实用工具

## 最佳实践

### 1. 清晰的工具描述

```python
@tools.register()
def send_email(to: str, subject: str, body: str):
    """
    发送邮件
    Args:
        to: 收件人邮箱地址,必须是有效的邮箱格式
        subject: 邮件主题,不超过100字符
        body: 邮件正文,支持HTML格式
    """
    # 实现...
```

### 2. 类型注解

```python
# 推荐: 有类型注解
@tools.register()
def process_data(data: dict, threshold: float) -> str:
    """..."""
    pass

# 不推荐: 无类型注解
@tools.register()
def process_data(data, threshold):
    """..."""
    pass
```

### 3. 错误处理

```python
@tools.register()
def safe_divide(a: float, b: float):
    """
    安全除法
    Args:
        a: 被除数
        b: 除数
    """
    try:
        return a / b
    except ZeroDivisionError:
        return "错误: 除数不能为0"
    except Exception as e:
        return f"错误: {str(e)}"
```

### 4. 返回值规范

```python
# 推荐: 返回字符串或可序列化对象
@tools.register()
def get_user(user_id: int):
    """获取用户信息"""
    return {
        "id": user_id,
        "name": "张三"
    }

# 不推荐: 返回复杂对象
@tools.register()
def get_user_object(user_id: int):
    """获取用户对象"""
    return UserObject(user_id)  # Agent 无法处理
```

## 常见问题

### Q: 工具描述不够详细,模型调用不准确?

A: 在函数文档字符串和参数描述中提供更多细节:

```python
@tools.register()
def book_flight(departure: str, destination: str, date: str):
    """
    预订航班。注意:需要提供完整的城市名称或机场代码。
    Args:
        departure: 出发城市或机场代码,如 "北京" 或 "PEK"
        destination: 目的地城市或机场代码,如 "上海" 或 "SHA"  
        date: 日期,格式为 YYYY-MM-DD,如 "2024-03-15"
    """
    pass
```

### Q: 如何处理可选参数?

A: 使用默认值:

```python
@tools.register()
def search(query: str, limit: int = 10, category: str = "all"):
    """
    搜索内容
    Args:
        query: 搜索关键词(必需)
        limit: 返回结果数量(可选,默认10)
        category: 搜索分类(可选,默认"all")
    """
    pass
```

### Q: 工具执行失败怎么办?

A: 工具内部应处理异常并返回错误信息,Agent 会将错误信息反馈给模型。

### Q: 如何查看已注册的工具?

A:
```python
# 获取工具定义列表
tool_definitions = tools.get_tools_definitions()
print(tool_definitions)

# 获取工具名称列表
tool_names = [t["function"]["name"] for t in tool_definitions]
print(tool_names)
```

## 进阶技巧

### 动态工具生成

```python
def create_calculator_tool(operation: str):
    """动态创建计算工具"""
    @tools.register()
    def calc(a: float, b: float):
        f"""
        {operation}运算
        Args:
            a: 第一个数字
            b: 第二个数字
        """
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
    return calc

# 创建多个运算工具
create_calculator_tool("add")
create_calculator_tool("subtract")
```

### 工具链

```python
@tools.register()
def step1(input_data: str):
    """第一步处理"""
    return f"Step1处理: {input_data}"

@tools.register()
def step2(step1_result: str):
    """第二步处理,依赖第一步结果"""
    return f"Step2处理: {step1_result}"

# Agent 可以自动形成工具调用链
```

---

[返回文档首页](../) | [上一章: LLM API](./llm.md) | [下一章: Agent API](./agent.md)
