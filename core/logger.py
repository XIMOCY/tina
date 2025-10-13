import logging

class Logger:
    def __init__(self,log_file:str="logs/tina.log",level:str="INFO",console:bool=False):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        self.logger.propagate = False
        self.formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.logger.handlers.append(logging.StreamHandler())
        self.logger.handlers.append(logging.FileHandler(log_file))
        self.logger.handlers[0].setFormatter(self.formatter)
        self.logger.handlers[1].setFormatter(self.formatter)

    def info(self,message:str):
        self.logger.info(message)

    def warning(self,message:str):
        self.logger.warning(message)

    def error(self,message:str):
        self.logger.error(message)

    def critical(self,message:str):
        self.logger.critical(message)

    def debug(self,message:str):
        self.logger.debug(message)

    def log(self,level:str,message:str):
        self.logger.log(level,message)

    def getLogger(self):
        return self.logger
    
    def setLevel(self,level:str):
        self.logger.setLevel(level)
        
    def setFormatter(self,formatter:logging.Formatter):
        self.logger.handlers[0].setFormatter(formatter)
        self.logger.handlers[1].setFormatter(formatter)