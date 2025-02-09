"""
编写者：王出日
日期：2024，12，1
版本？
记忆模块，用于存储和读取记忆数据，通过使用SQLite来对用户的消息做管理
importance为重要程度，由大模型评分，越重要，分数越高，越不容易被忘记
！！！注意：
该记忆模块可能更加像消息管理模块，因为它不对大模型内部进行处理，
涉及更底层的东西，请在 tina.core.LLM.memory 查看
内含：
-memory类
"""
import json
import os
import sqlite3
import datetime
from .LLM.tina import tina
from .manage import TinaFolderManager
from .textSegments import TextSegments
from .processFiles import fileToTxtByExten


class Memory:
    def __init__(self):
        self.folder = TinaFolderManager.getMemory()
        self.conn = sqlite3.connect(os.path.join(self.folder, "memory.db"))
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL,
            time TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            importance INTEGER NOT NULL
            )
        '''
        )
        self.prompt="""
        请按照以下格式和准则为记忆打分，从1-5分，1分最低，5分最高，返回数字即可：

        {"role":"谁","tag":"什么","content":"提取主要的内容，将无关描述去除","importance":1-5}
        role:分为 system,user,assistant。如果是系统信息，则填写system；如果是用户信息，则填写user；如果是助手信息，则填写assistant。
        tag:描述信息的种类，种类有：个人信息，聊天信息，请求信息，指令信息
        content:提取主要的内容，将无关描述去除。例如，对于“我是王出日，我是一名程序员”，content为“用户名叫王出日，是一名程序员”
        分数越高表示重要程度越高，被遗忘的概率越低。首先要明确是谁说的话，然后再输入内容，最后输入分数。具体内容如下：

        与用户相关的信息（例如用户的个人信息、偏好等）：重要程度最高，得分为5。
        描述工作类信息（例如工作职责、项目进度等）：重要程度较低，得分为2。
        关于我的信息（例如我是谁、我的功能等）：重要程度比用户的信息低，得分为3。
        5分的信息将会作为长期记忆，不会被遗忘，适用于用户的个人信息，他的喜好，他发出的命令等。
        4分的信息将会被记录，使用用于用户提到的他的某些信息，他的社交和朋友信息等。
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
        msg_role = message["role"]
        msg_content = message["content"]
        result = LLM.predict(
                input_text = f"role:'{msg_role},content:'{msg_content}'",
                sys_prompt = self.prompt,
                format = "json",
                json_format = '{"role":"","tag":"","content":"","importance":1-5}'
            )
        result_dict = json.loads(result["content"])
        if self.is_valid_json(result_dict):
            time = datetime.datetime.now().strftime("%Y年-%m月-%d日 %H时:%M分")
            self.insertInSQLite(result_dict, time)
        else:
            self.insertInSQLite({"role": "", "content": "", "main_content": "", "importance": 0}, time)
        return result_dict


    def insertInSQLite(self, result_dict, time):
        self.cursor.execute('''
            INSERT INTO logs(tag, time, role, content, importance)
            VALUES (?,?,?,?,?)
            ''', (result_dict["tag"], time, result_dict["role"], result_dict["content"], result_dict["importance"])
            )
        self.conn.commit()
    
    def forget(self,importence:int=1) -> None:
        """
        遗忘用户信息
        Args:
            importance: 1-5 重要程度，在这里也叫遗忘指数，越高表示越重要，越低表示越不重要
        """
        self.cursor.execute(
            '''DELETE FROM logs WHERE importance <=?''',
            (importence,)
        )
        self.conn.commit()
        
    def recallByTime(self,time:str):
        """
        根据时间戳获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE time =?''',
            (time,)
        )
        result = self.cursor.fetchone()
        if result:
            message = {
                "role": result[3],
                "content": result[4]
            }
            return message
        else:
            return None
        
    def recallByTag(self,tag:str):
        """
        根据tag获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE tag =?''',
            (tag,)
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
        
    def recallByRole(self,role:str):
        """
        根据role获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE role =?''',
            (role,)
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
        
    def recallByAll(self,role:str,tag:str,content:str,importance:int):
        """
        根据所有条件获取记忆信息
        """
        self.cursor.execute(
            '''SELECT * FROM logs WHERE role =? AND tag =? AND content LIKE ? AND importance =?''',
            (role,tag,f"%{content}%",importance)
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
    def returnMessages(self)->list:
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
        self.cursor.execute('''SELECT * FROM logs''')
        result = self.cursor.fetchall()
        messages = []
        for row in result:
            message = {
                "role": row[3],
                "content": row[2] + " " + row[4]
            }
            messages.append(message)
        return messages
        
    def rememberImportantMessage(LLM:type,message:str) -> None:
        """
        记入重要信息，比如用户的个人信息、工作信息等
        """
        pass
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