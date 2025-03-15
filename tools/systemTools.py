import os
import datetime
import winreg
import subprocess

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


def openSoftware(software_name: str) -> bool:
    pass