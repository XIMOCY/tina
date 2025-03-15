import faiss

from .embedding import Embedding
from ...core.manage import TinaFolderManager
from ..textSegments import TextSegments
from ..processFiles import fileToTxtByExten

def docToVec(file_path,model_path = None,dimesion=768,n=500,isCopyToTinaFolder:bool = False):
    """
    将文本文件转换为向量，并建立Faiss索引。
        Args:
            file_path: 文本文件路径
            dimesion: 向量维度
            n: 每个文本分段的最大字数
        Returns:
            None
    """
    text_segments = TextSegments(file_path)
    text_embedding = Embedding(model_path=model_path)
    faiss_index = faiss.IndexFlatL2(dimesion)
    faiss_index_file = TinaFolderManager.getFaissIndex()
    text_segments.segments(n,isCopyFileToTinaFolder=isCopyToTinaFolder)
    for i in range(text_segments.getMaxId()):
        text = text_segments.get(i+1)
        if text == []:
            continue
        vec = text_embedding.embedding(text)
        faiss_index.add(vec)
    faiss.write_index(faiss_index, faiss_index_file)
    print("已将文本文件转换为向量并建立Faiss索引。")