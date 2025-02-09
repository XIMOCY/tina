"""
定义事件类
"""
class Event:
    def __init__(self, name, data=None):
        self.name = name
        self.data = data
class LLMEvent(Event):
    def __init__(self, name, data=None):
        super().__init__(name, data)
        self.state = 0
class LLMNotInputEvent(LLMEvent):
    def __init__(self):
        super().__init__(name="LLM_NOT_INPUT",date = 0)
    def binding(self, func:type):
        """
        绑定触发事件
        """
        self.func = func
        