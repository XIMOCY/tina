import os
import datetime
import platform
import subprocess
import time
from tina import Tools

system_tools = Tools()

@system_tools.register()
def get_time() -> str:
    """
    获取当前系统时间
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@system_tools.register(require_confirmation=True)
def make_dir(path: str) -> None:
    """
    创建目录
    Args:
        path: 目录路径
    Returns:
        目录绝对路径
    """
    if not os.path.exists(path):
        os.makedirs(path)
    return os.path.abspath(path)

@system_tools.register()
def list_dir(path: str) -> list[str]:
    """
    打印目录结构
    Args:
        path: 目录路径
    """
    if not os.path.exists(path):
        print(f"❌ 路径不存在：{path}")
        return
    return os.listdir(path)

@system_tools.register()
def get_path(path: str) -> str:
    """
    获取一个文件或者文件夹的绝对路径
    Args:
        path: 文件或者文件夹路径
    Returns:
        文件或者文件夹的绝对路径
    """
    return os.path.abspath(path)

@system_tools.register()
def read_code(path: str,start:int=0,end:int = 2000) -> str:
    """
    读取文件内容
    Args:
        path: 文件路径
        start: 起始位置（默认0）
        end: 结束位置（默认2000）
    Returns:
        文件内容
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return content[start:end]
    except FileNotFoundError:
        return f"文件不存在：{path}"
    except UnicodeDecodeError:
        return f"无法解码文件：{path}，请检查文件编码格式"

@system_tools.register(require_confirmation=True)  
def write_code(path: str, content: str) -> None:
    """
    写入文件内容，如果文件不存在会自动创建，但是不存在的父文件夹无法创建
    Args:
        path: 文件路径
        content: 文件内容
    Returns:
        文件绝对路径
    
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)

@system_tools.register()
def shot_down_system() -> None:
    """
    关机（Windows/Linux）
    Returns:
        None
    """
    sure = input("确定关机吗？（Y/n)")
    if sure.lower() == "y":
        if platform.system() == "Windows":
            os.system("shutdown -s -t 0")
        else:
            os.system("shutdown -h now")
    elif sure.lower() == "n":
        print("取消关机")
    else:
        print("输入错误，取消关机")
    
@system_tools.register()
def delay(seconds: int, why: str = "延迟响应") -> str:
    """
    延时函数
    Args:
        seconds: 延时秒数
        why: 延时原因
    Returns:
        延时结束提示
    """
    time.sleep(seconds)
    return f"{why}时间到了"

@system_tools.register()
def terminal(command: str) -> str:
    """
    在终端运行指令
    Args:
        command: 指令内容
    Returns:
        指令输出
    """
    if platform.system() == "Windows":
        try:
            process = subprocess.Popen(
                 ["powershell", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            output, _ = process.communicate()
            return output
        except UnicodeDecodeError:
            output = output.decode("gbk").encode("utf-8",errors="replace").decode("utf-8")

        return output
    else:
        process = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8"
        )
        output, _ = process.communicate()
        return output