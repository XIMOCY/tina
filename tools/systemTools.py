import os
import datetime
    
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

