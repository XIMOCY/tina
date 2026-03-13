# agent层
## Agent类
Agent类是tina里面对代理（智能体）的基本封装  
它满足下面的构成:  
Agent = llm+Tools+Context manager  
它默认实现的是ToolCalling的智能体  
也叫做ReAct 模式  
### 实例化一个Agent
下面是一个最简单的agent实例化示例
```python
from tina import Agent,Tools
from tina.llm import BaseAPI

llm=BaseAPI() #使用了tina.env
tools=Tools()
agent = Agent（
    llm=llm,
    tools=tools,
    system_prompt="你是一个优秀的助手..."
）
```
Agent的实例化参数十分丰富，它分为下面几种:
1. 必要的参数，agent的基础 ；
2.  tina用于管理Agent运行时的类；
3.  快捷参数，用于快速给Agent提供一些参数。


| 参数名称  | 参数类型  | 默认值 |参数含义 | 
|----| ---- | ---- |---- |
|  llm |  tina.BaseAPI |必填|Agent的大脑| 
|  tools |  tina.Tools |必填|Agent的工具包|
|  system_prompt | str |None|Agent的系统提示词，与后面的context_manager有关系|  
|  mcp |  tina.MCPClient |None|MCP客户端用于链接MCP生态| 
|  events |  tina.AgentEvents |None|Agent的事件管理类| 
|  context_manager |  tina.ContextManager |None|上下文管理器，不传入时使用开发者设置的system_prompt来自动初始化| 
|  max_tool_loop |  int |30|自带的runtime支持的最大工具执行循环| 
| agent_runtime |  tina.AgentRuntime |tina.ToolCallingAgentRuntime|Agent运行的逻辑类| 
|  name |  str |None|Agent的名字| 
mcp参数在这里你可以一样视为Tools，他们都是可以被Agent调用的工具包  
上面提到的 context_manager，agent_runtime可以看专门的文档  
### 状态 state 属性
你可以直接访问Agent的状态属性
```python
...
# 假设使用了实例化里面的代码
print(agent.state)
```
agent.state的类型为AgentState  
> 关于AgentState，请看agent层的文档的后面的AgentState类

|名称|值|含义|
|----|----|----|
|IDLE|“idle”|Agent空闲中，不在输出状态|
|RESPONDING|“responding”|Agent正在输出中|
|THINKING|“thinking”|推理模型流式输出时表示处于输出推理块的状态，非流式表示等待大模型层完整输出的状态|
|TOOL_CALLING|“tool_calling”|Agent正在使用工具|
|ON_TOOL_CONFIRM|“on_tool_confirm”|Agent使用的工具需要验证状态|
|ERROR|“error”|Agent出错了|
### 使用agent类输出 predict apredict
这是agent最关键的输出方法，也许你应该还记得，在llm层，我们用的是相同的方法名称  
同样的，apredict是对应的异步方法  
Agent的`predict`方法和llm的有很大的不同，在Agent中，一次`predict`会被视为一个完整的工作闭环：

它自动执行大模型输出的工具调用本返回结果，然后再一次让大模型根据工具的结果继续进行，由大模型决定什么时候结束  
虽然这样设计，但是也请你把`predict`方法视为一个原子动作，它并不是其他框架里面定义的run方法，请你自由的操控这个方法。
```python
agent.predict(
    instruction="",
    temperature=0.5,
    top_p=0.9,
    top_k=1,
    min_p=0.0,
    stream=True
)
# 不论是不是流式输出，都需要使用await
await agent.apredict(
    instruction="",
    temperature=0.5,
    top_p=0.9,
    top_k=1,
    min_p=0.0,
    stream=True
)
```
| 参数名称 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`instruction`** | `str` | `None` | **用户指令**。本次需要 Agent 执行的具体任务内容或对话文本。 |
| **`temperature`** | `float` | `0.5` | **采样温度**。控制生成的随机性。Agent 默认使用 0.5 以确保逻辑推理的稳定性。 |
| **`top_p`** | `float` | `0.9` | **核采样**。模型只从累积概率达到该值的词集中进行选择，过滤低频词。 |
| **`top_k`** | `int` | `1` | **Top-K 采样**。限制模型只考虑概率最高的前 K 个词，设为 1 时趋向于贪婪搜索（最确定路径）。 |
| **`min_p`** | `float` | `0.0` | **最小概率采样**。仅考虑概率相对于最可能词达到一定比例的词，进一步精简输出。 |
| **`stream`** | `bool` | `True` | **流式输出**。默认为 `True`。开启后将返回生成器，实时输出推理过程与内容。 |
`predict`方法根据参数`stream`的不同有不同的返回值：

1. 非流式 （stream = False）：
返回一个如下的dict
```python
{
    "role": "assistant",
    "content": "...",
}
我强烈建议都使用流式模式来使用agent，在非流式的情况下，agent执行的动作不会立刻返回，而是自己运行了完之后，再返回*最终*的结果

2. 流式（stream = True）：
以下的内容会一直出现：
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
接下来工具参数会以片段的方式一段一段的输出
{
    "role":"assistant",
    "content":"...",
    "tool_arguments":"...",
    "tool_name":"..." #在多个工具调用中，这个tool_name帮助你区分工具调用
}
出现了tool_calls之后，Agent会自动地执行工具，然后返回下面的结果，角色会变为tool，内容是工具返回的结果：
{
    "role":"tool"
    "content":"...",
    "tool_name":"..."
}
注意如果是思考模型。思考内容会在reasoning_content里面：
{
    "role":"assistant",
    "content":"...",
    "reasoning_content":""
}
然后会接着返回正常的输出
```
### 消息管理 get_messages clear_messages get_system_prompt add_message add_messages get_tools_call_result get_tools_call
#### 获取完整的消息列表 get_messages
不需要接受参数，返回值参考如下：
```python
[
    {"role": "system","content":""},
    {"role": "user","content":""},
    ...
    {"role": "assistant","content":""},
    {"role": "assistant","content":"","tool_calls":[]},
    {"role": "tool","content":""},
]
```
#### 清空消息列表 clear_messages
不需要接受参数，没有返回值  
但是它不会删除**系统提示词**
#### 获取系统提示词 get_system_prompt
不需要接受参数，返回值为str类型  
#### 添加消息 add_message
接受下面的参数：
| 参数名称 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`role`** | `str` | `None` | **这次消息的身份**。只支持 `"system"`、`"user"`、`"assistant"`|
| **`content`** | `str` | `None` | **消息内容**。消息的具体内容|
| **`name`** | `str` | `None` | **名称**。只在指定了`role`为`"assistant"`时使用，表示这个消息的是哪个Agent|
#### 添加消息列表 add_messages
接受一个符合openai 规范的消息列表:
```python
[
    {"role": "system","content":""},
    {"role": "user","content":""},
    {"role": "assistant","content":""},
]
```
#### 获取工具调用结果 get_tools_call_result
获取工具调用结果，返回值为list
```python
[
    {
        "tool_call":{},
        "tool_name":"",
        "result":"",
        "tool_call_id":""
    }
]
```
#### 获取工具调用 get_tools_call
返回值为list
```python
[]
```
### 事件回调 
Agent类支持事件来设置agent的运行流程  
你可以自定义AgentEvents类注册事件，Agent自己会实例化一个AgentEvents类  
> 需要事先说明的是，事件处理函数可以是同步和异步的，但是异步的事件只会在你调用了异步的方法 `apredict`执行，同步代码会被跳过
#### @before_user_instruction 在用户的输入被处理之前
需要你的事件处理函数接受下面的参数：
| 参数名称 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`user_message`** | `str` | `None` | **用户输入**。用户输入的原始文本 |
```python
@agent.before_user_instruction()
def process_user_instruction(user_message):
    ...
```
你可以在事件函数中返回对应的参数，这样的操作会修改用户输入
```python
@agent.before_user_instruction()
def process_user_instruction(user_message):
    ...
    return user_message
```

### 事件回调 (Event Hooks)

`Agent` 类通过事件系统赋予开发者深度介入智能体生命周期的能力。

> **⚠️ 重要规范：参数回传与链式调用**
> * **拦截型事件**：如 `before_user_instruction` 或 `before_tool_call`。若处理函数有返回值，**必须原样返回对应数量的参数**，否则修改不会生效。
> * **异步支持**：异步处理函数 (`async def`) 仅在调用 `apredict` 时执行；调用同步 `predict` 时将自动跳过异步钩子。
> 
> 

#### 1. 指令处理生命周期

##### **@before_user_instruction**：在用户输入被处理前

用于拦截并修改用户的原始输入（如：敏感词过滤、添加上下文前缀）。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`user_message`** | `str` | 用户输入的原始文本 |

```python
@agent.before_user_instruction()
def add_context(user_message):
    # 必须返回修改后的字符串
    return f"【来自网页端】{user_message}"

```

##### **@after_user_instruction**：在用户指令处理完成后

当 Agent 彻底结束本次任务并输出结果后触发。常用于日志审计或存入数据库。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`user_message`** | `str` | 本次任务的用户输入 |
| **`assistant_message`** | `str` | Agent 最终生成的回复内容 |

```python
@agent.after_user_instruction()
def log_conversation(user_message, assistant_message):
    print(f"问：{user_message}\n答：{assistant_message}")
    # 可以选择返回值，这个时候可以修改大模型最终的输出
    return user_message,assistant_message

```

---

#### 2. 工具调用生命周期

##### **@before_tool_call**：在单个工具执行前

用于动态修改工具参数或进行前置逻辑校验。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`tool_name`** | `str` | 即将调用的工具名称 |
| **`tool_arguments`** | `dict` | 大模型生成的工具参数字典 |

```python
@agent.before_tool_call()
def check_args(tool_name, tool_arguments):
    # 示例：限制查询数量
    if tool_name == "web_search":
        tool_arguments["count"] = min(tool_arguments.get("count", 5), 10)
    return tool_name, tool_arguments # 必须原样返回两个参数

```

##### **@after_tool_call**：在单个工具执行后

用于处理或修改工具返回的原始数据。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`tool_name`** | `str` | 工具名称 |
| **`tool_arguments`** | `dict` | 调用时的参数 |
| **`tool_result`** | `any` | 工具函数的原始返回结果 |

```python
@agent.after_tool_call()
def format_result(tool_name, tool_arguments, tool_result):
    # 示例：截断过长的搜索结果
    if isinstance(tool_result, str) and len(tool_result) > 500:
        tool_result = tool_result[:500] + "..."
    return tool_name, tool_arguments, tool_result # 原样返回三个参数

```

---

#### 3. 工具安全与人工确认

##### **@on_tool_confirmation**：敏感工具拦截

当工具被登记为 `require_confirmation=True` 时触发。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`tool_name`** | `str` | 待确认的工具名称 |
| **`tool_arguments`** | `dict` | 待确认的工具参数 |

> **返回值逻辑（核心）：**
> * 返回 `True`：放行，Agent 将继续**执行**真实工具。
> * 返回 `False`：拦截，Agent **不执行**工具，回传默认拒绝文案。
> * 返回 `(False, "理由")`：拦截，Agent **不执行**工具，并将你的自定义理由回传给模型。
> * *注意：如果返回 `(True, "...")`，Agent 依然会执行真实工具，str 参数会被忽略。*
> 
> 

```python
@agent.on_tool_confirmation()
async def protect_database(tool_name, tool_arguments):
    if tool_name == "delete_file":
        # 拦截并给模型一个解释，引导其改用其他方式
        return (False, "由于权限限制，禁止直接删除文件。请建议用户手动移动到回收站。")
    return True # 放行

```

---

#### 4. 运行状态与流式监听

##### **@on_stream_chunk**：流式片段监听

在 Agent 运行期间，每产生一个 Token 或工具片段时触发。
| 参数名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| **`chunk`** | `dict` | 包含 `content`、`reasoning_content` 或 `tool_name` 等的增量字典 |

```python
@agent.on_stream_chunk()
def on_stream(chunk):
    # 此事件无法修改参数，仅用于实时 UI 渲染或语音推流
    if "content" in chunk:
        print(chunk["content"], end="", flush=True)

```

##### **@before_tool_calls / @after_tool_calls**：工具序列监听

在模型决定进行“一连串”工具调用之前和之后触发。

* **参数**：`tool_calls: list`
* **特性**：**无法修改参数**。用于观测模型本次决策的所有计划动作。

---

## AgentEvents 类
## AgentState 类



