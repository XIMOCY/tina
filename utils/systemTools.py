import os
import datetime
import winreg
import subprocess
import threading
import time
from queue import Queue
def getTime() -> str:
    return datetime.datetime.now().strftime("%Y年-%m月-%d日 %H时%M分%S秒")
    
def shotdownSystem() -> None:
    sure = input("确定关机吗？（Y/n)")
    if sure.lower() == "y":
        os.system("shutdown -s -t 0")
    elif sure.lower() == "n":
        print("取消关机")
    else:
        print("输入错误，取消关机")
    

def getSystemInfo() -> str:
    return os.popen("systeminfo").read()

def getSoftwareList() -> str:
    reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    software_list = []
    try:
        i = 0
        while True:
            # 枚举子键
            sub_key_name = winreg.EnumKey(reg_key, i)
            sub_key = winreg.OpenKey(reg_key, sub_key_name)
            
            try:
                # 获取软件名称
                software_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                software_list.append(software_name)
            except FileNotFoundError:
                # 如果找不到DisplayName，跳过该软件
                pass
            finally:
                winreg.CloseKey(sub_key)
            i += 1
    except OSError:
        # 当枚举结束时，会抛出OSError
        pass
    finally:
        winreg.CloseKey(reg_key)
    return software_list


def terminal(command):
    """
    在终端运行指令
    Args:
        command: 指令内容
    returns:
        指令输出
    """

    # 新增：获取当前模块所在目录
    module_dir = os.path.dirname(os.path.abspath(__file__))

    def _stream_reader(pipe, queue):
        try:
            for line in iter(pipe.readline, ''):
                queue.put(line)
        finally:
            pipe.close()
            queue.put(None)  # 结束标志

    process = subprocess.Popen(
        ["powershell", "-Command", command],  # 修改：显式使用PowerShell
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        cwd=module_dir
    )
    
    q = Queue()
    t = threading.Thread(target=_stream_reader, args=(process.stdout, q))
    t.daemon = True
    t.start()

    output = []
    while True:
        line = q.get()  # 阻塞式获取输出
        if line is None:
            break
        output.append(line)

    t.join()  # 确保读取线程完成
    process.wait()  # 等待进程完全终止

    return ''.join(output)
def delay(seconds: int) -> None:
    """
    延时函数
    Args:
        seconds: 延时秒数
    """
    time.sleep(seconds)
    return "时间到了"