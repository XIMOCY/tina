"""
设定agent的环境
"""
import os
import platform
from core.manage import TinaFolderManager

class Environment:
    def __init__(self, work_path):
        self.work_path = work_path
        TinaFolderManager.init(work_path)
        self.OperationSystemDict = {
            "nt": "Windows",
            "posix": "Linux"
        }
        self.OperationSystem = self.OperationSystemDict.get(os.name)
        self.SystemVersion = platform.version()
        self.SystemRelease = platform.release()
        self.SystemPlatform = platform.platform()
        self.SystemArchitecture = platform.architecture()

    @property
    def info(self):
        return (f"系统：{self.OperationSystem},\n"
                f"版本：{self.SystemVersion},\n "
                f"发布：{self.SystemRelease}, \n"
                f"平台：{self.SystemPlatform}, \n"
                f"架构：{self.SystemArchitecture[0]},\n "
                f"工作目录：{self.work_path}\n") 

if __name__ == '__main__':
    env = Environment(r'D:\development\project\TCG\test')
    print(env.info)
