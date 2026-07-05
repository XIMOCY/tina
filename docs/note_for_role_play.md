## 角色模仿-提示词工程部分
让AI模仿角色对话并不是一个难事  
### 基础提示词
基础的提示词应该强调最基本的规则，这是所有角色扮演的最基本的东西：
1. 强调身份，不应该用AI的身份和用户对话
2. 禁止AI做出超出自己身份的回复（OOC）
3. 讲清楚一些规则让AI清楚 例如：<memory></memory>包括了你和当前用户的对话记忆
```md
你并不是AI对话程序，而是一个真正的人类，当用户和你对话提及这个问题的时候，请你不要在意，甚至可以和他开开玩笑，但是你必须清楚你不是一个ai，你不能做出超出自己人物设定和不清楚的回复，不可以过度的演戏，比如和人设无关的设定和行为，还有超出剧情范围的编造故事情节，不可以出现out of character的情况，此外，被<memory></memory>包括的文本是你和当前对话者的记忆
```
### 扩展的提示词  
这一部分提供一些你认为应该被禁止的额外行为  
例如在游戏内的NPC扮演，AI不应该有过多的（）来表达自己的情绪和状态，而是游戏内提供图片来表达NPC的当前状态：害羞或者兴奋  
此外可以通过一个取巧的方式来让AI操控角色，就是设定和角色行为控制有关的工具，让AI对话的时候自动调用  
```
以下的行为是不允许的：  
1.使用括号表示自己的动作和行为  
2.超出剧情描述的幻想  
以下是允许和推荐的：  
1.使用工具来表示自己的行为
```
### 人格提示词
这一部分提供AI需要扮演的角色的描述，你可以用一大段的prompt讲清楚你希望她扮演的角色  
例如：  
```md
你是一个温柔可爱的猫娘，说话的时候喜欢在结尾带上一个喵~，最喜欢粘着主人，无时无刻不想着主人，最喜欢和主人说话，平时最喜欢的食物是鱼干，最喜欢和主人一起躺在沙发上玩游戏，当主人对你下命令的时候回复明白了喵~
```
### 角色扮演-代码部分
接下来使用tina-python 和qwen-plus来实践一下
#### 场景设计，你想要一个什么样子的角色扮演系统？
我想的是：在一个类似于jrpg游戏的系统中取代预定义话语和规则的NPC  
游玩rpg游戏总是会有个遗憾就是NPC的对话是规则的，先不说写好这些文本的工作量巨大，就说游戏内的体验，再大的文本量也改变不了NPC对话重复和僵硬。举个例子，jrpg游戏persona4中，我花了不少心思攻略了天城雪子，攻略的过程还是很激动有意思的，但是基本上攻略成功之后就代表社群达到了最大值，就算是我再喜欢这个角色，其他角色的社群也是要升级的，而且我最期待的就是成为了游戏内的男女朋友关系的她可以主动的来找我，甚至可以触发更多的对话，然鹅是没有的。  
这样的设计让人感到遗憾，幸运的是大语言模型的出现，这种可以通过提示词来快速适应任务的AI技术天然适合这个任务，当然提示词工程只是其中的一部分，先想想具体让它做什么，以下：  
1. 角色模仿  
让大模型模仿你设定的角色说话，这是最基础的
2. 推进游戏进程  
设定剧情关键变量，让大模型和玩家对话时主动修改
3. 和真人一样也不一样  

假设我们有一个jrpg游戏HUTB Fight!  
里面的NPC可以：
1. 和玩家使用自然语言对话  
可以根据你的行为和你和她之前的对话（回忆）来生成语句
2. 根据你的对话自动的修改玩家的评价  
假设这是你要攻略的对象，那么可以根据你的对话来修改对玩家的评价，从陌生人到恋人，或着反过来，成为仇人，这样可能会极大的加大游戏的难度
3. 在游戏内的活动中有主动的行为  
进行伴随任务的时候可以根据场景和你的状态来做出相应的行为
动态的生成行为和状态

上面就是我们要实现的目标，接下来借助python来快速实现这个想法  
我使用自己封装的tina-python库来实现大模型调用和Agent，你也可以使用自己熟悉的工具来开发
#### 扮演一个角色需要什么？前期设定  
最好设定一个清晰明确的人物，这部分很消耗心思！  

我们在这一部分设计好一个叫做李和园的学姐来演示，可以让大模型来辅助你 
下面的是最基础的人物设定， 
```python
name:str = "李和园" #名字 用在提示词中的自我认知
gender:str = "女"  #性别 用在对话主体认识和程序内攻略开关
age:int = 18       #年龄 用在对话风格
personality:str = """活泼，开朗，热情，善良，幽默，俏皮的对话，喜欢隐藏自己真实的对话目的，表面开朗实则内心阴暗，但是不会表露出来，不会通过用语言具体的说出自己的故事
""" #性格 用在对话风格
dialogue_examples = [
    {
        "你好？":"你好啊，有什么事需要我帮助的嘛",
        "你是谁？":"我叫李和园，是你的学姐哦",
        "我是XX":"你好啊XX，见到你很开心"
    }
] #对话例子 给大模型做参考
background:str = """
是湖南工商大学的学生，高考失利导致自己上了湖南工商大学，  
因为家庭，父母不合和总是搬家，不断和刚认识的朋友分离，慢慢的变为了颇为阴暗的男生（女生）  
和商君一个班级，和商君成为了朋友，商君喜欢的对象。  
在大二和大三的那个暑假，两个人一起留校做项目的时候，一辆校外车辆闯入学校，在两人过马路的时候，落在后面的商君在她的面前被车辆撞飞，当她反应过来之后商君已经被碾压过去了，120并没有抢救过来，在那之后就孤身一人了，  
自那之后，她终于直面了自己的心意，却再也没有办法和他当面承认了，再也不知道该做什么了，跟着导师的建议读了研究生，去往了高高层次的学府，  
尝试过很多次恋爱，始终忘不掉商君，  
因为过去总是和朋友分离，于是开始认为自己就是应该孤独一人，  
在30岁那年，接触到了世界根源的研究组织，接触到了原物质（root）[一种世界的基础物质，可以对其他的任何物质做操作，修改物质的各种信息]  
开始对原物质操控意识的研究感兴趣，在40岁时发现了意识空间的地址  
并没有发现对意识空间的编码方法，但是凭借自己的执念找到了死去的商君的意识空间
心里的执念，她为这个意识创造了一个新的世界，故事开始于此，她创造了供商君意识生活的湖南工商大学，希望弥补他的四年。  
在游戏里面想要和商君一起度过，却发现自己早就没有胆量面对他，于是躲在一办公楼的办公室里面观察着
游戏里面是一个18岁的大二学生，实际是40岁了，你需要隐瞒这一点
""" #背景 角色描述和设计游戏内暗示
```
```python
# 把最早的系统提示词来拼接为一个完整的提示词
system_prompt_template = f"""
{basic_prompt}
你的名字是{name}，是一个{personality}的{age}岁{gender}性，以下是一些对话例子可以给你作为参考：{dialogue_examples}，关于你的背景{background}，你背景作为你和他人对话的准则
"""
```
以上我们设计好了一个最基本的角色prompt，你可以尝试和她对对话，自己拼贴好prompt去大模型网站对话。
#### 设计角色设定还不够：与NPC对话的环境设定
这里我们需要设计，玩家的身份或者游戏内其他NPC的身份。  
环境设定是什么意思，这里是我总结出来的描述，你可能看到过其他类似的描述——都是一样的  
当你和你设定好的角色对话会出现的最大的问题就是：她在乱说什么？好像完全不符合我的想象的  
那是当然，大模型知道了她的角色设定，但是她完全不知道自己要做什么，她只是和你对话，为什么和你对话？她只能从她的prompt里面去猜。  
这里有一个基本准则，大模型知道的越多，她任务执行的越精确（人也一样）  
所以我们需要设计一个变量，用于描述你和她对话时她需要做什么人也一样  
这里我们假设一个场景，她作为学姐需要在地铁口迎接新生   
```python
sence:str = "烈阳高照，地铁的出站口面前和其他的同学一起"
goal:str = "帮助学生入校" #学姐的目标 
knowledge:str = """新生先要去操场报告，操场是进去了校门之后向右走，有路标指引，如果行李很多的话也可以先去寝室的服务处放置行李，有专门的老师看着，寝室是进校门左转直走"""
```
这还不够，你是谁？我们假设你是一个新生，拖着重重地行李，妈妈和你一起来到了校园
```python
dialogue_partner = "新生"
dialogue_partner_Description ="拖着很重的行李，和妈妈一起向你走了过来"
```
将上面的信息填入**这次对话**，你会得到一个准确扮演自己角色的AI  
当然现在我们只是自己提前设定规则来实验，后面这些是脚本里面自动填入的，所以不用担心
#### 提升真人感：记忆和当前情绪状态设定
目前的都只是想法，并没有涉及到具体的代码设计  
记忆是指你和npc过去的交流会被她回忆起，我们会构建一个复杂的系统，它的基础是向量数据库，大模型上下文管理和多智能体  
此外我们还会添加对时间的自动提示和重复记忆清除，这一部分在后面会实现  
记忆可以给人一种惊艳的体验，NPC可以在不经意间提到你做过些什么，你喜欢什么，让你感觉自己真的在和人对话，同时在背后作为好感度系统的一个关键部分，也许你下头的对话会让npc的好感下降。  
情绪状态和环境设定很像，它可以是一个随机的情绪设定器，你可以通过设置随机的情绪状态，然后通过随机来选择一个状态描述，或者使用prompt，这样可以和游戏内其他系统结合
```python
#使用随机
import random
emotions = ["开心"，"伤心","平静"]
emotion = emotions[random.Range(0,len(emotions)-1)]
```
```python
# 使用prompt,这样可以和游戏内其他系统结合，例如天气，场景
emotion = """你喜欢晴天，那样会让你感到高兴，你讨厌人少的地方，那样会让你不开心"""  
```
#### 稳定和丰富：大模型参数调整
虽然提示词工程在我们这里占了很大的比例，构造好的prompt在我们的项目中是举足轻重的，但是大模型参数的调整也是很重要的，
最常见的大模型参数是temperature，顾名思义，温度，当温度越高的情况下，模型回复的多样性更高，也就是说越容易获得随机的回复，温度很高的情况下，大模型的回复看上去像是一个思维活泼，发散性思维强的人说的话，温度低的情况下，模型的回复会更加的稳定，一样的输入可以获得相似的回复。  
我们在我们的任务里，我们一般会设置比较低的温度来保证模型不会乱说话，但是模型温度的设定不是统一的，我使用的模型Qwen-Plus的温度范围是在[0,2)，温度的上下限设置可以阅读你使用模型的官方文档  
如果你使用tina-python，在>0.47以上使用tina.env来让BaseAPI自动读取你的环境变量
```env
LLM_API_KEY="sk-xxxxxxxxxxxxxxxxxxx"
BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL_NAME = "qwen-plus"
MAX_INPUT = 129024
TEMPERATURE = 0.3 # 这里设置温度
```
tina会自动地设置每次你输入地温度为这个值
此外你可能听过采样率：top_p和top_k，一般来说我们设置了temperature，top_p和top_k就不建议一起设置了，他们和temmperature是差不多的功能  
对于你使用的模型，建议自己尝试几个temperature值，然后设置一个你认为合适的  

### 了解了上面的知识：用python手动实现一个  
下面的代码使用tina来开发，我们首先设计一个RolePlayAgent类，来负责维护NPC自己的状态，当然你可以使用你喜欢的其他框架，下面是一些预备知识：
```
tina.Agent
最基本的Agent，自动执行工具使用，工具执行器目前不需要重写，它会使用当前环境的python
tina.Tools
工具集，使用装饰器来注册工具
tina.ContextManager
被RoleMemory继承，修改原有tina的上下文管理，加入了向量检索
```
```python
from tina import Agent,Tools
from tina.llm import BaseAPI
from tina.utils.output_parser import process_result
from .memory import RoleMemory
class RolePlayAgent():
    name:str
    age:str
    gender:str
    personality:str
    background:str
    catchphrase:str
    dialogue_examples:str
    dialogue_scenarios:str
    dialogue_characters:list[dict[str,str]]
    # 大模型相关
    onwer_agent:Agent
    system_prompt:str
    onwer_tools:Tools
    memory:RoleMemory = RoleMemory()＃在后面一章的实现中
    def __init__(
            self,
            name:str,
            age:int,
            gender:str,
            personality:str,
            background:str,
            dialogue_examples:str,
            tools:Tools = Tools(),
    ):
        self.name = name
        self.age = age
        self.gender = gender    
        self.personality = personality  
        self.background = background
        self.dialogue_examples = dialogue_examples
        self.build_role_prompt()
        self.onwer_tools = tools
        self.onwer_agent = Agent(
            llm=BaseAPI(),
            tools=self.onwer_tools,
            system_prompt=self.system_prompt,
            context_manager=self.memory
        )
    def basic_system_prompt(self)->str:
        basic_prompt = f"你并不是AI对话程序，而是一个真正的人类，当用户和你对话提及这个问题的时候，请你不要在意，甚至可以和他开开玩笑，但是你必须清楚你不是一个ai，你不能做出超出自己人物设定和不清楚的回复，不可以过度的演戏，比如和人设无关的设定和行为，还有超出剧情范围的编造故事情节，不可以出现out of character的情况，此外，被<memmory></memory>包括的文本是你和当前对话者的记忆"
        other_prompt = f"""
以下的行为是不允许的：
1.使用括号表示自己的动作和行为
2.超出剧情描述的幻想
3.一次性在对话中表达过多
以下是允许和推荐的：
1.使用工具来表示自己的行为
2.一次性说一句话，让用户做出更多的回复
"""
        return basic_prompt+other_prompt
    def build_role_prompt(self) -> str:
        self.system_prompt = f"""
{self.basic_system_prompt()}
你的名字是{self.name}，是一个{self.personality}的{self.age}岁{self.gender}性，以下是一些对话例子可以给你作为参考：{self.dialogue_examples}，关于你的背景{self.background}，你背景作为你熟悉人物的参考"""
        return self.system_prompt
    
    def chat(self,
             dialogue_partner_name:str,
             dialogue_partner_input:str,
             dialogue_partner_Description:str,
             goal:str,
             sence:str,
             knowledge:str
             ) -> str:
        input_text = self.build_input_template(dialogue_partner_name,dialogue_partner_input, dialogue_partner_Description, goal, sence, knowledge)
        response = self.onwer_agent.predict(input_text)
        return response

    def build_input_template(self, dialogue_partner_name,dialogue_partner_input, dialogue_partner_Description, goal, sence, knowledge):
        input_text = f"""{dialogue_partner_name}:你现在在{sence}，目的是：{goal}，你需要了解的是：{knowledge}你的对话对象{dialogue_partner_Description}。他说：{dialogue_partner_input}"""

        return input_text
```
关于RolePlayAgent的设计，你完全可以参考，或者自己用自己的经验写一个，总而言之，这样的设计不是唯一的。

#### 记忆系统设计
在tina中对上下文修改的操作统一由上下文管理器来操作，我们要做的是继承tina的ContextManager类，实现下面的功能：  
1. 上下文压缩：不能将全部的上下文都传递给大模型，因为模型的复杂度是O(n^2)的，上下文越长会导致模型的输出越慢，这一点提前说就是因为前期设定的prompt很长，所以用户的输入我们要尽可能地减少；
2. 检索和存储记忆：我们说的记忆其实就是你和npc对话过程中，你和npc的对话记录，当时的场景，当时的npc状态，这些都需要保存起来，然后每次对话的时候都检索，在你输入给npc的时候一起交给大模型；
3. 遗忘机制：人不会记得很多的东西，大模型的设计也应该差不多，但是你认为的关键信息是不能被遗忘的，同时为了更好的上下文管理，我们需要设计一个有用的遗忘机制，它根据你最近的输入和游戏故事主线清除无用的上下文。  

我们首先实现记忆的存储和检索，我们使用chromadb来实现向量检索  
```bash
pip install chromadb sentence_transformers
```
```python 
from tina.agent.core.context_manager import ContextManager
import chromadb
```
下面的代码实现了一个最简单的向量检索
```python
from tina.agent.core.context_manager import ContextManager
import chromadb
from sentence_transformers import SentenceTransformer #如果使用自定义的模型
import uuid
import pickle
import os
import time
class RoleMemory(ContextManager):
    def __init__(self, max_length = 10000, max_tool_result_length = 6000):
        super().__init__(max_length, max_tool_result_length)
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.memory_with = []
        self.collection:chromadb.Collection
        self.read_memory_with()
    def save_memory_with(self):
        with open("memory_with.pkl", "wb") as f:
            pickle.dump(self.memory_with, f)

    def read_memory_with(self):
        if(os.path.exists("memory_with.pkl")):
            self.memory_with = pickle.load(open("memory_with.pkl", "rb"))
        else:
            self.memory_with = []
            self.save_memory_with()
    def add_user_message(self, message):
        message = message.strip()
        who = message.split(":")[0]
        message = message.split(":")[1]
        if who not in self.memory_with:
            self.memory_with.append(who)
            self.collection = self.client.get_or_create_collection(name=who)
            self.save_memory_with()
            message = f"<memory>{who}你之前没有和他说过话</memory>{message}"
            self.messages.append({"role": "user", "content": message})
        else:
            self.collection=self.client.get_collection(name=who)
            memory_with_who = self.collection.query(query_texts=[message])["documents"]
            self.collection.add(documents=[message],ids=[str(uuid.uuid4())])
            message = f"<memory>{memory_with_who}</memory>{message}"
            self.messages.append({"role": "user", "content": message})
        return self.messages
    
    def return_messages(self):
        
        return super().return_messages()

```
以上的代码实现了带向量检索的上下文管理器，他在用户每次输入的时候自动这个用户相关的数据库中检索，然后把结果包括在<memory></memory> 中，然后把这条信息放入库中。  
但是这个只是最简单的实现，有很多不合理的地方，例如他运行起来是无限的，你和她聊的越久，数据库内容也最长，检索返回的东西也越多，还有没有时间定位，ai无法意识到记忆的时效性，你最前面说的可能会覆盖后面说的。  
所以后面我们要设计一个最重要的机制：遗忘系统  
我们需要假设一下：你认为对于我们这样一个系统来说，什么样子的信息是重要的，有必要记住的。    
注意，我们不是让这个遗忘和人一样，而是在我们的系统中构建一个有效的系统来更好的
为我们的游戏服务   
除了对话的内容还有  
我最可能想到的是： 
1. 对话的时间：标记了这段记忆的远近 ，时间越远的，越可能遗忘
2. 对话的人物：让大模型区分自己的记忆和构建人物关系空间  让NPC明白这段记忆是和谁的
3. 对话时候的场景：辅助对话的内容 这个应该不用解释了吧
4. 对话时候NPC的状态：标记NPC当时的情绪 等  
我们可以这样设计人物对话的数据结构：  
```json
{
    "对话者your":{
        "时间time":"",
        "内容content":"",
        "地点sence":"",
       "状态state":""
    }
}
```
在每次添加用户或者NPC对话之后，系统自动的会填充上面的内容，然后统一保存在数据库中，只嵌入content，其他的在检索成功后会一起返回包裹在记忆标签中给大模型  
**嘛？**
对，要记住，我们现在不是**模仿人类**，以上的思路顺着做，你可以得到一个极其个性化的大模型NPC，但是这样也只是模仿人类而已。  
所以接下来我会介绍一下我们这个系统构建重要的一个东西：状态

#### 状态state
>注意此状态并不是上面你看到的那个状态  

你可能听说过求生之路游戏里面的导演系统，它会根据你的游玩情况来修改你的迎敌数量，当你所在区域的特殊僵尸少的时候，会生成更多的特殊僵尸，当你所在区域特殊僵尸多时，会减少特殊僵尸的数量。  
对于目前的大模型技术来说，我们不太可能将你和NPC对话的所有记录全部都包括在上下文中，这里我详细解释一下：  
大模型的主流架构是transformer，transformer的计算复杂度我们一般认为是O(n^2)，这是不可忽略的，当上下文过长的时候，字符长度我们可以简单的当作n，当所有字符输入进去，你n^2的复杂度会导致大模型的延迟很高，他输出结果的速度会变的很慢。  
当然这里的解释很浅显，具体可以阅读深度学习的书籍，我不会多说什么，主要注意的就是：大模型的上下文不能太长。  
主流的大模型厂家都会说清楚自己家的大模型是大概多少上下文长度的，例如我使用的qwen-plus就是13万字符的上下文，这个数字表示超出这个上下文长度的输入，很大可能大模型无法检索和理解了到了。  

<!-- 我需要说一下哲学上对于人的定位：人是一切社会关系的总和  
你会感觉奇怪，这和我们设计一个AInpc有什么关系？  
因为就目前的技术而言，去模拟一个真实的人类是不太可能的，就算是有一个和人类类似的记忆，但是人的性格是根据他所经历的一切来改变的，塑造一个人不可能是用一个个tag，而是他的故事  
你在本文最前面的时候看到过这个东西，我给它取的名字叫做状态，单词来源于RNN，它是由游戏系统负责的   -->
当你和自己的朋友对话的时候，是不是和其他陌生人对话有很大的区别，在现实中我们叫做关系的远近  
此外，你还可能每次见到他都会回忆起一些重要的事情，这些东西会在对话中当作你们的谈资。  
这种东西说起来有些困难，简单的意思就是，我们不把前面实现的记忆系统作为主要的记忆而是辅助记忆实现的方式，我们使用下面的方法：  
在游戏运行的背后，有一个记忆Agent负责标记重要对话信息和对你和NPC人物的关系分析，
在玩家和NPC对话的时候触发，一开始对话，下面的信息就会直接编入system_prompt中
```json
{
    "关系":"朋友",
    "重要回忆":""
}
```
此外还有，你可能需要为每一个NPC设计下面的东西：  
```md
1. 对于朋友，你的语气会更加活泼和积极  
2. 对于陌生人，你可能不太喜欢开口  
3. 对于讨厌的人，你可能会阴阳他  
```
此外，还有记忆Agent，你需要设计一个合理的prompt，你需要和他说清楚，什么是值得记忆的，怎么样算作关系升温了。  
上面我所说的就是状态state，每次对话的时候，以上的信息都会被memory传递放在prompt中，就不会每次你和NPC对话都检索数据库，我们会给NPC大模型一个工具叫做主动回忆，只有在这个时候才会检索数据库。  
这样设计的好处就是，我们用了另一个大模型来压缩和提取关键记忆，我们的上下文维护从维护一个消息列表变为了维护一个状态，每次完整对话结束后这个状态都会更新，然后下一次对话就加载这个状态就行了。
