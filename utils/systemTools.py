import os
import sys
import datetime
import platform
import subprocess
import threading
import time
from queue import Queue

def getTime() -> str:
    """获取当前系统时间"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
def shotdownSystem() -> None:
    """关机（Windows/Linux）"""
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

def getSoftwareList() -> list:
    """
    获取已安装软件列表
    Returns:
        软件名称列表
    """
    if platform.system() == "Windows":
        import winreg
        reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall")
        software_list = []
        try:
            i = 0
            while True:
                sub_key_name = winreg.EnumKey(reg_key, i)
                sub_key = winreg.OpenKey(reg_key, sub_key_name)
                try:
                    software_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                    software_list.append(software_name)
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(sub_key)
                i += 1
        except OSError:
            pass
        finally:
            winreg.CloseKey(reg_key)
        return software_list
    else:
        # Linux常见软件包管理器
        if os.path.exists("/usr/bin/dpkg"):
            return os.popen("dpkg -l | awk '{print $2}'").read().splitlines()
        elif os.path.exists("/usr/bin/rpm"):
            return os.popen("rpm -qa").read().splitlines()
        else:
            return []

def startSoftware(name: str) -> str:
    """
    启动指定软件（Windows/Linux）
    Args:
        name: 软件名或可执行文件名
    Returns:
        启动结果
    """
    try:
        if platform.system() == "Windows":
            os.startfile(name)
        else:
            subprocess.Popen([name])
        return f"{name} 启动成功"
    except Exception as e:
        return f"{name} 启动失败: {e}"

def openFile(path: str) -> str:
    """
    打开文件或文件夹（Windows/Linux）
    Args:
        path: 文件或文件夹路径
    Returns:
        打开结果
    """
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return f"{path} 已打开"
    except Exception as e:
        return f"打开失败: {e}"

def getProcessList() -> list:
    """
    获取当前进程列表
    Returns:
        进程信息列表
    """
    if platform.system() == "Windows":
        return os.popen('tasklist').read().splitlines()
    else:
        return os.popen('ps aux').read().splitlines()

def killProcess(pid: int) -> str:
    """
    杀死指定进程
    Args:
        pid: 进程ID
    Returns:
        操作结果
    """
    try:
        os.kill(pid, 9)
        return f"进程 {pid} 已被杀死"
    except Exception as e:
        return f"杀死进程失败: {e}"

def getEnv(var: str) -> str:
    """
    获取环境变量
    Args:
        var: 环境变量名
    Returns:
        环境变量值
    """
    return os.environ.get(var, "")

def getDiskInfo() -> str:
    """
    获取磁盘信息
    Returns:
        磁盘信息字符串
    """
    if platform.system() == "Windows":
        return os.popen("wmic logicaldisk get size,freespace,caption").read()
    else:
        return os.popen("df -h").read()

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
    process = subprocess.Popen(
        command, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    output, _ = process.communicate()
    return output