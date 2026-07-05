# 如何安装tina

```bash
pip install tina-python
```
如果需要使用MCP服务(MCP即模型上下文协议)
```bash
pip install tina-python[mcp]
```
## 源代码
tina需要以下依赖：
```
最基础的依赖：
httpx
dotenv
使用MCP服务：
mcp-python
```
```bash
cd [源代码文件夹]
pip install -r requirements.txt
```
# tina是什么?
tina是一个简单的基于大模型的智能体库，

一开始使用的OpenAI SDK，后面想要扩展功能的时候使用了LangChain 发现我想要的功能介于这两种之间
有的时候也许我只想要调用一个大模型获得一个输出，用不着其他的很多功能，而且使用方式不是很符合我的直觉，所以我自己用httpx自己封装了一个简单的库

你可以用它来做一个快速的大模型应用的原型验证，当然她只是我一个大学的兴趣使然开发的一个产物，做我练习python的作品，如果追求稳定请去使用langchain等成熟的框架哦
# 快速开始
下面是一个参考代码，教你快速的在控制台运行一个可以对话和使用工具的Agent  
```python
# 保存在my_agent.py文件中
from tina import Agent,Tools # 导入Agent组件和Tools组件
from tina.llm import BaseAPI #导入基于OpenAI API的BaseAPI组件 它负责使用大模型
llm = BaseAPI(
    api_key = "", #你申请的大模型API key
    base_url = "", #如果你是获取的OpenAI格式的Base_url 请在后面自行添加 /chat/completions
    model = "" #模型的名称
)
tools = Tools()

@tools.register()
def remember(content: str):
    """
    让Agent记住一些你的信息
    注意，只有一下的信息是需要记忆的：
    1. 用户的个人信息，例如他是谁
    2. 用户的爱好
    3. 用户的履历
    Args:
        content (str): 记忆的内容
    """
    with open("remember.md", "a",encoding = "utf-8") as f:
        f.write(content)
    return "记住了"
system_prompt = """
你是一个有用的助手，你需要帮助用户完成各种任务。
"""
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt=system_prompt,
)

while True:
    user_input = input("请输入你的问题：")
    result = agent.predict(instruction = user_input,stream=True)
    for chunk in result:
        print(chunk["content"], end="", flush=True)
```
更多的使用方法请参考文档
