"""
编写者：王出日
日期：2024，12，1
版本？
记忆模块，用于存储和读取记忆数据，通过使用SQLite来对用户的消息做管理
importance为重要程度，由大模型评分，越重要，分数越高，越不容易被忘记
！！！注意：
该记忆模块可能更加像消息管理模块，因为它不对大模型内部进行处理，
内含：
-memory类
"""
import json
import os
import sqlite3
import datetime
from .manage import TinaFolderManager



class Memory:
    def __init__(self):
        self.folder = TinaFolderManager.getMemory()
        self.conn = sqlite3.connect(os.path.join(self.folder, "memory.db"))
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, time TEXT, role TEXT, content TEXT, importance INTEGER)''')
        self.conn.commit()
        self.conn.close()
        self.prompt="""
        请按照以下格式和准则为记忆打分，从1-5分，1分最低，5分最高，返回数字即可：

        {"role":"谁","tag":"什么","content":"提取主要的内容，将无关描述去除","importance":1-5}
        role:分为 system,user,assistant。如果是系统信息，则填写system；如果是用户信息，则填写user；如果是助手信息，则填写assistant。
        tag:描述信息的种类，种类有：用户信息，指令信息，聊天信息，工具信息和其他信息。
        content:提取主要的内容，将无关描述去除。例如，对于“我是王出日，我是一名程序员”，content为“用户名叫王出日，是一名程序员”
        分数越高表示重要程度越高，被遗忘的概率越低。首先要明确是谁说的话，然后再输入内容，最后输入分数。具体内容如下：
        用户信息是和用户相关的信息，比如用户是谁，用户的身份是什么，用户的喜好，用户的社交信息等，注意区分用户的名字和身份，比如我叫王出日表示我的名字是王出日和我是一名学生表示我是一位还在读书的学生。
        指令信息是指用户要求你做的事情，比如用户让你做角色扮演，让你做某件事情等。
        工具信息是指你调用了什么工具，工具的执行结果，工具的使用方法等。
        聊天信息是指用户和机器人之间交流的消息，比如用户问你问题，机器人回答你问题，机器人提出建议等。
        其他信息是指上面的信息之外的信息。
        在给了标签之后，同一标签的信息再根据importance进行排序，同一标签内的importance越高，越容易被记忆。
        例如：我是王出日，我是一名大学生。这个消息被归类为用户信息，impotence为最高分5分
        5分的信息将会作为长期记忆，不会被遗。
        4分的信息将会被记录。
        3分的信息会被记录，但不会被优先遗忘。
        2分的信息比1分的信息更长久被记忆。
        1分的信息会在短期内被遗忘,适用于没什么用的信息，例如询问或者无意义的聊天。
        按照这个格式返回数据
        """

    def remember(self, LLM:type,message:str) -> dict:
        """
        记忆用户信息
        importance: 1-5 重要程度
        """
        self.conn = sqlite3.connect(os.path.join(self.folder, "memory.db"))
        self.cursor = self.conn.cursor()
        msg_role = message["role"]
        msg_content = message["content"]
        result = LLM.predict(
                input_text = f"role:'{msg_role},content:'{msg_content}'",
                sys_prompt = self.prompt,
                format = "json",
                json_format = '{"role":"","tag":"","content":"","importance":1-5}'
            )
        result_dict = self.__json(result["content"],LLM)
        # result_dict = json.loads(result["content"])
        if self.is_valid_json(result_dict):
            time = datetime.datetime.now().strftime("%Y年-%m月-%d日 %H时:%M分")
            self.__insertInQOLite(result_dict, time)
        else:
            time = datetime.datetime.now().strftime("%Y年-%m月-%d日 %H时:%M分")
            self.__insertInQOLite({"role": "", "tag": "", "content": "", "importance": 0}, time)
        self.conn.close()
        return result_dict
    def __json(self,result:str,LLM:type=None)->dict:
        """
        将字符串转换为字典
        """
        try:
            result_dict = json.loads(result)
            return result_dict
        except:
            result = LLM.predict(
                input_text = result,
                sys_prompt = "按照以下的格式修正数据：\n\n{'role':'','tag':'','content':'','importance':1-5}",
                format = "json",
                json_format = '{"role":"","tag":"","content":"","importance":1-5}'
            )
            result_dict = self.json(result)
        return result_dict
    def __insertInQOLite(self, result_dict, time):
        try:
            self.cursor.execute('''
                INSERT INTO logs(tag, time, role, content, importance)
                VALUES (?,?,?,?,?)
                ''', (result_dict["tag"], time, result_dict["role"], result_dict["content"], result_dict["importance"])
                )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
    
    def forget(self,importence:int=1) -> None:
        """
        遗忘用户信息
        Args:
            importance: 1-5 重要程度，在这里也叫遗忘指数，越高表示越重要，越低表示越不重要
        """
        self.conn = sqlite3.connect(os.path.join(self.folder, "memory.db"))
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            '''DELETE FROM logs WHERE importance <=?''',
            (importence,)
        )
        self.conn.commit()
        self.conn.close()
        
        
    def recallByTag(self,tag:list=["用户信息","指令信息"],importance:int=3):
        """
        根据tag获取记忆信息
        """
        self.conn = sqlite3.connect(os.path.join(self.folder, "memory.db"))
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            '''SELECT * FROM logs WHERE tag IN ({}) AND importance >=?'''.format(",".join(["?"]*len(tag))),
            tag+[importance]
        )
        result = self.cursor.fetchall()
        messages = []
        for row in result:
            message = {
                "role": row[3],
                "content": row[4],
                "time": row[2]
            }
            messages.append(message)
        return messages
        
        
    def recallByContent(self,content:str):
        """
        根据content获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE content LIKE ?''',
            (f"%{content}%",)
        )
        result = self.cursor.fetchall()
        messages = []
        for row in result:
            message = {
                "role": row[3],
                "content": row[4]
            }
            messages.append(message)
        return messages
        
    def recallByImportance(self,importance:int):
        """
        根据importance获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE importance =?''',
            (importance,)
            )
        result = self.cursor.fetchall()
        messages = []
        for row in result:
            message = {
                "role": row[3],
                "content": row[4]
            }
            messages.append(message)
        return messages
        
    def returnMessages(self,length:int,memory_percent:float=0.2,tag:list=["用户信息","指令信息"],importance:int=3)->list:
        """
        读取memory.db中的所有信息
        返回以下的格式：
        [
            {
                "role": "谁",
                "content":时间+内容
            }
        ]
        """
        messages = self.recallByTag(tag=tag,importance=importance)
        memory_length = 0
        for message in messages:
            if messages == []:
                memory_length = 0
            else:
                memory_length = len(message["role"])+len(message["content"])+len(message["time"])

        if memory_length/length > memory_percent:
            if importance == 5:
                messages = self.returnMessages(length,memory_percent,tag=["用户信息"],importance=5)
            messages = self.returnMessages(length,memory_percent,tag,importance=importance+1)
        else:
            return messages
    
    def is_valid_json(self,json_obj:dict):
        if not isinstance(json_obj, dict):
            return False
    
        # 检查是否包含必要的键
        if "role" not in json_obj or "content" not in json_obj:
            return False
    
        allowed_roles = {"system", "user", "assistant"}
        if json_obj["role"] not in allowed_roles:
            return False
    
        # 检查content的值是否是字符串
        if not isinstance(json_obj["content"], str):
            return False
    
        return True