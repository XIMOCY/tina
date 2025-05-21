import os
import dotenv

def load_env(env_path):
    dotenv.load_dotenv(dotenv_path=env_path)    

def get_env(key):
    return os.getenv(key)
