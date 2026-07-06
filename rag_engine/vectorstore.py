"""向量库：基于 Chroma 持久化存储。"""
from typing import List, Dict, Any

from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

from config import config
from .embedder import Embedder


class VectorStore:
    """Chroma 向量库封装，支持增删查。"""

    def __init__(self, collection_name: str = "default"):
        self.collection_name = collection_name
        self._store: Chroma | None = None

    @property
    def store(self) -> Chroma:
        if self._store is None:
            self._store = Chroma(
                collection_name=self.collection_name,
                embedding_function=Embedder.get(),
                persist_directory=str(config.chroma_persist_dir),
            )
        return self._store

    def add_documents(self, documents: List[Document]) -> List[str]:
        return self.store.add_documents(documents)

    def similarity_search(self, query: str, k: int = None) -> List[Document]:
        return self.store.similarity_search(query, k=k or config.top_k)

    def similarity_search_with_score(
        self, query: str, k: int = None
    ) -> List[tuple[Document, float]]:
        return self.store.similarity_search_with_score(query, k=k or config.top_k)

    def get_all(self) -> Dict[str, Any]:
        return self.store.get()

    def delete_by_source(self, source: str) -> None:
        """按来源文件名删除所有相关文档。"""
        all_data = self.store.get()
        ids_to_delete = [
            _id
            for _id, meta in zip(all_data.get("ids", []), all_data.get("metadatas", []))
            if meta and meta.get("source") == source
        ]
        if ids_to_delete:
            self.store.delete(ids=ids_to_delete)

    def count(self) -> int:
        return self.store._collection.count()
