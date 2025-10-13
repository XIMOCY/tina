"""
设定多agent的运行环境
"""

class Environment:
    def __init__(self, agents):
        """
        初始化环境，接收多个agent
        :param agents: list of agents
        """
        self.agents = agents

        #共享消息池
        self.message_pool = []

    def generate(self,
                 agent_id,
                 content,
                 target_agent_id=None):
        """
        生成消息并添加到消息池
        :param agent_id: 发送消息的agent ID
        :param content: 消息内容
        :param target_agent_id: 接收消息的agent ID（可选）
        """
        message = {
            'agent_id': agent_id,
            'content': content,
            'target_agent_id': target_agent_id
        }
        self.message_pool.append(message)