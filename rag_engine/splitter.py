"""文档切分：递归字符切分，保留语义连贯性。"""
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import config


class TextSplitter:
    """递归字符切分器，按中文/英文分隔符优先级切分。"""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or config.chunk_size
        self.chunk_overlap = chunk_overlap or config.chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""],
            length_function=len,
        )

    def split(self, documents: List[Document]) -> List[Document]:
        return self._splitter.split_documents(documents)

    def split_text(self, text: str) -> List[str]:
        return self._splitter.split_text(text)
