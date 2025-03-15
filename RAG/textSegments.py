"""
编写者：王出日
日期：2024，12，1
版本？
描述：
文本分段类
功能：
1. 文本分段
2. 获取指定编号的分段结果
3. 找到第几段
"""

import os
import pickle
import pathlib
import shutil

from ..core.manage import TinaFolderManager
from .processFiles import fileToTxtByExten 

class TextSegments:
    def __init__(self, folder_path:str=''):
        self.folder_path = folder_path
        self.segment_path = TinaFolderManager.getSegment()
    
    def getMaxId(self):
        #获取当前最大编号
        if not os.path.exists(os.path.join(self.segment_path, 'id.txt')):
            max_id = 0
            for file in os.listdir(self.segment_path):
                if file.startswith('seg_'):
                    id = int(file.split('_')[1])
                    if id > max_id:
                        max_id = id
            return max_id
        else:
            with open(os.path.join(self.segment_path, 'id.txt'), 'r') as f:
                max_id = int(f.read())
            return max_id
        
    def segments(self, n:int,isCopyFileToTinaFolder:bool=False):
        """
        分段方法
        Args:
            n:每段的字数
            isCopyFileToTinaFolder:是否将文件复制到Tina的文件夹中
        """
        for file in os.listdir(self.folder_path):
            text_list = fileToTxtByExten(
                os.path.join(self.folder_path, file),
                isClean=True,
                isSegments=True,
                n=n
                )
            if isCopyFileToTinaFolder:
                shutil.copy2(os.path.join(self.folder_path, file), TinaFolderManager.getDocumentFolder())

            #构建文件名，数字+文件名+内分段数，数字从0开始
            file_name = self.__getId() + '_' + file + '_' + str(len(text_list))+'.pkl'
            #保存分段结果
            with open(os.path.join(self.segment_path, file_name), 'wb') as f:
                pickle.dump(text_list, f)
            
        
    def get(self, id:int):
        #获取指定文件的所有分段结果
        for file in os.listdir(self.segment_path):
            if file.startswith('seg_') and file.endswith('.pkl'):
                #提取末尾分段数
                num = int(pathlib.Path(file).stem.split('_')[1])
                if num == id:
                    with open(os.path.join(self.segment_path, file), 'rb') as f:
                        result = pickle.load(f)
                    return result
        
    def find(self, n:int):
        #找到第几段
        num = 0
        for file in os.listdir(self.segment_path):
            if file.startswith('seg_') and file.endswith('.pkl'):
                #提取末尾分段数
                num += int(pathlib.Path(file).stem.split('_')[3])
                if num < n:
                    continue
                elif num >= n:
                    with open(os.path.join(self.segment_path, file), 'rb') as f:
                        result = pickle.load(f)
                    return result[n-num-1]                       
                else:
                    raise IndexError('查找值超出范围！')
                
    def findFile(self,file_name:str):
        #查找指定文件对应的分段文件地址
        for file in os.listdir(self.segment_path):
            if file.startswith('seg_') and file.endswith('.pkl'):
                segment_onthistimesname = pathlib.Path(file).stem.split('_')[2]
                if segment_onthistimesname == file_name:
                    return os.path.join(self.segment_path, file)
                
    def __getId(self):
        #获取当前最大编号
        if not os.path.exists(os.path.join(self.segment_path, 'id.txt')):
            max_id = 0
            for file in os.listdir(self.segment_path):
                if file.startswith('seg_'):
                    id = int(file.split('_')[1])
                    if id > max_id:
                        max_id = id
            with open(os.path.join(self.segment_path, 'id.txt'), 'w') as f:
                f.write(str(max_id + 1))
            return'seg_' + str(max_id + 1)
        else:
            with open(os.path.join(self.segment_path, 'id.txt'), 'r') as f:
                max_id = int(f.read())
            with open(os.path.join(self.segment_path, 'id.txt'), 'w') as f:
                f.write(str(max_id + 1))
            return'seg_' + str(max_id + 1)