from event import Event
class Listener:
    def __init__(self, config):
        self.config = config
    def start(self):
        pass
    def stop(self):
        pass
    def bindings(self,event:Event):
        pass