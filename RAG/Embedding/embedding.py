import numpy as np

from typing import Union

from ...core.manage import TinaFolderManager



class Embedding:
    def __init__(self, model_path: str = None, GPU_n: int = -1, log: bool = False):
        from llama_cpp import Llama
        if model_path is None:
            model_path = TinaFolderManager.getEmbedingModel()

        self.embeddingModel = Llama(model_path=model_path, embedding=True, n_gpu_layers=GPU_n, verbose=log)
        
    def embedding(self, input_str: Union[str, list[str]]) -> np.ndarray:
        if isinstance(input_str, str):
            return np.array(self.embeddingModel.create_embedding(input_str)["data"][0]["embedding"]).reshape(1, -1)
        elif isinstance(input_str, list):
            embeddings = []
            for i in input_str:
                embedding = np.array(self.embeddingModel.create_embedding(i)["data"][0]["embedding"])
                embeddings.append(embedding)
            return np.array(embeddings)
        else:
            raise TypeError("input_str 参数只能是str或list[str]类型")
