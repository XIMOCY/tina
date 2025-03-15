"""
编写者：王出日
日期：2024，12，1
版本？
实用工具：
1. cleaning(text)：清理文本，去除乱码、空格、换行符、制表符等
2. segment(text,n=100)：将文本分段，每段不超过n个字符
"""
__all__ = ['cleaning','segment']

import re
from typing import Union,Generator

def cleaning(text: str,word:list=['\u3000','\xa0','\u2003','\u2002','\u2004','\u2005','\u2006','\u2007','\u2008','\u2009','\u200a','\u202f','\u205f','\u3000','\u2028','\u2029']) -> str:
    """
    清理文本，去除乱码、空格、换行符、制表符等，同时保留常用标点符号
    Args:
        text: 待清理文本
    Returns:
        str: 清理后的文本
    """
    # 定义需要保留的常用标点符号
    punctuation = r'，。！？；：“”‘’（）、.?!\'\";:'

    # 更新正则表达式以保留标点符号
    pattern = re.compile(r'[^、\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u0020-\u007E\u00A0-\u00FF' + punctuation + r']+')
    text = pattern.sub('', text)
    text = text.replace('\n', '').replace('\t', '').replace('\r', '')
    
    return text

def segment(text: str, n: int = 100, step: int = None, is_yield: bool = False) -> Union[Generator, list]:
    """
    将文本分段，每段不超过n个字符，可以指定步长达到滚动窗口的效果，同时在大文本量时可以使用生成器节省内存
    Args:
        text: 待分段文本
        n: 每段字符数
        step: 分段步长,如果不指定则默认为n
        is_yield: 是否使用生成器返回结果，默认为False
    Returns:
        Union[Generator, list]: 分段后的文本生成器或列表
    """
    if step is None:
        step = n
    
    if len(text) <= n:
        return [text]
    else:
        if is_yield:
            def gen():
                for i in range(0, len(text) - n + 1, step):
                    yield text[i:i + n]
            return gen()
        else:
            return [text[i:i + n] for i in range(0, len(text) - n + 1, step)]
