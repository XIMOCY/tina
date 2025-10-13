import sqlite3
import os
import datetime
import threading
from contextlib import contextmanager
from ..agent.core.tools import Tools

memories = Tools()

class Memory:
    def __init__(self, db_path: str = os.path.join(os.getcwd(), 'memory.tina')):
        self.db_path = db_path
        self.cache = {}  # 修复拼写错误
        self.lock = threading.Lock()  # 添加线程锁
        
        # 初始化数据库表（仅在数据库不存在时）
        self._init_database()
        
        # 记录数据库创建时间
        if os.path.exists(db_path):
            self.dbcreatetime = os.path.getctime(db_path)
        else:
            self.dbcreatetime = datetime.datetime.now().timestamp()

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    time TEXT, 
                    content TEXT
                )
            ''')
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器，确保连接正确关闭"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    def remember(self, content: str):
        """记忆重要信息到数据库"""
        if not content or not content.strip():
            return  # 空内容不记忆
            
        with self.lock:  # 确保线程安全
            with self._get_connection() as conn:
                cursor = conn.cursor()
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "INSERT INTO logs (time, content) VALUES (?, ?)", 
                    (current_time, content.strip())
                )
                conn.commit()
                
                # 插入后立即执行遗忘逻辑
                self._forget_old_memories(cursor, conn)

    def _forget_old_memories(self, cursor, conn):
        """遗忘过期的记忆（内部方法，在已有连接的情况下使用）"""
        now = datetime.datetime.now().timestamp()
        
        # 获取所有记录
        cursor.execute("SELECT id, time FROM logs")
        rows = cursor.fetchall()
        
        delete_ids = []
        for row_id, time_str in rows:
            try:
                row_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").timestamp()
                time_diff = now - row_time
                
                # 超过90天的记录自动删除
                if time_diff > 3600 * 24 * 90:  # 90天
                    delete_ids.append(row_id)
                    
            except ValueError:
                # 如果时间格式有问题，跳过这条记录
                continue
        
        # 批量删除过期记录
        if delete_ids:
            cursor.executemany("DELETE FROM logs WHERE id=?", [(id,) for id in delete_ids])
            conn.commit()

    def search(self, query: str) -> list:
        """搜索记忆信息"""
        with self.lock:  # 确保线程安全
            # 检查缓存
            if query in self.cache:
                return self.cache[query]
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM logs WHERE content LIKE ? ORDER BY time DESC", 
                    (f'%{query}%',)
                )
                result = cursor.fetchall()
                
                # 更新缓存
                self.cache[query] = result
                return result

    def clear_cache(self):
        """清空搜索缓存"""
        with self.lock:
            self.cache.clear()

    def returnMessages(self, limit: int = 20) -> list:
        """
        获取最近的记忆信息
        返回格式：
        [
            {
                "role": "system",
                "content": "<memory>记忆内容</memory>"
            }
        ]
        """
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT time, content FROM logs ORDER BY time DESC LIMIT ?", (limit,))
                result = cursor.fetchall()
                
                messages = []
                for time_str, content in result:
                    messages.append({
                        "role": "system",
                        "content": f"<memory>{content}</memory>"
                    })
                
                if messages:
                    messages.append({"role": "system", "content": "以上被<memory></memory>标记的是你的记忆信息"})
                
                return messages

    def getAllMemories(self) -> list:
        """获取所有记忆信息"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT time, content FROM logs ORDER BY time DESC")
                return cursor.fetchall()

    def get_stats(self) -> dict:
        """获取数据库统计信息"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM logs")
                total_count = cursor.fetchone()[0]
                
                # 获取最早和最新的记录时间
                cursor.execute("SELECT MIN(time), MAX(time) FROM logs WHERE time IS NOT NULL")
                time_range = cursor.fetchone()
                
                return {
                    "total_records": total_count,
                    "earliest_record": time_range[0] if time_range[0] else "无记录",
                    "latest_record": time_range[1] if time_range[1] else "无记录",
                    "database_created": datetime.datetime.fromtimestamp(self.dbcreatetime).strftime("%Y-%m-%d %H:%M:%S")
                }


# 创建全局实例
memory = Memory()

@memories.register()
def searchFromMemory(query: str) -> str:
    """
    搜索记忆信息。
    Args:
        query (str): 要搜索的内容。
    """
    result = memory.search(query)
    if len(result) == 0:
        return "未找到相关记忆。"
    else:
        return "\n".join([f"[{row[1]}] {row[2]}" for row in result])
    
@memories.register()
def toDoList(content: str) -> str:
    """
    添加待办事项，按照下面的格式：
    - ~~日期（2022-01-01-08:00） 待办事项内容（内容）~~
    - 日期（2022-01-01-08:00） 待办事项内容（内容）

    📌 用途说明：
    用于记录用户的待办事项，便于后续查看和管理。
    已经完成的消息，请手动添加~~标记~~，以便于区分。

    ✅ 使用原则：
    - 待办事项内容应简洁明了，避免过多信息干扰；
    - 待办事项内容应结构清晰、事实明确、可长期使用；
    - 待办事项内容应与用户的身份、兴趣、习惯、偏好、关键指令等相关；
    - 待办事项内容应与用户的日常生活息息相关。


    Args:
        content (str): 待办事项内容。
    """
    with open('todo.md', 'w', encoding='utf-8') as f:
        f.write(content)
    return "已添加到待办事项清单！"

@memories.register()
def remember(content: str):
    """
   🧠 记忆重要信息（用户长期偏好与身份特征）

    📌 用途说明：
    用于记录长期有价值的用户信息，如身份、兴趣、习惯、偏好、关键指令等。

    ✅ 使用原则：
    - 仅在遇到明确且长期有效的信息时调用；
    - 不记录无效聊天（如寒暄、确认语）；
    - 内容应结构清晰、事实明确、可长期使用；
    - 不重复记录相同信息。

    🧾 参数说明：
    content (str): 需要记忆的核心信息，应简洁、明确，指明说话者、行为或偏好。

    ✍️ 内容格式要求：
    - 需包含“用户...”或“用户表示...”等结构，避免非事实性内容；
    - 每次调用仅传递一条清晰、独立的信息；
    - 去除口语化、修饰词，聚焦事实表达。


    🛑 不应调用的内容示例：
    - "用户说你好"（无信息量）
    - "用户问你是谁"（无用户偏好）
    - "知道了"（重复性确认，无需存储）
    Args:
        content (str): 要记忆的内容
    Returns:
        str: 操作结果提示
    """
    memory.remember(content)
    return "记忆已更新！"

@memories.register()
def getMemoryStats() -> str:
    """
    获取记忆数据库的统计信息。
    """
    stats = memory.get_stats()
    return f"记忆统计: 总记录数={stats['total_records']}, 最早记录={stats['earliest_record']}, 最新记录={stats['latest_record']}, 数据库创建时间={stats['database_created']}"

@memories.register()
def clearMemoryCache() -> str:
    """
    清空记忆搜索缓存。
    """
    memory.clear_cache()
    return "记忆缓存已清空！"

@memories.register()
def getRecentMemories(limit: int = 10) -> list:
    """
    获取最近的记忆信息，用于添加到对话上下文中。
    
    Args:
        limit (int): 获取记忆的数量限制，默认10条
    
    Returns:
        list: 包含记忆信息的消息列表，格式为system role
    """
    return memory.returnMessages(limit)

if __name__ == '__main__':
    print(memories) 