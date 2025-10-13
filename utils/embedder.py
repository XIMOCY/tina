import numpy as np
from typing import List, Optional, Union
from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """嵌入模型基类"""
    
    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        为文本生成嵌入向量
        
        Args:
            texts: 单个文本或文本列表
            
        Returns:
            嵌入向量列表
        """
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """嵌入向量的维度"""
        pass


class DummyEmbedder(BaseEmbedder):
    """虚拟嵌入模型，用于测试"""
    
    def __init__(self, dimension: int = 768):
        self._dimension = dimension
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """生成随机嵌入向量"""
        if isinstance(texts, str):
            # 单个文本
            return np.random.rand(1, self._dimension).tolist()
        else:
            # 文本列表
            return np.random.rand(len(texts), self._dimension).tolist()
    
    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """
        使嵌入模型可以像函数一样被调用，符合ChromaDB的要求
        """
        return self.embed(input)


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于SentenceTransformer的嵌入模型"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化SentenceTransformer嵌入模型
        
        Args:
            model_name: 模型名称
        """
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self._dimension = self.model.get_sentence_embedding_dimension()
        except ImportError:
            raise ImportError(
                "需要安装sentence-transformers库: pip install sentence-transformers"
            )
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """生成嵌入向量"""
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = self.model.encode(texts)
        return embeddings.tolist()
    
    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """
        使嵌入模型可以像函数一样被调用，符合ChromaDB的要求
        """
        return self.embed(input)


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI嵌入模型"""
    
    def __init__(self, 
                 api_key: str,
                 model_name: str = "text-embedding-ada-002",
                 base_url: Optional[str] = None):
        """
        初始化OpenAI嵌入模型
        
        Args:
            api_key: API密钥
            model_name: 模型名称
            base_url: API基础URL（可选，用于兼容其他平台）
        """
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.model_name = model_name
            # OpenAI嵌入模型维度是固定的
            self._dimension = 1536 if "ada" in model_name else 768
        except ImportError:
            raise ImportError("需要安装openai库: pip install openai")
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """生成嵌入向量"""
        if isinstance(texts, str):
            texts = [texts]
            
        response = self.client.embeddings.create(
            input=texts,
            model=self.model_name
        )
        
        embeddings = [item.embedding for item in response.data]
        return embeddings
    
    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """
        使嵌入模型可以像函数一样被调用，符合ChromaDB的要求
        """
        return self.embed(input)


class DashScopeEmbedder(BaseEmbedder):
    """DashScope（阿里云）嵌入模型"""
    
    def __init__(self, 
                 api_key: str,
                 model_name: str = "text-embedding-v1"):
        """
        初始化DashScope嵌入模型
        
        Args:
            api_key: API密钥
            model_name: 模型名称
        """
        try:
            import dashscope
            dashscope.api_key = api_key
            self.model_name = model_name
            # DashScope嵌入模型维度
            self._dimension = 1024 if "text-embedding-v2" in model_name else 1536
        except ImportError:
            raise ImportError("需要安装dashscope库: pip install dashscope")
    
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """生成嵌入向量"""
        try:
            import dashscope
            from dashscope import TextEmbedding
            
            if isinstance(texts, str):
                texts = [texts]
                
            embeddings = []
            for text in texts:
                response = TextEmbedding.call(
                    model=self.model_name,
                    input=text
                )
                
                if response.status_code == 200:
                    embeddings.append(response.output['embeddings'][0]['embedding'])
                else:
                    raise Exception(f"嵌入生成失败: {response.message}")
                    
            return embeddings
        except Exception as e:
            raise Exception(f"DashScope嵌入模型调用失败: {str(e)}")
    
    @property
    def dimension(self) -> int:
        return self._dimension

    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """
        使嵌入模型可以像函数一样被调用，符合ChromaDB的要求
        """
        return self.embed(input)


def get_embedder(embedder_type: str, **kwargs) -> BaseEmbedder:
    """
    获取嵌入模型实例
    
    Args:
        embedder_type: 嵌入模型类型 ('dummy', 'sentence_transformer', 'openai', 'dashscope')
        **kwargs: 模型特定参数
        
    Returns:
        嵌入模型实例
    """
    if embedder_type == "dummy":
        return DummyEmbedder(**kwargs)
    elif embedder_type == "sentence_transformer":
        return SentenceTransformerEmbedder(**kwargs)
    elif embedder_type == "openai":
        return OpenAIEmbedder(**kwargs)
    elif embedder_type == "dashscope":
        return DashScopeEmbedder(**kwargs)
    else:
        raise ValueError(f"不支持的嵌入模型类型: {embedder_type}")