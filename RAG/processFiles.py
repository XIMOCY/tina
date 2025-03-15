"""
编写者：王出日
日期：2024，12，1
版本？
对文件进行处理包括：
1.文本类文件：docx，txt，pdf
    已经实现
2.图片类文件：jpg，png，gif
    未实现

内含：

1.docxToTxt(docx_file,isClean = False)：对docx文件进行处理，返回docx文件内容，每段内容用换行符分隔
2.pdfToTxt(pdf_file,isClean = False)：对pdf文件进行处理，返回pdf文件内容，每段内容用换行符分隔
3.txtToTxt(txt_file,isClean = False)：对txt文件进行处理，返回txt文件内容，每段内容用换行符分隔
"""

import os
import docx
import PyPDF2
import urllib.request

from typing import Union,Generator
from .utils import cleaning, segment

class FileProcess:
    """文件处理类"""
    def __init__(self):
        pass
    def read_file(self,file_path:str=None,file_url:str=None)->str:
        """通过文件路径自动判断文件类型并读取文件内容"""
        if file_path is not None:
            return fileToTxtByExten(file_path=file_path)
        elif file_url is not None:
            try:
                response = urllib.request.urlopen(file_url)
                content = response.read()
                content = content.decode('utf-8')
                return content
            except Exception as e:
                print(f"处理文件 {file_url} 时出错了：{e}")
                raise
        elif file_path is not None and file_url is not None:
            raise ValueError("文件路径和文件url不能同时存在")
        else:
            raise ValueError("文件路径和文件url不能同时为空")
    

def process_document(content: str, isClean: bool, isSegments: bool, n: int,step:int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """处理文本内容，进行数据清洗和分段"""
    if isClean:
        content = cleaning(content)
    return segment(content, n,step,is_yield) if isSegments else [content]


def docxToTxt(docx_file: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """对docx文件进行处理"""
    try:
        doc = docx.Document(docx_file)
        content = '\n'.join(para.text.strip() for para in doc.paragraphs if para.text.strip())
        return process_document(content, isClean, isSegments, n,step, is_yield)
    except Exception as e:
        print(f"处理文件 {docx_file} 时出错了：{e}")
        raise


def pdfToTxt(pdf_file: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """对pdf文件进行处理"""
    try:
        with open(pdf_file, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            content = ''.join(page.extract_text().strip() + '\n' for page in pdf.pages if page.extract_text())
            return process_document(content, isClean, isSegments, n,step, is_yield)
    except Exception as e:
        print(f"处理文件 {pdf_file} 时出错了：{e}")
        raise


def txtToTxt(txt_file: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """对txt文件进行处理""" 
    try:
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read().strip().split('\n')
            cleaned_content = '\n'.join(para for para in content if para.strip())
            return process_document(cleaned_content, isClean, isSegments, n,step, is_yield)
    except Exception as e:
        print(f"处理文件 {txt_file} 时出错了：{e}")
        raise

def mdToTxt(md_file: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """对md文件进行处理"""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read().strip().split('\n')
            cleaned_content = '\n'.join(para for para in content if para.strip())
            return process_document(cleaned_content, isClean, isSegments, n,step, is_yield)
    except Exception as e:
        print(f"处理文件 {md_file} 时出错了：{e}")
        raise

def fileToTxt(file_path: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> list[str]:
    """对文件夹内所有文件进行处理"""
    if os.path.isfile(file_path):
        return fileToTxtByExten(file_path, isClean, isSegments, n,step, is_yield)

    content_list = []
    file_list = os.listdir(file_path)
    for file in file_list:
        full_file_path = os.path.join(file_path, file)
        content_list.extend(fileToTxtByExten(full_file_path, isClean, isSegments, n,step, is_yield))
    return content_list


def fileToTxtByExten(file_path: str, isClean: bool = False, isSegments: bool = False, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator,list[str]]:
    """根据文件扩展名调用相应的转换函数"""
    file_suffix = os.path.splitext(file_path)[1]
    if file_suffix == '.docx':
        return docxToTxt(file_path, isClean, isSegments, n,step, is_yield)
    # elif file_suffix == '.doc':
    #     return docToTxt(file_path, isClean, isSegments, n)
    elif file_suffix == '.pdf':
        return pdfToTxt(file_path, isClean, isSegments, n,step, is_yield)
    elif file_suffix == '.txt':
        return txtToTxt(file_path, isClean, isSegments, n,step, is_yield)
    elif file_suffix == '.md':
        return mdToTxt(file_path, isClean, isSegments, n,step, is_yield)
    #出现非法文件类型时，返回空列表
    else:
        return [f"该文件类型暂不支持，格式为{file_suffix},告诉用户使用docx,pdf,txt文件"]


class Image:
    """图片类"""
    def __init__(self):
        pass
