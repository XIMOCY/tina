import logging
import os
from typing import Optional


class Logger:
    _instance: Optional["Logger"] = None
    _initialized: bool = False

    _LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        log_file: str = "logs/tina.log",
        level: str = "DEBUG",  # 日志系统整体最低级别（通常 DEBUG）
        console: bool = True,
        console_level: str = "ERROR",  # 控制台默认只打印 ERROR+
    ):
        if Logger._initialized:
            return

        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        self.logger = logging.getLogger("tina")
        self.logger.setLevel(self._to_level(level))
        self.logger.handlers.clear()

        self.formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 控制台 handler
        self.console_handler: Optional[logging.Handler] = None
        if console:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setFormatter(self.formatter)
            self.console_handler.setLevel(self._to_level(console_level))
            self.logger.addHandler(self.console_handler)

        # 文件 handler
        self.file_handler = logging.FileHandler(log_file, encoding="utf-8")
        self.file_handler.setFormatter(self.formatter)
        # 文件一般记录完整一点，用整体 level
        self.file_handler.setLevel(self._to_level(level))
        self.logger.addHandler(self.file_handler)

        Logger._initialized = True

    # 下面这些是方便用的封装方法
    def info(self, message: str):
        self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str):
        self.logger.error(message)

    def critical(self, message: str):
        self.logger.critical(message)

    def debug(self, message: str):
        self.logger.debug(message)

    def log(self, level: str, message: str):
        self.logger.log(self._to_level(level), message)

    def get_logger(self) -> logging.Logger:
        return self.logger

    def set_level(self, level: str):
        """设置整体日志级别（logger + 文件 handler）"""
        lvl = self._to_level(level)
        self.logger.setLevel(lvl)
        self.file_handler.setLevel(lvl)

    def set_console_level(self, level: str):
        """单独设置控制台输出级别"""
        if self.console_handler is None:
            return
        self.console_handler.setLevel(self._to_level(level))

    @classmethod
    def _to_level(cls, level: str) -> int:
        return cls._LEVEL_MAP.get(level.upper(), logging.INFO)
