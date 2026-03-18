import os
import dotenv


class EnvReader:
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
        """
        if os.path.exists(self.env_file):
            return dotenv.dotenv_values(self.env_file)
        else:
            raise FileNotFoundError(f"Environment file '{self.env_file}' not found.")

    def get_env(self, key):
        """
        Returns the value of the specified environment variable.
        :param key: Name of the environment variable.
        :return: Value of the environment variable.
        """
        return self.envs.get(key)

    def get_api_key(self):
        """
        Returns the value of the LLM environment variable.
        :return: Value of the LLM environment variable.
        """
        return self.get_env("LLM_API_KEY")

    def get_base_url(self):
        """
        Returns the value of the BASE_URL environment variable.
        :return: Value of the BASE_URL environment variable.
        """
        return self.get_env("BASE_URL")

    def get_model(self):
        """
        Returns the value of the MODEL environment variable.
        :return: Value of the MODEL environment variable.
        """
        return self.get_env("MODEL_NAME")

    def getTemperature(self):
        """
        Returns the value of the TEMPERATURE environment variable.
        :return: Value of the TEMPERATURE environment variable.
        """
        return self.get_env("TEMPERATURE")

    def getMaxInput(self):
        """
        Returns the value of the MAX_TOKENS environment variable.
        :return: Value of the MAX_TOKENS environment variable.
        """
        return self.get_env("MAX_INPUT")

    def getTopK(self):
        """
        Returns the value of the TOP_K environment variable.
        :return: Value of the TOP_K environment variable.
        """
        return self.get_env("TOP_K")
