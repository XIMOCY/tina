"""
编写者：王出日
日期：2024，12，13
版本？
tina提供的查询文档工具，可以根据输入的文本进行向量检索，并返回最相似的文档。
"""
import os
import numpy as np
import faiss
from tina.RAG.Embedding.embedding import Embedding
from tina.core.manage import TinaFolderManager
from tina.RAG.textSegments import TextSegments

def query(query_text, n=10)->list:
    """
    根据输入的文本进行向量检索，并返回最相似的文档片段。
        Args:
            query_text: 输入的文本
            n: 返回的文档片段数量
        Returns:
            最相似的文档片段列表
    """
    text_segments = TextSegments()
    text_embedding = Embedding()
    faiss_index = faiss.read_index(os.path.join(TinaFolderManager.getFaissIndex()))
    query_embedding = text_embedding.embedding(query_text)
    distances, indices = faiss_index.search(np.array([query_embedding]).reshape(1, -1), n)
    indices = indices.tolist()[0]
    results = []
    counter = 0
    for i in indices:
        if i == -1:
            break
        results.append(text_segments.find(i+1))
        counter += 1
    
        
    return results, counter
        