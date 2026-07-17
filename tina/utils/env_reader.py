import os
import dotenv

from ..core import logger


class EnvReader:
    # 新旧键名映射表：新键名 -> (旧键名列表)
    KEY_MAP = {
        "api_key": ["LLM_API_KEY"],
        "base_url": ["BASE_URL"],
        "model": ["MODEL_NAME"],
        "temperature": ["TEMPERATURE"],
        "max_input": ["MAX_INPUT"],
        "top_k": ["TOP_K"],
    }

    def __init__(self, env_file=".env"):
        """
        Initializes the EnvReader with the specified environment file.
        :param env_file: Path to the .env file (default is ".env").
        """
        self.env_file = env_file
        self.envs = self.load_env()

    def load_env(self):
        """
        Loads environment variables from the specified .env file.
        文件不存在时返回空字典，不抛出异常。
        """
        if os.path.exists(self.env_file):
            return dotenv.dotenv_values(self.env_file)
        else:
            logger.warning(f"EnvReader - 环境配置文件 '{self.env_file}' 未找到，跳过读取")
            return {}

    def get_env(self, key):
        """
        Returns the value of the specified environment variable.
        :param key: Name of the environment variable.
        :return: Value of the environment variable.
        """
        return self.envs.get(key)

    def _get_with_fallback(self, new_key: str, old_keys: list[str]) -> str | None:
        """
        先查新键名，没有则回退旧键名（同时打印废弃提示）
        """
        # 先查新键名
        value = self.get_env(new_key)
        if value is not None:
            return value

        # 回退旧键名
        for old_key in old_keys:
            value = self.get_env(old_key)
            if value is not None:
                logger.warning(
                    f"EnvReader - 环境变量 '{old_key}' 已废弃，请改为 '{new_key}'"
                )
                return value

        return None

    def get_api_key(self):
        """
        获取 API Key。
        新键名: api_key    旧键名: LLM_API_KEY
        """
        return self._get_with_fallback("api_key", ["LLM_API_KEY"])

    def get_base_url(self):
        """
        获取 Base URL。
        新键名: base_url    旧键名: BASE_URL
        """
        return self._get_with_fallback("base_url", ["BASE_URL"])

    def get_model(self):
        """
        获取模型名称。
        新键名: model       旧键名: MODEL_NAME
        """
        return self._get_with_fallback("model", ["MODEL_NAME"])

    def get_temperature(self):
        """
        获取温度参数。
        新键名: temperature 旧键名: TEMPERATURE
        """
        return self._get_with_fallback("temperature", ["TEMPERATURE"])

    def get_max_input(self):
        """
        获取最大输入长度。
        新键名: max_input   旧键名: MAX_INPUT
        """
        return self._get_with_fallback("max_input", ["MAX_INPUT"])

    def get_top_k(self):
        """
        获取 Top-K 参数。
        新键名: top_k       旧键名: TOP_K
        """
        return self._get_with_fallback("top_k", ["TOP_K"])

    # === 向后兼容：保留旧方法名 ===

    def getTemperature(self):
        """已废弃，请使用 get_temperature()"""
        logger.warning("EnvReader - getTemperature() 已废弃，请使用 get_temperature()")
        return self.get_temperature()

    def getMaxInput(self):
        """已废弃，请使用 get_max_input()"""
        logger.warning("EnvReader - getMaxInput() 已废弃，请使用 get_max_input()")
        return self.get_max_input()

    def getTopK(self):
        """已废弃，请使用 get_top_k()"""
        logger.warning("EnvReader - getTopK() 已废弃，请使用 get_top_k()")
        return self.get_top_k()