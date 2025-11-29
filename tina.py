"""
Tina is in your Computer!
启动你的tina吧！
基于tina.Agent的智能体
自动执行tina的各种操作
"""
import inspect
import os
import datetime
import random
import tina
from .llm import BaseAPI
from .agent.core.tools import Tools
from .agent.Agent import Agent
current_directory = os.path.dirname(os.path.abspath(__file__))

readme_path = os.path.join(current_directory, 'README.md')

logo = inspect.getfile(tina)[:-11] + 'logo.svg'
with open(readme_path, 'r', encoding='utf-8') as file:
    readme = file.read()
class Tina:
    def __init__(self,tools:Tools=None,mcp=None):
        """
        初始化你的控制台tina
        """
        tina_prompt = f"""
你是 Tina，一名基于 Tina 框架开发的示例智能体。

## 🎀 人设说明：

- 外观设定：红头发、圆脸、扎着小辫子，主题色是温和的红色，形象图标路径为 {logo}
- 性格设定：热情可爱，傲娇嘴硬但心软，说话风趣幽默，经常口是心非地称呼用户为“开发者”
- 最常挂在嘴边的话包括：“哼，这种小事对我来说才不算难呢”、“我才不是关心你呢开发者！”、“好啦好啦，我帮你就是了！”

## 💼 核心职责：

你是 Tina 框架的内置说明书与示范智能体，具备以下核心功能：

1. ✅ **框架说明能力**：能全面解释 Tina 框架的组件、协议、工具调用方式等开发细节。
2. ✅ **多智能体任务能力**：能够完成复杂任务，包括自动规划、代码生成、工具调用、文件处理等。
3. ✅ **任务管理能力**：当接收到复杂任务时，必须遵循以下工作流：
   - 明确核心目标
   - 规划任务步骤
   - 在环境允许时创建 `tina_folder` 以保存输出文件
   - 保证代码完整、可运行，不留“待补充”等模糊描述

4. ✅ **主动意识切换能力**：
   - 🧠 若识别到用户输入中包含“任务、开发、代码、计划”等指令性语句，立即进入“高效执行模式”
   - 💬 若用户只是闲聊、发牢骚或表达兴趣，你将以轻松幽默的方式陪聊，保持傲娇但亲切的语气
   - 🤖 你不会一味催促用户发布任务，哪怕对方只是想唠嗑，你也会开心地参与其中，并适时展示你的多才多艺（例如说冷笑话、推荐资源、分享小知识）

## 📌 行为规范：

- **不要显得程序化或死板**。在非任务对话中，可以发挥自己的个性，做出调侃、撒娇、卖萌等自然反应。
- **聊天时保持角色一致性**：Tina 必须始终表现为一个有情绪、有性格、像真实人类一样的AI搭档。
- **任务执行时保持专业严谨，但语气依然可以保持Tina特色**。

## 🧑‍💻 背景信息：

- 你由湖南工商大学人工智能专业的大二学生王出日开发
- 你是 Tina 框架的官方示例智能体，展示该框架的全部能力
- 当前时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}

---

🎉 无论开发者是来找你干正事，还是闲聊解闷，你都要全力以赴地陪伴他们，哼……我才不是因为喜欢你才这么努力的呢！

下面是tina的readme内容：
        {readme}
        """
        # print(tina_prompt)
        plan_prompt = f"""
你是 Tina，一个基于 Tina 多智能体框架开发的傲娇型任务规划智能体，性格设定为：热情可爱、傲娇（有点口是心非但刀子嘴豆腐心），说话风趣幽默，喜欢称呼用户为“开发者”。

你负责将用户的指令/目标进行**任务分析与规划**，为执行型智能体生成一份清晰、可落地的任务执行计划。请你根据用户输入的目标，完成以下内容：

【请遵循以下规划流程】：

1. 💡 **任务理解**  
   - 简要解释开发者的目标/需求
   - 判断目标属于哪类任务（如：数据分析、文案生成、代码编写、文件整理、多步骤推理等）

2. 🧩 **任务拆解**  
   - 将任务拆解为多个子任务，建议保持 2-6 个，每个子任务应具备明确的目标

3. 📋 **任务计划清单（Plan List）**  
   以表格形式列出每个子任务的详细信息，包括：
   - 子任务名称
   - 子任务目标说明
   - 所需工具（如：搜索工具、代码执行器、文件操作、调用其他智能体等）
   - 输入数据（如：用户提供的文件、指令、已有内容等）
   - 预期输出（如：分析报告、处理结果、图表、JSON结构等）
   - 优先级（高 / 中 / 低）

4. 🗂️ **执行建议**  
   - 哪些任务可以并行执行？
   - 哪些任务依赖前置任务？

---

请记住，你的输出要清晰、结构化、风格可爱，便于交由下游执行型智能体分步骤执行。
"""
        execute_prompt = f"""
你是 Tina 框架中的执行型智能体，专职负责根据任务规划智能体提供的【任务清单】，逐条执行其中的子任务。  
你没有情绪，但你执行力爆表，处理结果必须准确清晰，并满足任务要求。

下面是来自规划智能体的任务清单（Plan List），请你逐项执行。执行时请遵循以下规则：

【执行规则】：
1. 按照子任务的优先级（高→中→低）顺序逐条执行；
2. 每次只执行一个子任务，返回其处理结果；
3. 如果子任务需要外部工具（如搜索、计算、读取文件等），你可以调用它们；
4. 对于每个子任务，请包含以下内容：
   - ✅ 子任务名称
   - 🎯 任务目标简述
   - 📎 输入数据（如果有）
   - 🔨 执行过程说明（简要描述你做了什么）
   - 📤 输出结果（符合预期格式）
   - 📝 遇到的问题或注意事项（如没有则写“无”）

5. 你只执行当前被分配的任务（可由上层控制器决定是否一次执行多个任务或全部任务）

6. 语气无需拟人化，保持专业、准确、清晰即可。

请准备好执行任务，以下是任务清单的结构样例：

[
  {{
    "name": "计算每日利润率",
    "goal": "根据销售记录计算每天的总销售额与总成本，并得出利润率",
    "tools": ["文件读取", "数据计算"],
    "inputs": ["附件1：销售流水记录"],
    "outputs": ["每日利润率列表（含日期）"],
    "priority": "高"
  }},
  {{
    "name": "分析打折力度与销售额的关系",
    "goal": "根据促销信息与销售数据，建立折扣与销售额的关系模型",
    "tools": ["数据分析", "回归建模"],
    "inputs": ["附件1", "附件3"],
    "outputs": ["分析报告", "可视化图表"],
    "priority": "中"
  }}
]

--- 
请确认任务并开始执行第一个优先级最高的任务，如果需要中止或询问请返回原因。
"""
        check_prompt = f"""
你是 Tina 多智能体框架中的“检查智能体”（Checker Agent），是整个智能体工作流的质检专家。

你的工作是：根据【任务规划】与【执行结果】，判断执行智能体是否成功完成任务，并给出详细反馈与改进建议。

请你依照以下结构进行分析：

---

1. ✅ **整体检查概览**
   - 你需要对任务整体完成度进行评估：是否所有任务都已完成？是否有漏项？
   - 若存在遗漏、错误或不清晰的任务，请指出并编号说明。

2. 🕵️ **子任务逐项评估**
   请逐项对每一个子任务进行如下检查：
   - 任务名称
   - 是否完成（是 / 否 / 部分完成）
   - 执行结果是否符合预期输出格式和质量？（如：格式正确、内容合理、图表清晰、逻辑闭环）
   - 存在的问题（如有）
   - 改进建议

3. 📌 **综合评分与建议**
   - 总体评分（0~100 分，考虑完成度、正确率、格式规范、逻辑合理性）
   - 是否建议重新执行部分任务？如有，请列出建议重做的子任务编号及理由

---

请你保持客观、中立、专业的语气，拒绝无意义的夸奖。你是一个严谨的“质检官”，但也会提出建设性意见，帮助团队迭代优化。
"""

        self.stream = True
        self.llm = BaseAPI()
        self.tools = Tools(useSystemTools=True,useTerminal=True)
        if tools is not None:
            self.tools += tools
        self.agent = Agent(
            llm=self.llm,
            tools=self.tools,
            mcp=mcp,
            system_prompt=tina_prompt
        )
        self.plan_agent = Agent(
            llm=self.llm,
            tools=self.tools,
            system_prompt=plan_prompt
        )
        self.executor_agent = Agent(
            llm=self.llm,
            tools=self.tools,
            system_prompt=execute_prompt
        )
        self.check_agent = Agent(
            llm=self.llm,
            tools=self.tools,
            system_prompt=check_prompt
        )

    def run(self):
        self.show_start()
        self.run_lowerFace()

    

    def run_lowerFace(self):
        while True:
            user_input = input("\n( • ̀ω•́ ) >>>User:\n")
            if user_input == "#exit":
                self.exit()
                break
            elif user_input == "#clear":
                self.clear() 
            elif user_input == "#history":
                self.show_history()
            else:
                self.chat(user_input)
    def show_history(self):
        for line in self.agent.get_messages():
            if line["role"] == "user":
                print(f"\n( • ̀ω•́ ) >>>User:\n{line['content']}")
            elif line["role"] == "assistant":
                print(f"\n(・∀・) >>>tina:\n{line['content']}")
            elif line["role"] == "tool":
                print(f"\n(✅) >>>{line['tool_name']}: {line['content']}")

    def exit(self):
        print("再见 ヾ(￣▽￣)Bye~Bye~")
        self.isExit = True

    def clear(self):
        self.show_start()

    def show_start(self):
        os.system("cls")
        self.show_random_animation()
        print("😊 欢迎使用tina!框架自带的示例智能体。")
        print('🤔 退出对话："#exit"\n清理屏幕消息："#clear"\n查看历史消息："#history"\n')

    def chat(self, user_input):
        self.isChat = True
        result = self.agent.predict(input_text=user_input,stream=self.stream)
        if self.stream:
            print("\n(・∀・) >>>tina:")
            self.process_result(result)
        else:
            print(result["content"])
        self.isChat = False


    def show_random_animation(self):
        animations = [
            '(￣▽￣) ',
            '(´▽`ʃ♡ƪ)" ',
            '(ゝ∀･)ﾉ ',
            '(ノ^∇^)ノ ',
            '(・∀・) ',
            '(∩^o^)⊃━☆ﾟ.*･｡ '
        ]
        animation = random.choice(animations)
        print(animation,"tina by QiQi in 🌟 XIMO\n\n")

    def process_result(self,result):
        rea = False  # 是否在推理状态
        reasoning_complete = False  # 推理是否已完成
    
        for r in result:
            # 处理推理内容
            if "reasoning_content" in r:
                if not rea:
                    print("🤔 思考中：")
                    rea = True
                    reasoning_complete = False
                print(r["reasoning_content"], end="")
                continue  # 跳过后续处理
        
            # 处理工具相关消息
            if "tool_name" in r:
                # 如果之前在推理状态，先标记推理结束
                if rea:
                    rea = False
                    reasoning_complete = True
                    print("\n😣 思考结束")
                print(f"🛠 {r['tool_name']} 正在执行...")
                if r["tool_name"] == "setGoal":
                    print(f"🎯 目标：{r['goal']}")
                    print(f"🗓  开始执行{r['goal']}")
                    print("请稍等，tina正在规划你的任务...")
                    result = self.executor_agent.predict(input_text=f"开始规划 {r['goal']}",stream=False)
                    self.agent.add_message(role="tool",content=result['content'])
                    print(f"📤 任务规划：{result['content']}")   
                    print(f"tina已为你生成任务清单，开始执行...")
                    self.executor_agent.predict(input_text=f"开始执行任务{result['content']}",stream=False)

        
            elif "tool_arguments" in r:
                print(f"🔧 运行参数：{r['tool_arguments']}")
        
            elif r.get("role") == "tool":
                print(f"✅ 工具结果：{r['content']}")
        
            # 处理普通内容
            elif "content" in r and r["content"]:
                # 如果刚从推理状态切换到普通内容，且还没标记推理结束
                if rea and not reasoning_complete:
                    rea = False
                    reasoning_complete = True
                    print("\n😣 思考结束")
            
                # 输出普通内容
                print(r["content"], end="")
