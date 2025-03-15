"""
编写者：王出日
日期：2024，12，1
版本？
描述：
使用QwenEmbeddings库将文本转换为向量，并使用Faiss建立索引。
包含：
QwenDocvec(file_path)：将文本文件转换为向量，并建立Faiss索引。
"""

import os
import faiss
import numpy as np
from ..core.Embedding.QwenEmbeddings import TextEmbedding
from ..core.processFiles import fileToTxt
from ..core.manage import TinaFolderManager
from ..RAG.textSegments import TextSegments

def QwenDocToVec(file_path,dimesion=1536,n=500):
    """
    将文本文件转换为向量，并建立Faiss索引。
        Args:
            file_path: 文本文件路径
            dimesion: 向量维度
            n: 每个文本分段的最大句子数
        Returns:
            None
    """
    text_segments = TextSegments(file_path)
    text_embedding = TextEmbedding()
    faiss_index = faiss.IndexFlatL2(dimesion)
    faiss_index_file = TinaFolderManager.getFaissIndex()
    text_segments.segments(n)
    for i in range(text_segments.getMaxId()):
        text = text_segments.get(i+1)
        if text == []:
            continue
        vec = text_embedding.embedding(text)
        vec_np = np.array(vec)
        faiss_index.add(vec_np)
    faiss.write_index(faiss_index, faiss_index_file)