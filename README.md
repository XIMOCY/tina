# tina
这是一个简单的agent库，是我在大二时编写的，同时作为我的Python练习项目

# 如何使用？
在我的库里，Agent需要LLM（大语言模型）作为驱动，Tools类管理工具，prompt类管理提示

因为暂时没有whl文件，请拉取代码后，作为本地库使用。

# 下面是一些示例步骤：

1. 初始化文件夹管理类
2. 初始化一个LLM对象
3. 初始化一个Tools对象
4. 初始化一个prompt对象
5. 初始化Agent对象

# 示例代码

```python
from tina.core.manage import TinaFolderManager
from tina.core.LLM.tina import tina
from tina.core.tools import Tools
from tina.core.prompt import Prompt
from tina.Agent import Agent

# 初始化工作路径
work_path = r"【你的工作路径】"
TinaFolderManager.init(work_path)

# 初始化LLM对象
llm = tina(
    path=r"【你的模型路径】",  # 注意是gguf格式的模型
    context_length=10240  # 这是模型的上下文长度，可以根据自己的模型调整
)

# 初始化Tools对象
tools = Tools()

# 初始化prompt对象
prompt = Prompt()

# 示例工具列表
tools_list = [
    {
        "name": "query",
        "description": "在用户的文档里面查询相关内容，该工具直接和用户的文档相关联，当你想查询的时候直接调用就好了",
        "required_parameters": ["query_text"],
        "parameters": {
            "query_text": {"type": "str", "description": "要查询的文本"},
            "n": {"type": "int", "description": "返回的结果数量,默认为10"}
        },
        "path": "【该工具的路径】"
    },
    {
        "name": "getTime",
        "description": "获取当前时间",
        "required_parameters": [],
        "parameters": {},
        "path": "【该工具的路径】"
    },
    {
        "name": "shotdownSystem",
        "description": "关闭系统原理是直接调用shotdown命令，该命令会关闭系统，请再次询问用户是否确认关闭，再使用，请谨慎使用",
        "required_parameters": [],
        "parameters": {},
        "path": "【该工具的路径】"
    }
]

# 使用tools.multiregister方法注册工具
tools.multiregister(tools_list)

# 初始化Agent对象
agent = Agent(
    LLM=llm,
    tools=tools,
    prompt=prompt,
    is_tool_call_permission=False  # 是否验证工具安全性，默认是False，不验证
)

# 主循环
if __name__ == "__main__":
    while True:
        input_text = input(">>> 王出日: ")
        output = agent.predict(input_text, stream=True)  # 当stream=True时，返回的是一个生成器
        print("\n>>> tina:")
        for chunk in output:
            print(chunk, end="", flush=True)
        print("\n")
```

### 依赖安装
通过 `pip install -r requirements.txt` 安装依赖。

以下是我使用的依赖：
- diskcache==5.6.3
- faiss-cpu==1.9.0.post1
- Jinja2==3.1.5
- lxml==5.3.0
- MarkupSafe==3.0.2
- numpy==2.2.1
- packaging==24.2
- PyPDF2==3.0.1
- python-docx==1.1.2
- setuptools==75.1.0
- typing_extensions==4.12.2
- wheel==0.44.0
- llama_cpp_python==0.3.4

### 为什么叫tina
- 因为我和朋友取了这个名字，虽然一眼看过去好像不知道做什么的？

### 如何使用
- 我暂时没有提交到pypi上，因为现在功能太少和稚嫩了。

### 使用GPU加速推理
- 需要你手动删除cpu版本的llama.cpp，然后安装使用vulkan或者cuda支持的llama-cpp-python
- 如果使用cuda，请确保你的电脑安装了cuda工具包
- llama-cpp-python提供了cuda版本预编译版本，index-url 为 `https://abetlen.github.io/llama-cpp-python/whl/cu[cuda版本号]`
- 一定要指定版本号，例如cu124的安装示例如下：
  ```bash
  pip install llama-cpp-python==0.3.4 --index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
  ```