# 快速开始
快速使用tina来开发你的Agent  
```bash
pip install tina-python==0.4.9rc0 
```
该教程是基于0.4.9预览版和0.5.0编写的  
在开始之前 请清楚tina不是一个复杂的框架，是一个方便你使用大模型功能和Agent功能的工具库  
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
        # print(chunk["content"], end="", flush=True) 你也可以这样做，因为返回值本质是一个dict 但是下面的方法有语法提示
        print(chunk.content, end="", flush=True)
```
在后面的文档我会一一介绍里面的用法 Have Fun!
