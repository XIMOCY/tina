import os
import sys
import datetime
import platform
import subprocess
import time

def getTime() -> str:
    """获取当前系统时间"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def makeDir(path: str) -> None:
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
def listDir(path:str):
    """
    列出目录下的文件
    Args:
        path: 目录路径
    Returns:
        目录下的文件列表
    """
    if not os.path.exists(path):
        return []
    return os.listdir(path)
def getPath(path: str) -> str:
    """
    获取一个文件或者文件夹的绝对路径
    Args:
        path: 文件或者文件夹路径
    Returns:
        文件或者文件夹的绝对路径
    """
    return os.path.abspath(path)
def makeFile(path: str) -> None:
    """
    创建一个空文件
    Args:
        path: 文件路径
    Returns:
        文件绝对路径
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write("")
    return os.path.abspath(path)

def readFile(path: str) -> str:
    """
    读取文件内容
    Args:
        path: 文件路径
    Returns:
        文件内容
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
    
def writeFile(path: str, content: str) -> None:
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

def shotdownSystem() -> None:
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
    
def getSystemInfo() -> str:
    """获取系统信息（Windows/Linux）"""
    if platform.system() == "Windows":
        return os.popen("systeminfo").read()
    else:
        return os.popen("uname -a && lsb_release -a 2>/dev/null").read()

def getEnv(var: str) -> str:
    """
    获取环境变量
    Args:
        var: 环境变量名
    Returns:
        环境变量值
    """
    return os.environ.get(var, "")

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