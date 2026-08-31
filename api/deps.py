"""依赖注入：RAG 引擎 / 注册表 / 去重索引单例（懒加载 + 双检锁，进程内共享）。

不直接 import 时初始化，避免拉起服务就加载模型；
首次访问（含 lifespan 预热）才构建引擎。
"""
import threading

from config import config
from rag_engine.loader import DocumentLoader
from rag_engine.retriever import HybridRetriever
from rag_engine.splitter import TextSplitter
from rag_engine.vectorstore import VectorStore

from .dedup import DedupIndex
from .registry import DocumentRegistry

_lock = threading.Lock()
_vectorstore: VectorStore | None = None
_retriever: HybridRetriever | None = None
_loader: DocumentLoader | None = None
_splitter: TextSplitter | None = None
_registry: DocumentRegistry | None = None
_dedup: DedupIndex | None = None


def _init() -> None:
    global _vectorstore, _retriever, _loader, _splitter
    if _retriever is not None:
        return
    with _lock:
        if _retriever is None:
            _vectorstore = VectorStore()
            _retriever = HybridRetriever(_vectorstore)
            _loader = DocumentLoader()
            _splitter = TextSplitter()


def get_engine() -> tuple[VectorStore, HybridRetriever, DocumentLoader, TextSplitter]:
    _init()
    return _vectorstore, _retriever, _loader, _splitter


def get_vectorstore() -> VectorStore:
    _init()
    return _vectorstore


def get_retriever() -> HybridRetriever:
    _init()
    return _retriever


def get_loader() -> DocumentLoader:
    _init()
    return _loader


def get_splitter() -> TextSplitter:
    _init()
    return _splitter


def get_registry() -> DocumentRegistry:
    """文档注册表单例（SQLite 状态机）。"""
    global _registry
    if _registry is None:
        with _lock:
            if _registry is None:
                _registry = DocumentRegistry(config.registry_db_path)
    return _registry


def get_dedup() -> DedupIndex:
    """去重索引单例（内存 hash 映射，写操作后需 sync）。"""
    global _dedup
    if _dedup is None:
        with _lock:
            if _dedup is None:
                _dedup = DedupIndex()
    return _dedup
