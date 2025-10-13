import random
import json
from typing import Generator
from .Agent import Agent

from .core.manage import TinaFolderManager

play_prompt_template = "你是一位专业的演员，你需要扮演的角色是{personality}，年龄是{age}，性别为{gender}。请按照他或者她的语气说话，不需要添加心理活动和人物动作，注意一位演员的修养，说话的时候严禁过长的台词，因为不符合现实，一次对话最好只说一件事，你需要完美的做到符合这位角色的行为和言行，不需要过于夸张的表现，恰到好处即可，就像日常的对话一样自然"
writer_prompt_template = "你现在是一位作家，这是一段用户提供的人物性格描述，请你优化这段描述，形成一个人物大纲，总结为：人物性格，人物爱好，人物常用动作，人物描述等，这位角色的名字是{name}。"

class Character():
    """
    基于大模型的角色类
    """
    def __init__(self,LLM:type,
                  tools:type,
                  name:str,
                  folder:str=None,
                  personality:str=None,
                  age:int=None,
                  gender:str=None,
                  isMemory:bool=False,
                  enable_llm_optimization:bool=False,
                  ):
        self.name = name
        self.folder = folder
        self.LLM = LLM
        self.age = age if age else random.randint(18,60)
        self.gender = gender if gender else random.choice(['male','female'])
        if isMemory:
            self.initMemory(name, folder, personality, isMemory, enable_llm_optimization)
        else:
            self.personality = personality
            if enable_llm_optimization:
                self.optimize_personality()
        self.agent = Agent(LLM=LLM,tools=tools,sys_prompt=play_prompt_template.format(personality=personality,age=self.age,gender=self.gender))
        
    @classmethod
    def loadCharacterFromjson(cls,json_path:str,isMemory:bool=False,enable_llm_optimization:bool=False)->'Character':
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(name=data["name"],personality=data["personality"],age=data["age"],gender=data["gender"],isMemory=isMemory,enable_llm_optimization=enable_llm_optimization)

    def initMemory(self, name, folder, personality, isMemory, enable_llm_optimization):
        if isMemory:
            if folder:
                TinaFolderManager.init(folder)
            self.memory = Memory(name,personality)
            self.agent.addMessage(messages=self.memory.returnMessages(32757))
            if self.memory.getPersonality() is not None:
                self.personality = self.memory.getPersonality()
        else:
            if personality is None:
                raise ValueError("Personality需要被提供")
            else:
                self.personality = personality
                if enable_llm_optimization:
                    self.optimize_personality()
    def changeName(self,name:str):
        self.name = name
        del self.agent
        self.agent = Agent(LLM=self.LLM,tools=self.agent.tools,sys_prompt=play_prompt_template.format(personality=self.personality,age=self.age,gender=self.gender))
    def optimize_personality(self):
        """
        优化角色性格
        """
        self.personality = self.LLM.predict(
            input_text = self.personality,
            sys_prompt = writer_prompt_template.format(name=self.name),
        )["content"]
    def __str__(self):
        return f"{self.name}({self.age}岁,{self.gender})"
    def __repr__(self):
        return f"Character({self.name},{self.personality},{self.age},{self.gender})"
    def respond(self,input_text:str,character:type=None)->Generator[str, None, None]:
        """
        角色对话
        """
        if character is None:
            yield from self.agent.predict(input_text=input_text,stream=True)
        else:
            yield from self.agent.predict(input_text=f"向{character.name}性别：{character.gender}，{input_text}",stream=True)
            toAnotherCharacter = self.getMessages()[-1]["content"]
            character.addMessage(role = "assistant",content = f"另一位角色{self.name}对你说：{toAnotherCharacter}")

    def getPersonality(self)->str:
        """
        获取角色性格
        """
        return self.personality
    
    def getMessages(self) -> list:
        return self.agent.getMessages()
    
    def getTools(self) -> list:
        return self.agent.getTools()
    
    def getPrompt(self) -> str:
        return self.agent.getPrompt()
    
    def addMessage(self, role: str=None, content: str=None,messages: list = None) -> None:
        self.agent.addMessage(role=role,content=content,messages=messages)

    def recreatePersonality(self,personality:str,enable_llm_optimization:bool=False):
        self.personality = personality
        if enable_llm_optimization:
            self.optimize_personality()
        del self.agent
        self.agent = Agent(LLM=self.LLM,tools=self.agent.Tools,sys_prompt=f"你是一位专业的演员，你需要扮演的角色是{self.personality}，年龄是{self.age}，性别为{self.gender}。请按照他或者她的语气说话，不需要添加心理活动和人物动作，注意一位演员的修养，说话的时候严禁过长的台词，因为不符合现实，一次对话最好只说一件事，你需要完美的做到符合这位角色的行为和言行，不需要过于夸张的表现，恰到好处即可，就像日常的对话一样自然")