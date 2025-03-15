"""
编写者：王出日
日期：2024，12，1
版本？
使用通义大模型的词嵌入模型对中文文本进行编码
包含：
TextEmbedding类：用于对中文文本进行编码
"""
import dashscope
from http import HTTPStatus
from typing import Union


dashscope.api_key= "sk-aa328698ca6f4a7c9c0dde0b9851a772"
class TextEmbedding:
    def __init__(self,model_version = "v1"):
        """
        初始化通义大模型的词嵌入模型
        :param model_version: 模型版本，默认为v1
        """
        # self.cache = getCache()
        if model_version == "v1":
            self.model = dashscope.TextEmbedding.Models.text_embedding_v1
        elif model_version == "v2":
            self.model = dashscope.TextEmbedding.Models.text_embedding_v2
        elif model_version == "v3":
            self.model = dashscope.TextEmbedding.Models.text_embedding_v3
        else:
            raise ValueError("不存在该版本")
        
    def embedding(self, text: Union[str, list]):
        """
        对中文文本进行编码
        Args:
            text: 输入的中文文本
        Returns:
            文本的嵌入向量
        """
        return self.strOrList(text)

    def strOrList(self, text):
        if isinstance(text, list):
            return [self.textembedding(t).output["embeddings"][0]['embedding'] for t in text]
        else:
            return self.textembedding(text).output["embeddings"][0]['embedding']

    def textembedding(self, text):
        resp = dashscope.TextEmbedding.call(
            model=self.model,
            input=text
        )
        if resp.status_code == HTTPStatus.OK:
            return resp
        else:
            print(resp)
            raise ValueError("调用API失败")