import re
import os
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path


class TextSplitter:
    """
    文本分割器类，用于将长文本分割成较小的块
    支持多种分割策略和文件格式
    """
    
    # 预定义的分割规则
    PREDEFINED_RULES = {
        "default": ["\n\n", "\n", ". ", "。", "! ", "? ", "！", "？", ";", "；", ",", "，"],
        "paragraph": ["\n\n"],
        "sentence": [".", "。", "!", "！", "?", "？", ";", "；"],
        "line": ["\n"],
        "markdown": ["\n\n", "\n# ", "\n## ", "\n### ", "\n#### ", "\n##### ", "\n###### "],
        "python": ["\n\n", "\nimport ", "\nclass ", "\ndef ", "\nif __name__"],
        "java": ["\n\n", "\nimport ", "\nclass ", "\npublic ", "\nprivate ", "\nprotected "],
        "javascript": ["\n\n", "\nimport ", "\nclass ", "\nfunction ", "\nconst ", "\nlet ", "\nvar "]
    }

    def __init__(self, 
                 chunk_size: int = 1000, 
                 chunk_overlap: int = 200,
                 separators: Optional[List[str]] = None,
                 predefined_rule: Optional[str] = None,
                 length_function: Callable[[str], int] = len,
                 keep_separator: bool = False):
        """
        初始化文本分割器
        
        Args:
            chunk_size: 每个文本块的最大长度
            chunk_overlap: 文本块之间的重叠长度
            separators: 分割符列表，按优先级排序
            predefined_rule: 预定义分割规则名称
            length_function: 长度计算函数
            keep_separator: 是否保留分割符
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.keep_separator = keep_separator
        
        # 处理分割符
        if separators is not None:
            self.separators = separators
        elif predefined_rule is not None:
            self.separators = self.PREDEFINED_RULES.get(predefined_rule, self.PREDEFINED_RULES["default"])
        else:
            self.separators = self.PREDEFINED_RULES["default"]

    def split_text(self, text: str) -> List[str]:
        """
        将文本分割成较小的块
        
        Args:
            text: 待分割的文本
            
        Returns:
            分割后的文本块列表
        """
        if self.length_function(text) <= self.chunk_size:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            # 确定当前块的结束位置
            end = min(start + self.chunk_size, len(text))
            
            # 如果不是最后一块，尝试在分隔符处分割
            if end < len(text):
                # 寻找合适的分割点
                split_pos = self._find_split_position(text, start, end)
                if split_pos != -1:
                    end = split_pos
            
            # 提取文本块
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # 移动起始位置（考虑重叠）
            if end >= len(text):  # 已经处理完所有文本
                break
            elif self.length_function(text[start:end]) <= self.chunk_size:
                # 正常情况下按重叠长度移动
                start = max(start + 1, end - self.chunk_overlap)
            else:
                # 特殊情况处理
                start = end - self.chunk_overlap
                if start <= 0:
                    start = end
                
        return chunks

    def _find_split_position(self, text: str, start: int, end: int) -> int:
        """
        在指定范围内寻找最佳分割位置
        
        Args:
            text: 原始文本
            start: 起始位置
            end: 结束位置
            
        Returns:
            最佳分割位置，如果未找到返回-1
        """
        # 从后向前查找分割符
        for separator in self.separators:
            # 在当前块中查找分割符
            if self.keep_separator:
                split_pos = text.rfind(separator, start, end)
                if split_pos != -1:
                    return split_pos + len(separator)
            else:
                split_pos = text.rfind(separator, start, end)
                if split_pos != -1:
                    return split_pos + len(separator)
                
        return -1

    def _find_new_start_position(self, text: str, start: int, end: int) -> int:
        """
        计算下一个文本块的起始位置
        
        Args:
            text: 原始文本
            start: 当前块起始位置
            end: 当前块结束位置
            
        Returns:
            下一个块的起始位置
        """
        # 默认按重叠长度计算
        new_start = end - self.chunk_overlap
        
        # 确保不会回退到当前位置之前
        if new_start <= start:
            new_start = end
            
        return new_start

    def split_document(self, 
                       content: str, 
                       metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        分割文档并保留元数据
        
        Args:
            content: 文档内容
            metadata: 文档元数据
            
        Returns:
            包含文本块和元数据的字典列表
        """
        if metadata is None:
            metadata = {}
            
        chunks = self.split_text(content)
        documents = []
        
        for i, chunk in enumerate(chunks):
            doc = {
                "content": chunk,
                "metadata": {
                    **metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            }
            documents.append(doc)
            
        return documents

    def split_documents(self, 
                        documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量分割文档
        
        Args:
            documents: 文档列表，每个文档包含content和metadata字段
            
        Returns:
            分割后的文档列表
        """
        split_docs = []
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            split_docs.extend(self.split_document(content, metadata))
            
        return split_docs

    def split_file(self, file_path: str, encoding: str = "utf-8") -> List[Dict[str, Any]]:
        """
        分割文件内容
        
        Args:
            file_path: 文件路径
            encoding: 文件编码
            
        Returns:
            分割后的文档列表
        """
        # 确保file_path是Path对象
        file_path = Path(file_path)
        
        # 检查文件是否存在
        if not file_path.exists():
            raise FileNotFoundError(f"文件 {file_path} 不存在")
            
        file_extension = file_path.suffix.lower()
        
        try:
            if file_extension == ".pdf":
                content = self._read_pdf_file(file_path)
            elif file_extension in [".docx", ".doc"]:
                content = self._read_docx_file(file_path)
            elif file_extension == ".txt":
                content = self._read_text_file(file_path, encoding)
            elif file_extension in [".md", ".markdown"]:
                content = self._read_markdown_file(file_path, encoding)
            elif file_extension == ".json":
                content = self._read_json_file(file_path, encoding)
            else:
                # 默认按文本文件处理
                content = self._read_text_file(file_path, encoding)
                
            # 从文件路径提取元数据
            metadata = {
                "source": str(file_path),
                "file_type": file_extension[1:] if file_extension else "unknown"
            }
            
            return self.split_document(content, metadata)
        except Exception as e:
            raise Exception(f"读取文件 {file_path} 时出错: {str(e)}")

    def _read_text_file(self, file_path: Path, encoding: str) -> str:
        """读取文本文件"""
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()

    def _read_pdf_file(self, file_path: Path) -> str:
        """读取PDF文件"""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except ImportError:
            raise ImportError("需要安装PyPDF2库来处理PDF文件: pip install PyPDF2")

    def _read_docx_file(self, file_path: Path) -> str:
        """读取DOCX文件"""
        try:
            from docx import Document
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except ImportError:
            raise ImportError("需要安装python-docx库来处理DOCX文件: pip install python-docx")

    def _read_markdown_file(self, file_path: Path, encoding: str) -> str:
        """读取Markdown文件"""
        return self._read_text_file(file_path, encoding)

    def _read_json_file(self, file_path: Path, encoding: str) -> str:
        """读取JSON文件并转换为文本"""
        import json
        with open(file_path, "r", encoding=encoding) as f:
            data = json.load(f)
            return json.dumps(data, ensure_ascii=False, indent=2)

    def split_by_tokens(self, text: str, tokenizer: Any = None) -> List[str]:
        """
        基于token的分割方式（适用于大模型token限制）
        
        Args:
            text: 待分割文本
            tokenizer: 分词器，如果为None则使用简单分割
            
        Returns:
            分割后的文本块列表
        """
        if tokenizer is None:
            # 简单的基于空格和标点的分割
            tokens = re.findall(r'\S+|\s+', text)
        else:
            # 使用实际的分词器
            tokens = tokenizer.encode(text)
            
        chunks = []
        current_chunk = []
        current_length = 0
        
        for token in tokens:
            token_length = self.length_function(token)
            if current_length + token_length > self.chunk_size and current_chunk:
                # 创建当前块
                chunk_text = "".join(current_chunk)
                chunks.append(chunk_text.strip())
                
                # 根据重叠大小保留部分token
                if self.chunk_overlap > 0:
                    # 计算需要保留的token数量
                    overlap_tokens = []
                    overlap_length = 0
                    for t in reversed(current_chunk):
                        t_length = self.length_function(t)
                        if overlap_length + t_length <= self.chunk_overlap:
                            overlap_tokens.insert(0, t)
                            overlap_length += t_length
                        else:
                            break
                    current_chunk = overlap_tokens
                    current_length = overlap_length
                else:
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(token)
            current_length += token_length
            
        # 添加最后一个块
        if current_chunk:
            chunk_text = "".join(current_chunk)
            chunks.append(chunk_text.strip())
            
        return chunks

    def split_by_paragraphs(self, text: str) -> List[str]:
        """
        按段落分割文本
        
        Args:
            text: 待分割文本
            
        Returns:
            分割后的文本块列表
        """
        # 按双换行符分割段落
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # 检查添加段落后是否会超出块大小
            test_chunk = (current_chunk + "\n\n" + paragraph) if current_chunk else paragraph
            if self.length_function(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                # 如果当前块不为空，先保存
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    
                # 如果段落本身就很长大于块大小，需要进一步分割
                if self.length_function(paragraph) > self.chunk_size:
                    # 使用常规分割方法处理大段落
                    sub_chunks = self.split_text(paragraph)
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = paragraph
                    
        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    def split_by_semantic(self, text: str, sentence_transformer: Any = None) -> List[str]:
        """
        基于语义的分割方式（需要sentence transformers库）
        
        Args:
            text: 待分割文本
            sentence_transformer: 句子转换器模型
            
        Returns:
            分割后的文本块列表
        """
        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            raise ImportError("需要安装numpy和scikit-learn库: pip install numpy scikit-learn")
            
        if sentence_transformer is None:
            # 如果没有提供转换器，回退到按句子分割
            sentences = re.split(r'[.!?。！？]', text)
            sentences = [s.strip() for s in sentences if s.strip()]
        else:
            # 按句子分割
            sentences = re.split(r'[.!?。！？]', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            
            # 获取句子嵌入
            embeddings = sentence_transformer.encode(sentences)
            
            # 计算相邻句子间的相似度
            similarities = []
            for i in range(len(embeddings) - 1):
                sim = cosine_similarity([embeddings[i]], [embeddings[i+1]])[0][0]
                similarities.append(sim)
            
            # 根据相似度决定分割点
            # 这里简化处理，实际可以更复杂
            
        # 根据句子长度分组
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            test_chunk = (current_chunk + " " + sentence) if current_chunk else sentence
            if self.length_function(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
                
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    def custom_split(self, text: str, split_function: Callable[[str], List[str]]) -> List[str]:
        """
        使用自定义分割函数
        
        Args:
            text: 待分割文本
            split_function: 自定义分割函数
            
        Returns:
            分割后的文本块列表
        """
        initial_splits = split_function(text)
        chunks = []
        
        for split in initial_splits:
            if self.length_function(split) <= self.chunk_size:
                chunks.append(split)
            else:
                # 如果分割后的部分仍然太大，继续使用基本分割方法
                sub_chunks = self.split_text(split)
                chunks.extend(sub_chunks)
                
        return chunks
        
    @classmethod
    def get_available_rules(cls) -> List[str]:
        """
        获取所有可用的预定义规则
        
        Returns:
            可用规则名称列表
        """
        return list(cls.PREDEFINED_RULES.keys())