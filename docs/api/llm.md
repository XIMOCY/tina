# LLM API 文档

## 概述

`BaseAPI` 类提供了统一的大语言模型调用接口,支持任何 OpenAI 兼容的 API 服务。

## 快速开始

```python
from tina.llm import BaseAPI

llm = BaseAPI(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-3.5-turbo"
)

result = llm.predict(input_text="你好")
print(result["content"])
```

## 初始化参数

```python
BaseAPI(
    api_key: str = None,
    base_url: str = None,
    model: str = None
)
```

### 参数说明

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| api_key | str | API 密钥 | 从 `tina.env` 读取 `LLM_API_KEY` |
| base_url | str | API 端点 URL | 从 `tina.env` 读取 `BASE_URL` |
| model | str | 模型名称 | 从 `tina.env` 读取 `MODEL_NAME` |

### 环境配置

推荐在项目根目录创建 `tina.env` 文件:

```env
LLM_API_KEY=sk-xxx
BASE_URL=https://api.openai.com/v1/chat/completions
MODEL_NAME=gpt-3.5-turbo
MAX_INPUT=8000
```

## 核心方法

### predict()

同步调用大语言模型执行预测任务。

```python
predict(
    input_text: str = None,
    sys_prompt: str = "你的工作非常的出色！",
    messages: list = None,
    temperature: float = 1.0,
    top_p: float = 0.9,
    top_k: int = None,
    min_p: float = None,
    max_tokens: int = None,
    presence_penalty: float = None,
    frequency_penalty: float = None,
    stream: bool = False,
    format: str = "text",
    json_format: str = "",
    tools: list = None,
    timeout: int = 180
) -> Union[dict, Generator]
```

#### 参数详解

**基础参数**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| input_text | str | 用户输入文本 | None |
| sys_prompt | str | 系统提示词 | "你的工作非常的出色！" |
| messages | list | 历史对话消息列表 | None |
| stream | bool | 是否启用流式响应 | False |

**采样参数**

| 参数 | 类型 | 说明 | 范围 | 默认值 |
|------|------|------|------|--------|
| temperature | float | 控制随机性,越高越随机 | 0.0-1.0 | 1.0 |
| top_p | float | 核采样,控制候选词汇多样性 | 0.0-1.0 | 0.9 |
| top_k | int | 限制候选词汇数量(部分模型不支持) | >0 | None |
| min_p | float | 最小概率阈值(较新参数,部分模型不支持) | 0.0-1.0 | None |

**输出控制参数**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| max_tokens | int | 最大生成 token 数量 | None |
| presence_penalty | float | 存在惩罚,鼓励谈论新话题 | None |
| frequency_penalty | float | 频率惩罚,减少重复内容 | None |

**格式化参数**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| format | str | 返回格式: "text" 或 "json" | "text" |
| json_format | str | JSON 格式模板 | "" |

**工具调用参数**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| tools | list | 工具调用列表 | None |
| timeout | int | 请求超时时间(秒) | 180 |

#### 返回值

**非流式模式 (stream=False)**

返回字典格式:

```python
{
    "role": "assistant",
    "content": "回复内容"
}
```

如果调用了工具:

```python
{
    "role": "assistant",
    "content": "...",
    "tool_calls": [
        {
            "index": 0,
            "type": "function",
            "function": {
                "name": "tool_name",
                "arguments": "{\"param\": \"value\"}"
            },
            "id": "call_xxx"
        }
    ]
}
```

如果是推理模型:

```python
{
    "role": "assistant",
    "content": "回复内容",
    "reasoning_content": "推理过程"
}
```

**流式模式 (stream=True)**

返回生成器,逐块yield字典:

```python
for chunk in llm.predict("你好", stream=True):
    print(chunk["content"], end="")
```

每个 chunk 的格式:

```python
{
    "role": "assistant",
    "content": "片段内容"
}
```

## 使用示例

### 单次对话

```python
from tina.llm import BaseAPI

llm = BaseAPI()

# 非流式输出
result = llm.predict(
    input_text="请帮我翻译: Hello tina",
    sys_prompt="你是一位专业的翻译家",
    stream=False
)
print(result["content"])
```

### 流式输出

```python
# 流式输出
result = llm.predict(
    input_text="讲个故事",
    stream=True
)

for chunk in result:
    print(chunk["content"], end="")
```

### 多轮对话

```python
messages = [
    {"role": "system", "content": "你是专业的翻译家"},
    {"role": "user", "content": "翻译: Hello"},
    {"role": "assistant", "content": "你好"},
    {"role": "user", "content": "翻译: Goodbye"}
]

result = llm.predict(messages=messages)
print(result["content"])
```

### 调整采样参数

```python
# 更有创意的输出
result = llm.predict(
    input_text="写一首诗",
    temperature=1.5,
    top_p=0.95,
    max_tokens=500
)
```

### JSON 格式输出

```python
result = llm.predict(
    input_text="介绍一下北京",
    format="json",
    json_format='{"city": "", "population": 0, "attractions": []}'
)
```

### 使用工具

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气信息",
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
]

result = llm.predict(
    input_text="北京天气怎么样?",
    tools=tools
)

if "tool_calls" in result:
    print(f"调用工具: {result['tool_calls'][0]['function']['name']}")
```

## apredict()

异步版本的 `predict()` 方法,参数完全相同。

```python
import asyncio
from tina.llm import BaseAPI

async def main():
    llm = BaseAPI()
    
    # 非流式
    result = await llm.apredict(input_text="你好")
    print(result["content"])
    
    # 流式
    async for chunk in llm.apredict(input_text="讲个故事", stream=True):
        print(chunk["content"], end="")

asyncio.run(main())
```

## 异常处理

```python
from tina.core.error import APIRequestFailed

try:
    result = llm.predict(input_text="你好")
except APIRequestFailed as e:
    print(f"API 调用失败: {e}")
```

## 最佳实践

### 1. 使用环境变量

```python
# 推荐: 使用 tina.env 文件
llm = BaseAPI()  # 自动读取环境变量

# 不推荐: 硬编码
llm = BaseAPI(api_key="sk-xxx", ...)
```

### 2. 流式输出提升体验

```python
# 长回复使用流式
for chunk in llm.predict("写一篇文章", stream=True):
    print(chunk["content"], end="", flush=True)
```

### 3. 合理设置超时

```python
# 复杂任务增加超时时间
result = llm.predict(
    input_text="分析这篇长文档...",
    timeout=300  # 5分钟
)
```

### 4. 控制输出长度

```python
# 避免过长回复
result = llm.predict(
    input_text="简单介绍一下",
    max_tokens=200
)
```

## 常见问题

### Q: 支持哪些模型?

A: 支持任何 OpenAI 兼容 API 的模型,包括:
- OpenAI (GPT-3.5, GPT-4, GPT-4-turbo 等)
- Azure OpenAI
- 国内大模型(通义千问、文心一言、豆包等提供 OpenAI 兼容接口的)
- 本地部署的模型(如使用 vLLM, ollama 等)

### Q: top_k 和 min_p 不生效?

A: 这些是较新的采样参数,部分老模型不支持。如果模型不支持会自动忽略。

### Q: 如何处理 token 超限?

A: 
```python
from tina.core.error import APIRequestFailed

try:
    result = llm.predict(input_text=very_long_text)
except APIRequestFailed as e:
    if "token" in str(e).lower():
        # 处理 token 超限
        print("输入过长,请分段处理")
```

### Q: 流式模式下如何获取完整回复?

A:
```python
full_response = ""
for chunk in llm.predict("你好", stream=True):
    content = chunk.get("content", "")
    full_response += content
    print(content, end="")
print(f"\n\n完整回复: {full_response}")
```

## 进阶使用

### 自定义请求头

如需自定义 HTTP 请求头,需要修改底层实现。建议提 Issue 讨论需求。

### 批量请求

```python
import asyncio

async def batch_predict():
    llm = BaseAPI()
    tasks = [
        llm.apredict(input_text=f"问题{i}")
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)
    return results

results = asyncio.run(batch_predict())
```

---

[返回文档首页](../) | [下一章: Tools API](./tools.md)
