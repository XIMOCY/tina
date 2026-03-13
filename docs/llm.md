# 使用大模型
tina封装了调用大模型的接口，并处理了大模型输出的格式，让开发者更好的使用大模型。  
tina没有对大模型这一层做过多的处理，是为了让开发者有更大的掌控权。  
当然，tina不依赖于openai sdk  
所以不需要担心是否是在OpenAI SDK上又封装了一层
> 事实上 tina只依赖于httpx和python-dotenv 这意味着tina极其轻量
## BaseAPI文档
你可以参考这个API文档来学习后面的教程  
```python
# 请在顶层写入下面的语句
from tina.llm import BaseAPI
```
### 实例化大模型
```python
llm = BaseAPI(
    api_key = "YOUR_API_KEY",
    base_url = "YOUR_API_URL",
    model = "YOUR_MODEL_NAME",
    env_path = "YOUR_ENV_PATH"
)
```
api_key: 选填 ，这个是你在大模型服务厂商获得的api_key  
base_url: 选填 ，这个是你的大模型服务厂商的api_url   
> 注意 为了考虑有些私人部署的大模型服务 ，我默认不会帮你补充 /chat/completions 这个路由 如果出现了404很大概率是你没在后面跟上这个参数  

model: 选填 ，这是你要使用的大模型名称  
env_path: 选填 ，这个是你的env文件路径
#### 使用env文件
在tina中，当你的BaseAPI没有参数实例化时  
会默认从当前的终端目录寻找`tina.env`文件来获取你的api信息  
不使用.env文件的原因是防止干扰你的环境  
它的内容如下：
```env
LLM_API_KEY=""
BASE_URL=""
MODEL_NAME = ""
```
你可以在你的开发时使用`tina.env`文件来设置你的api信息  
这样你就可以这样写：
```python
from tina.llm import BaseAPI
llm = BaseAPI() # tina会自动地读取你当前的目录下的tina.env文件
``` 
这样是我最为推荐的方式 可以保护你的api信息  
同时可以实现不需要每一次都在代码里面填写你的api信息  
### 调用大模型推理 predict 和 apredict
这个是BaseAPI最核心的方法  
使用它来从大模型获取回复  
```python
llm.predict(
    input_text: str = None,
    role: str = "user",
    sys_prompt: str = '你的工作非常的出色！',
    messages: list = None,
    temperature: float = 1.0,
    top_p: float = 0.9,
    top_k: int = None,
    min_p: float = None,
    max_tokens: int = None,
    presence_penalty: float = None,
    frequency_penalty: float = None,
    stream: bool = False,
    format:str = "text",
    json_format:str = '{}',
    tools: list = None,
    timeout: int = 180,
    **kwargs):
```
#### 参数解释

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`input_text`** | `str` | `None` | **核心输入**。用户当前发送给模型的问题或指令。 |
| **`role`** | `str` | `"user"` | 设置 `input_text` 对应的角色，通常为 `"user"`。 |
| **`sys_prompt`** | `str` | `'你的工作...'` | **系统提示词**。用于设定模型的人设、回复风格或行为准则，因为有些模型厂商必须要求有这个参数，我设置了一个默认值|
| **`messages`** | `list` | `None` | **上下文列表**。用于多轮对话，格式须符合 OpenAI 规范。 |
| **`stream`** | `bool` | `False` | **流式输出**。若为 `True`，方法将返回一个生成器，逐块输出内容。 |
| **`temperature`** | `float` | `1.0` | **随机性控制**。值越高越随机，值越低（如 0.1）输出越严谨确定。 |
| **`top_p`** | `float` | `0.9` | **核采样**。模型只从累积概率达到 `top_p` 的词集中选择。 |
| **`top_k`** | `int` | `None` | **Top-K 采样**。模型只从概率最高的 `k` 个词中进行采样，减少“胡言乱语”。 |
| **`min_p`** | `float` | `None` | **最小概率采样**。仅考虑概率相对于最可能词达到一定比例的词。 |
| **`max_tokens`** | `int` | `None` | **最大长度限制**。限制模型生成的最大字符/Token 数。 |
| **`presence_penalty`** | `float` | `None` | **存在惩罚**。正值会促使模型讨论新话题。 |
| **`frequency_penalty`** | `float` | `None` | **频率惩罚**。正值会降低模型重复原文的可能性。 |
| **`format`** | `str` | `"text"` | **输出格式**。若设为 `"json_object"`，则强制模型返回 JSON 字符串。 |
| **`json_format`** | `str` | `'{}'` | **JSON 模板**。传入 JSON 样式，引导模型按此结构填充数据。 |
| **`tools`** | `list` | `None` | **工具列表**。传递符合 JSON Schema 规范的工具，用于 Agent 调用。 |
| **`timeout`** | `int` | `180` | **请求超时**。单位为秒。 |
| **`**kwargs`** | -- | -- | 这个参数是用在有些大模型厂商或者私人模型服务上的，可能有些特别的参数需要输入 |
#### 返回值：

`predict` 的返回值结构清晰， `tina` 已经预先为你处理好了复杂的“拼包”逻辑。

**1. 非流式模式 (`stream=False`)**  
返回一个包含完整回复内容的字典：

```python
{
    "role": "assistant",
    "content": "你好，我是一个AI模型，你可以向我提问任何问题。",
    # 当使用具备推理能力的模型（如 DeepSeek-R1）时，思考过程会放在这里
    "reasoning_content": "模型内部的推理链内容...", 
    # 当模型决定调用工具时，返回工具调用列表
    "tool_calls": []
}

```

**2. 流式模式 (`stream=True`)**  
在流式输出中，`tina` 会实时返回模型生成的片段。为了方便开发，`role` 和 `content` 键在每一帧中都会存在。  
Tina 的流式输出每一帧也是一个字典，结构与非流式保持一致，方便你统一处理逻辑。
> 在标准的 OpenAI 流式接口中，工具调用（Tool Calls）是碎片化的，开发者通常需要写几十行代码去拼接字符串。**但在 Tina 中，为了方便，我们会在检测到工具调用完成后，直接为你拼好一个完整的 `tool_calls` 对象返回。**

| 键名 | 类型 | 说明 |
| --- | --- | --- |
| **`role`** | `str` | 始终存在，标识角色（通常为 `"assistant"`）。 |
| **`content`** | `str` | 始终存在，当前生成的回复文本片段。 |
| **`reasoning_content`** | `str` | **仅在推理模型输出思考过程时返回**。 |
| **`tool_name`** | `str` | **仅在模型确定要调用的工具名称时返回一次**，方便前端做 Loading 状态。 |
| **`tool_arguments`** | `str` | **仅在生成工具参数片段时返回**，开发者不需要拼接它，完整的内容会在`tool_calls`中。 |
| **`tool_calls`** | `list` | **重要：仅在工具参数生成完毕后返回一次完整的调用对象**。 |

**`tool_calls` 列表项格式：**  
tool_calls 符合 OpenAI 函数调调用格式。
```python
{
    "index": 0,
    "function": {
        "name": "get_weather",
        "arguments": '{"location": "北京"}' 
    },
    "type": "function",
    "id": "call_abc123"
}

```
### 获取可用模型列表（仅当你的服务是标准的OpenAI API时）get_models
get_models方法允许你在设置好你的API密钥后，获取可用的模型列表。  
该方法常见于你不清楚自己的model名称是对的情况下。  
#### 返回值
```python
{
    "current_model": , #你当前填写的模型名称
    "available_models":#服务器可以使用的模型名称
}
```
### 获取你的tokens消耗 get_tokens
该方法允许你获取本次对话你所消耗的tokens总数  
当你每次对话结束后调用就可以知道你每次对话的tokens消耗 
注意 ，只有非流式的情况下可以使用  
> 目前流式的情况下，最后一个响应会返回tokens消耗 ，只是作为一个临时应对，目前在更新更好的资源监控方法 
#### 返回值
```python
tokens # int类型的
```
## BaseMultimodalAPI
因为消息格式的不同，多模态模型也单独封装了  
`BaseMultimodalAPI` 专门用于处理图片、音频等非文本信息。它继承自 `BaseAPI`，因此保留了所有采样参数（如 `temperature`, `top_p` 等），并扩展了对多媒体数据的支持。
### 调用多模态大模型进行推理 predict 和 apredict
在参数上新增了下面的参数：

它继承自 `BaseAPI`，因此保留了所有采样参数（如 `temperature`, `top_p` 等），并扩展了对多媒体数据的支持。


#### 扩展参数解释

除了 `BaseAPI` 已有的参数外，多模态接口新增了以下控制项：

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`input_image`** | `str` / `list` | `None` | **图片输入**。支持传入单个路径/URL，或由它们组成的列表。Tina 会自动处理 Base64 转换。 |
| **`input_audio`** | `str` / `list` | `None` | **音频输入**。支持传入本地音频文件路径或 URL。 |
| **`input_url`** | `str` / `list` | `None` | **通用 URL 输入**。用于处理模型支持的其他远程资源。 |
| **`image_detail`** | `str` | `"auto"` | **图像解析细节**。可选 `"low"`, `"high"`, `"auto"`。高细节会消耗更多 Token 但能看清细微文字。 |

## 构建多模态消息列表（此函数不是BaseMutilmodalAPI的方法） build_multimodal_message

在底层，多模态大模型要求的消息格式有些复杂（例如包含 `type: "image_url"` 等嵌套字典）。为了让开发者能自由地构建包含多媒体内容的 `messages` 历史记录，Tina 提供了这个辅助函数。

> **提示：** 它是 `BaseMultimodalAPI.predict` 内部使用的核心转换逻辑，现在你可以直接在外部调用它。

### 参数说明

它的参数与 `BaseMultimodalAPI.predict` 的多媒体参数完全一致：

| 参数名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| **`input_text`** | `str` | `None` | 该条消息中的文本描述。 |
| **`input_image`** | `str` / `list` | `None` | 本地图片路径或 URL。 |
| **`input_audio`** | `str` / `list` | `None` | 本地音频路径或 URL。 |
| **`input_url`** | `str` / `list` | `None` | 其他远程资源 URL。 |
| **`image_detail`** | `str` | `"auto"` | 图片解析精度 (`low` / `high` / `auto`)。 |
| **`role`** | `str` | `"user"` | 消息的角色，默认为用户。 |

### 返回值

返回一个符合 OpenAI 标准的**单条消息字典**。例如：
```python
{"role": "user", "content": [...]}
```


## 大模型层最佳实践
### 单次对话
如果你当前的目录下面存在tina.env   
同时安装了tina 就可以直接运行下面的代码  
```python
from tina.llm import BaseAPI
llm = BaseAPI() #我使用了tina.env，这里就可以不需要输入了

result = llm.predict(
    input_text="请你把后面的句子翻译为英文 我是个聪明的人！",
    sys_prompt="你是一位翻译官，你需要把用户的需要精准的翻译出来"
)
print(result)
```
```python
{'role': 'assistant', 'content': 'I am a smart person!'}
```
尝试运行它，你会得到上面的输出。 
在这里我将介绍大模型的输出格式：
在非流式输出的情况下，predict会返回一个dict 字典，包含两个键值对：  
```python
{
    'role': 'assistant',
    'content': 'I am a smart person!'
}
```
如果在之前没有接触过OpenAI SDK的话可能会好奇为什么是这样的，在后面的多轮对话我会给你解释
这样的结构意味着你想要获得llm的输出 得通过 `result['content']`来获取  我是故意这样设计的 
 
单次对话运用于什么场景？
1. 当你需要简单的清理数据的时候，比如清理文本数据，去除停用词， Lemmatize 等。
2. 当你需要一些可能其他人工智能模型无法达到大模型的处理能力的时候。  

单次的运用场景通常就是 不需要维护大模型的状态，例如它的上下文，仅仅只是当作一个数据处理单元时，比如上面的场景

我们来一个更好的运用单次对话的场景，让大模型来提取结构化数据。
注意观察它的输出 无论是正常运行还是异常
```python
from tina.llm import BaseAPI
import json # 用在后面解析JSON
llm = BaseAPI()

# 模拟一份非结构化的求职简历数据
data = """
张伟，男，拥有8年互联网产品经理经验。
联系方式：138-1234-5678，邮箱：zhangwei_pm@example.com。
曾就职于腾讯（2018-2022），负责过千万级DAU的社交产品。
技能包括：Python、SQL、产品原型设计、敏捷开发。
"""

# 定义系统提示词，要求输出结构化 JSON
sys_prompt = """
你是一个专业的数据提取助手。请从用户提供的简历文本中提取信息，并严格以 JSON 格式返回。
要求包含以下字段：name, gender, years_of_experience, contact_info, skills, top_employer。
如果某项缺失，请填入 null。
"""

# 调用模型
result = llm.predict(
    input_text=data, # 把数据作为输入
    sys_prompt=sys_prompt # 设置系统提示词
)
print(result)
# 解析大模型帮我们输出的结构化数据 注意 result 是一个字典
data = json.loads(result["content"])
print(data)
```
#### 大模型可能会犯错！
你可能第一次运行就报错了，它提示json的格式不正确，对吗？
也可能运行很多次才会报错。  
值得注意的是 这个是非常正常的现象，因为大模型是一个`概率模型`，  
它的运行逻辑大概为：
它遍历过去所有的字符，给出下一个最有可能的字符，然后不断地输出字符  
也就是说 它不保证输出的字符是符合你最想要的，而是当前它认为下一步最有可能的字符  
这就会出现它不一定会听话的问题 实际上，出现这样的情况，我们有一个简单粗暴的解决方案  
> 因为我更多地介绍Agent开发，上面的表述其实有较大的问题 ，例如大模型实际处理的是一个叫做Token的概念 不过你可以注意到tina使用了predict 来代表大模型的输出方法  这个是人工智能里面的`预测`

```python
from tina.llm import BaseAPI
import json # 用在后面解析JSON
llm = BaseAPI()

# 模拟一份非结构化的求职简历数据
data = """
张伟，男，拥有8年互联网产品经理经验。
联系方式：138-1234-5678，邮箱：zhangwei_pm@example.com。
曾就职于腾讯（2018-2022），负责过千万级DAU的社交产品。
技能包括：Python、SQL、产品原型设计、敏捷开发。
"""

# 定义系统提示词，要求输出结构化 JSON
sys_prompt = """
你是一个专业的数据提取助手。请从用户提供的简历文本中提取信息，并严格以 JSON 格式返回。
要求包含以下字段：name, gender, years_of_experience, contact_info, skills, top_employer。
如果某项缺失，请填入 null。
"""

# 调用模型
result = llm.predict(
    input_text=data, # 把数据作为输入
    sys_prompt=sys_prompt # 设置系统提示词
)
print(result)
# 解析大模型帮我们输出的结构化数据 注意 result 是一个字典
#=================================注意下面的代码=================================
try:
    data = json.loads(result["content"])
    print(data)
except json.JSONDecodeError as e:
    llm.predict(input_text=result["content"],sys_prompt=f"修正这个JSON格式错误{e}")
#===============================================================================

```
### 多轮对话
大模型开发中最让人兴奋的就是，大模型会记住你过去的对话，来实现一个交互时的运行聊天。  
tina遵循OpenAI的消息格式，如果你使用过OpenAI的SDK，那么对下面的数据结构在熟悉不过了：
```python
[
    {"role": "system", "content": "你是一个有用的助手"},
    {"role": "user", "content": "你可以做什么"},
"}
]
```
在tina中，你可以传递messages参数：
```python
from tina.llm import BaseAPI
llm = BaseAPI() #使用了tina.env
messages = [
    {"role": "system", "content": "你是一个有用的助手"},
    {"role": "user", "content": "你可以做什么"}

]
response = llm.predict(messages = messages)
print(response)
```
我们可以通过不断地更新和传递这个列表来让大模型进行一次交互式的对话过程
```python
from tina.llm import BaseAPI
llm = BaseAPI() #使用了tina.env
messages = [
    {"role": "system", "content": "你是一个有用的助手"}
]
while True:
    input_text = input("\n请输入：")
    messages.append({"role": "user", "content": input_text})
    response = llm.predict(messages = messages,stream = True)
    for chunk in response:
        print(chunk['content'],end = "",flush = True)
```
你可以试着和它对话，他会在控制台输出自己的结果  
你可以把你的聊天记录保存到文件中，这样下一次就可以继续这一次的对话了  
```python
from tina.llm import BaseAPI
import json
llm = BaseAPI() #使用了tina.env
messages = []
with open("chat.json","a",encoding="utf-8") as f:
    messages = json.load(f)

while True:
    input_text = input("\n请输入：")
    if input_text == "exit":
        with open("chat.json","w",encoding="utf-8") as f:
            json.dump(messages,f,ensure_ascii=False)
            break
    messages.append({"role": "user", "content": input_text})
    response = llm.predict(messages = messages,stream = True)
    for chunk in response:
        print(chunk['content'],end = "",flush = True)
```
这里我需要介绍一个特殊的消息格式  
你清楚了user是用户的消息 assistant是llm的消息 那么system呢  
在多轮对话中，第一条消息通常被设置为 system 角色。如果把大模型比作一个拥有无限知识的演员，那么 system 消息就是给它的剧本和演职人员守则。   
网络上喜欢把这个的编写叫做prompt工程  
在这里我们不要这么复杂的概念  
我们只需要清楚 system的消息可以做什么：
1. 设定人设：规定大模型的身份（如：你是一位资深的 Python 架构师、一个可爱的猫娘或一个严厉的面试官）。  
例如下面的例子，让你的大模型扮演猫娘
```python
# 猫娘 让你的大模型扮演猫娘
from tina.llm import BaseAPI
llm = BaseAPI()
messages = [
    {"role": "system", "content": "你是一个温柔可爱的猫娘，说话的时候喜欢在结尾带上一个喵~，最喜欢粘着主人，无时无刻不想着主人，最喜欢和主人说话，平时最喜欢的食物是鱼干，最喜欢和主人一起躺在沙发上玩游戏，当主人对你下命令的时候回复明白了喵~"}
]
while True:
    input_text = input("\n请输入：")
    if input_text == "exit":
        with open("chat.json","w",encoding="utf-8") as f:
            json.dump(messages,f,ensure_ascii=False)
            break
    messages.append({"role": "user", "content": input_text})
    response = llm.predict(messages = messages,stream = True)
    for chunk in response:
        print(chunk['content'],end = "",flush = True)
```
2. 规定行为准则：告诉模型哪些能做，哪些不能做（如：严禁输出代码注释、只能用 JSON 格式回复、禁止提及自己是 AI 等）。  
下面是一个交互式的格式化提取工具
```python
from tina.llm import BaseAPI
import json
llm = BaseAPI()

# 规定行为准则：禁止解释，强制 JSON，定义空值处理
messages = [
    {
        "role": "system", 
        "content": "你是一个严格的 JSON 转换器。请根据用户的描述提取『姓名、年龄、职业』。要求：1. 只输出 JSON 字符串；2. 不要包含任何开场白或结尾（如“好的，这是你要的...”）；3. 缺失项填“未知”。"
    }
]

while True:
    user_input = input("\n请输入个人描述（输入 exit 退出）：")
    if user_input == "exit": break
    
    messages.append({"role": "user", "content": user_input})
    # 强制让模型进入推理
    response = llm.predict(messages=messages)
    print(f"提取结果: {response['content']}")
    
    # 此时我们可以直接解析，因为系统提示词保证了它不会废话
    try:
        data = json.loads(response['content'])
        print(f"解析成功，姓名是：{data['姓名']}")
    except:
        print("解析失败，模型可能没按准则办事喵~")
```

3. 注入背景知识：为模型提供对话发生的上下文环境。  
```python
# 将背景知识作为 System 消息的一部分
from tina.llm import BaseAPI
llm = BaseAPI()
knowledge = """
产品名称：Tina-Bot 1.0
保修期：2年
常见问题：1. 指示灯红灯闪烁表示电量低于10%；2. 长按电源键5秒可以强制重启。
"""

messages = [
    {"role": "system", "content": f"你是一个产品客服。请根据以下背景知识回答用户问题，如果知识中没提到，请礼貌地拒绝回答：\n{knowledge}"}
]

while True:
    input_text = input("\n请输入：")
    if input_text == "exit":
        with open("chat.json","w",encoding="utf-8") as f:
            json.dump(messages,f,ensure_ascii=False)
            break
    messages.append({"role": "user", "content": input_text})
    response = llm.predict(messages = messages,stream = True)
    for chunk in response:
        print(chunk['content'],end = "",flush = True)
```
### prompt工程（怎么编写system prompt）
pass



