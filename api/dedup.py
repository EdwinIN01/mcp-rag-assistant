"""入库去重索引：文件级 + 片段级双重去重。

以 Chroma 中的 chunk 元数据为唯一事实源：
- file_hash：整份文件（或文本）内容的 SHA256，同一来源的所有 chunk 共享
- chunk_hash：单个片段文本的 SHA256，入库时写入元数据持久化

索引在内存中维护 hash → 来源集合 的映射，任何写操作后调用 sync() 重建。
历史入库的 chunk（无 chunk_hash 元数据）在 sync 时按内容现场计算补齐，同样参与去重。
"""
import hashlib
import threading
from typing import List, Optional, Tuple

from langchain_core.documents import Document


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DedupIndex:
    """线程安全的去重索引，需在写入方调用 sync() 保持与向量库一致。"""

    def __init__(self):
        self._chunk_hashes: dict[str, set[str]] = {}  # chunk_hash → 来源集合
        self._file_hashes: dict[str, set[str]] = {}   # file_hash → 来源集合
        self._lock = threading.Lock()
        self._loaded = False

    @property
    def ready(self) -> bool:
        """是否已完成至少一次 sync（未加载前去重判断不可靠）。"""
        return self._loaded

    def sync(self, all_data: dict) -> None:
        """从 vectorstore.get_all() 的结果重建索引。"""
        chunk_map: dict[str, set[str]] = {}
        file_map: dict[str, set[str]] = {}
        for text, meta in zip(all_data.get("documents", []), all_data.get("metadatas", [])):
            meta = meta or {}
            source = meta.get("source", "未知")
            chunk_hash = meta.get("chunk_hash") or (sha256_text(text) if text else None)
            if chunk_hash:
                chunk_map.setdefault(chunk_hash, set()).add(source)
            file_hash = meta.get("file_hash")
            if file_hash:
                file_map.setdefault(file_hash, set()).add(source)
        with self._lock:
            self._chunk_hashes = chunk_map
            self._file_hashes = file_map
            self._loaded = True

    def is_known_file(self, file_hash: str) -> bool:
        """文件级去重：同内容（字节级一致）是否已存在于任意来源。"""
        with self._lock:
            return file_hash in self._file_hashes

    def filter_new_chunks(self, chunks: List[Document]) -> Tuple[List[Document], int]:
        """片段级去重：过滤已存在的片段，返回 (新片段列表, 重复数)。

        就地为每个片段写入 chunk_hash 元数据（新片段入库后随元数据持久化）；
        同一文件内部重复的片段同样只保留一份。
        """
        new_chunks: List[Document] = []
        dup_count = 0
        with self._lock:
            seen_local: set[str] = set()
            for c in chunks:
                chunk_hash = sha256_text(c.page_content)
                c.metadata["chunk_hash"] = chunk_hash
                if chunk_hash in self._chunk_hashes or chunk_hash in seen_local:
                    dup_count += 1
                    continue
                seen_local.add(chunk_hash)
                new_chunks.append(c)
        return new_chunks, dup_count

    def stats(self) -> dict:
        with self._lock:
            return {
                "known_file_hashes": len(self._file_hashes),
                "known_chunk_hashes": len(self._chunk_hashes),
                "loaded": self._loaded,
            }
