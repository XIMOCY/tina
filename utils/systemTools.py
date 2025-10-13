import os
import sys
import datetime
import platform
import subprocess
import time
import pathspec

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

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"

def format_mtime(path: str) -> str:
    try:
        timestamp = os.path.getmtime(path)
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
    except:
        return "未知时间"

def load_gitignore(base_path: str):
    """
    从 .gitignore 文件中加载忽略规则
    """
    gitignore_path = os.path.join(base_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None

    with open(gitignore_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
        return spec

def listDir(path: str, prefix: str = "", max_depth: int = -1, current_depth: int = 0, spec=None, root_path=None):
    """
    打印树状目录结构，支持大小、时间、深度限制、.gitignore忽略规则
    """
    if not os.path.exists(path):
        print(f"❌ 路径不存在：{path}")
        return

    if root_path is None:
        root_path = path  # 初始根目录记录下来
        spec = load_gitignore(path)  # 初始加载 .gitignore

    entries = sorted(os.listdir(path))
    for index, entry in enumerate(entries):
        full_path = os.path.join(path, entry)
        rel_path = os.path.relpath(full_path, root_path)  # 相对于根路径的路径
        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "
        sub_prefix = "    " if is_last else "│   "

        # 检查是否被 .gitignore 忽略
        if spec and spec.match_file(rel_path):
            continue

        mtime_str = format_mtime(full_path)

        if os.path.isdir(full_path):
            print(f"{prefix}{connector}📁 {entry}/   ({mtime_str})")
            if max_depth == -1 or current_depth < max_depth:
                listDir(full_path, prefix + sub_prefix, max_depth, current_depth + 1, spec, root_path)
        else:
            try:
                size = os.path.getsize(full_path)
                size_str = format_size(size)
            except:
                size_str = "未知大小"
            print(f"{prefix}{connector}📄 {entry}   ({size_str}, {mtime_str})")


def getPath(path: str) -> str:
    """
    获取一个文件或者文件夹的绝对路径
    Args:
        path: 文件或者文件夹路径
    Returns:
        文件或者文件夹的绝对路径
    """
    return os.path.abspath(path)

def readCode(path: str,start:int=0,end:int = 2000) -> str:
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
    
def writeCode(path: str, content: str) -> None:
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