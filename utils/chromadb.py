import os
import uuid
import numpy as np
from typing import List, Dict, Any, Optional, Union, Callable
import chromadb
from chromadb.config import Settings
from .text_splitter import TextSplitter
from .embedder import BaseEmbedder, DummyEmbedder


class ChromaDB:
    """
    ChromaDB向量数据库封装类
    实现文档存储、向量检索和持久化功能
    """

    def __init__(self, 
                 name: str,
                 persist_directory: Optional[str] = None,
                 embedding_function: Optional[Callable] = None,
                 embedder: Optional[BaseEmbedder] = None,
                 text_splitter: Optional[TextSplitter] = None,
                 splitter_config: Optional[Dict[str, Any]] = None):
        """
        初始化ChromaDB
        
        Args:
            name: 数据库名称
            persist_directory: 持久化存储目录
            embedding_function: 嵌入函数（已废弃，建议使用embedder参数）
            embedder: 嵌入模型实例
            text_splitter: 文本分割器
            splitter_config: 文本分割器配置参数
        """
        self.name = name
        self.embedder = embedder
        
        # 创建文本分割器
        if text_splitter is not None:
            self.text_splitter = text_splitter
        elif splitter_config is not None:
            self.text_splitter = TextSplitter(**splitter_config)
        else:
            self.text_splitter = TextSplitter()
        
        # 配置Chroma客户端
        if persist_directory:
            # 确保存储目录存在
            os.makedirs(persist_directory, exist_ok=True)
            # 使用持久化存储
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
        else:
            # 使用内存存储
            self.client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False)
            )
            
        # 处理嵌入函数
        if embedding_function is not None:
            # 已废弃的参数，但仍支持向后兼容
            self.embedding_function = embedding_function
        elif embedder is not None:
            # 使用新的嵌入模型接口
            self.embedding_function = self._embed_with_embedder
        else:
            # 默认使用虚拟嵌入模型
            self.embedder = DummyEmbedder()
            self.embedding_function = self._embed_with_embedder
            
        # 获取或创建集合
        try:
            self.collection = self.client.get_collection(name=name)
        except:
            # 集合不存在，创建新集合
            self.collection = self.client.create_collection(
                name=name,
                embedding_function=self.embedding_function
            )

    def _embed_with_embedder(self, input: Union[str, List[str]]) -> List[List[float]]:
        """
        使用嵌入模型生成嵌入向量 (符合ChromaDB接口要求)
        
        Args:
            input: 输入文本或文本列表
            
        Returns:
            嵌入向量列表
        """
        return self.embedder.embed(input)

    def add_documents(self, 
                      documents: List[Dict[str, Any]], 
                      embeddings: Optional[List[List[float]]] = None) -> List[str]:
        """
        添加文档到数据库
        
        Args:
            documents: 文档列表，每个文档包含content和metadata
            embeddings: 可选的预计算嵌入向量
            
        Returns:
            添加的文档ID列表
        """
        ids = []
        contents = []
        metadatas = []
        
        for doc in documents:
            # 生成唯一ID
            doc_id = str(uuid.uuid4())
            ids.append(doc_id)
            
            # 提取内容
            contents.append(doc.get("content", ""))
            
            # 提取元数据
            metadata = doc.get("metadata", {})
            # 确保元数据是字符串类型且非空
            metadata = {k: str(v) for k, v in metadata.items()}
            if not metadata:
                metadata = {"source": "default"}
            metadatas.append(metadata)
            
        # 如果没有提供预计算的嵌入向量，且有嵌入模型，则生成嵌入向量
        if embeddings is None and self.embedder is not None:
            embeddings = self.embedder.embed(contents)
            
        # 添加到集合
        self.collection.add(
            ids=ids,
            documents=contents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        return ids

    def add_texts(self, 
                  texts: List[str], 
                  metadatas: Optional[List[Dict[str, Any]]] = None,
                  ids: Optional[List[str]] = None) -> List[str]:
        """
        添加文本到数据库
        
        Args:
            texts: 文档列表
            metadatas: 元数据列表
            ids: ID列表
            
        Returns:
            添加的文档ID列表
        """
        if metadatas is None:
            metadatas = [{"source": "default"} for _ in texts]
            
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
            
        # 确保元数据是字符串类型
        metadatas = [{k: str(v) for k, v in metadata.items()} for metadata in metadatas]
        # 确保元数据非空
        for metadata in metadatas:
            if not metadata:
                metadata["source"] = "default"
            
        # 生成嵌入向量
        embeddings = None
        if self.embedder is not None:
            embeddings = self.embedder.embed(texts)
            
        # 添加到集合
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        return ids

    def add_files(self, 
                  file_paths: Union[str, List[str]], 
                  encoding: str = "utf-8",
                  splitter_config: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        添加文件到数据库
        
        Args:
            file_paths: 文件路径或文件路径列表
            encoding: 文件编码
            splitter_config: 临时的文本分割器配置参数
            
        Returns:
            添加的文档ID列表
        """
        # 如果提供了临时配置，使用临时分割器
        if splitter_config is not None:
            text_splitter = TextSplitter(**splitter_config)
        else:
            text_splitter = self.text_splitter
            
        # 确保file_paths是列表
        if isinstance(file_paths, str):
            file_paths = [file_paths]
            
        all_documents = []
        for file_path in file_paths:
            documents = text_splitter.split_file(file_path, encoding)
            all_documents.extend(documents)
            
        return self.add_documents(all_documents)

    def query(self, 
              query_text: Optional[str] = None,
              query_embeddings: Optional[List[List[float]]] = None,
              n_results: int = 5,
              where: Optional[Dict[str, Any]] = None,
              where_document: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        查询相似文档
        
        Args:
            query_text: 查询文本
            query_embeddings: 查询嵌入向量
            n_results: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件
            
        Returns:
            查询结果
        """
        # 如果提供了查询文本但没有提供查询嵌入向量，且有嵌入模型，则生成查询嵌入向量
        if query_text is not None and query_embeddings is None and self.embedder is not None:
            query_embeddings = self.embedder.embed(query_text)
        
        results = self.collection.query(
            query_texts=[query_text] if query_text and query_embeddings is None else None,
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            where_document=where_document
        )
        
        # 重新组织结果
        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                'id': results['ids'][0][i],
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i] if results['metadatas'][0][i] else {},
                'distance': results['distances'][0][i] if 'distances' in results and results['distances'][0][i] else None
            })
            
        return {
            'documents': formatted_results,
            'count': len(formatted_results)
        }

    def query_by_metadata(self, 
                          metadata_filter: Dict[str, Any],
                          n_results: int = 5) -> Dict[str, Any]:
        """
        基于元数据过滤的查询
        
        Args:
            metadata_filter: 元数据过滤条件
            n_results: 返回结果数量
            
        Returns:
            查询结果
        """
        return self.query(
            query_text="",  # 空查询文本
            n_results=n_results,
            where=metadata_filter
        )

    def delete(self, ids: Optional[List[str]] = None, where: Optional[Dict[str, Any]] = None):
        """
        删除文档
        
        Args:
            ids: 要删除的文档ID列表
            where: 元数据过滤条件
        """
        self.collection.delete(
            ids=ids,
            where=where
        )

    def update_document(self, 
                        doc_id: str, 
                        content: Optional[str] = None, 
                        metadata: Optional[Dict[str, Any]] = None):
        """
        更新文档
        
        Args:
            doc_id: 文档ID
            content: 新内容
            metadata: 新元数据
        """
        # 确保元数据是字符串类型
        if metadata:
            metadata = {k: str(v) for k, v in metadata.items()}
            
        # 生成嵌入向量
        embeddings = None
        if content is not None and self.embedder is not None:
            embeddings = self.embedder.embed(content)
            
        self.collection.update(
            ids=[doc_id],
            documents=[content] if content else None,
            metadatas=[metadata] if metadata else None,
            embeddings=[embeddings] if embeddings else None
        )

    def get_document_count(self) -> int:
        """
        获取文档总数
        
        Returns:
            文档总数
        """
        return self.collection.count()

    def get_collection_info(self) -> Dict[str, Any]:
        """
        获取集合信息
        
        Returns:
            集合信息
        """
        return {
            'name': self.name,
            'count': self.get_document_count()
        }

    def persist(self):
        """
        持久化数据（仅在使用PersistentClient时需要）
        """
        if hasattr(self.client, 'persist'):
            self.client.persist()

    def reset(self):
        """
        重置集合（删除所有数据）
        """
        # 获取所有文档的ID并删除它们
        result = self.collection.get()
        if result and result['ids']:
            self.collection.delete(ids=result['ids'])

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            文档内容，如果未找到返回None
        """
        try:
            result = self.collection.get(ids=[doc_id])
            if result['ids']:
                return {
                    'id': result['ids'][0],
                    'content': result['documents'][0],
                    'metadata': result['metadatas'][0] if result['metadatas'] else {}
                }
            return None
        except:
            return None

    def similarity_search_with_score(self, 
                                     query: str, 
                                     k: int = 5) -> List[tuple]:
        """
        相似性搜索并返回分数
        
        Args:
            query: 查询文本
            k: 返回结果数量
            
        Returns:
            (文档, 分数) 元组列表
        """
        result = self.query(query_text=query, n_results=k)
        docs_and_scores = []
        for doc in result['documents']:
            docs_and_scores.append((doc['content'], doc.get('distance', 0)))
        return docs_and_scores