"""检索结果缓存：基于 LRU + FAISS 相似查询命中。"""
import hashlib
import threading
from collections import OrderedDict
from typing import List, Optional

import numpy as np

from .embedder import Embedder


class QueryCache:
    """
    两级缓存：
    1. 精确匹配 LRU（query 文本哈希）
    2. 语义近似匹配（FAISS 索引，余弦相似度阈值）
    """

    def __init__(self, max_size: int = 256, similarity_threshold: float = 0.92):
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        self._exact: OrderedDict[str, List] = OrderedDict()
        self._vectors: List[np.ndarray] = []
        self._keys: List[str] = []
        self._lock = threading.Lock()
        self._faiss_index = None

    def get(self, query: str) -> Optional[List]:
        key = self._hash(query)
        with self._lock:
            # 精确命中
            if key in self._exact:
                self._exact.move_to_end(key)
                return self._exact[key]
            # 语义近似命中
            if self._vectors:
                hit = self._semantic_lookup(query)
                if hit is not None:
                    return hit
        return None

    def set(self, query: str, value: List) -> None:
        key = self._hash(query)
        with self._lock:
            self._exact[key] = value
            self._exact.move_to_end(key)
            if len(self._exact) > self.max_size:
                self._exact.popitem(last=False)
            # 维护语义索引
            vec = np.array(Embedder.embed_query(query), dtype=np.float32)
            vec = vec / (np.linalg.norm(vec) + 1e-8)
            self._vectors.append(vec)
            self._keys.append(key)
            self._rebuild_index()

    def _semantic_lookup(self, query: str) -> Optional[List]:
        if self._faiss_index is None or len(self._vectors) == 0:
            return None
        import faiss

        vec = np.array(Embedder.embed_query(query), dtype=np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        D, I = self._faiss_index.search(vec.reshape(1, -1), 1)
        if D[0][0] >= self.similarity_threshold:
            return self._exact.get(self._keys[I[0][0]])
        return None

    def _rebuild_index(self) -> None:
        if not self._vectors:
            return
        import faiss

        matrix = np.vstack(self._vectors).astype(np.float32)
        dim = matrix.shape[1]
        self._faiss_index = faiss.IndexFlatIP(dim)
        self._faiss_index.add(matrix)

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def stats(self) -> dict:
        return {"exact_size": len(self._exact), "semantic_size": len(self._vectors)}
