"""向量化：支持本地 BGE 模型或 API Embedding，单例懒加载。"""
import os
import threading
from typing import List

# 离线模式：避免请求 HuggingFace 官网
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# 禁用 transformers 的 safetensors 自动转换后台线程
# （该线程会联网调用 HfApi.model_info，离线时打印大量超时报错，但不影响功能）
# 需 patch modeling_utils 中导入的 auto_conversion 引用（线程 target 绑定的是这个名字）
try:
    import transformers.modeling_utils as _mu
    _mu.auto_conversion = lambda *a, **k: (None, k.get("revision", "main"), False)
except Exception:
    pass
try:
    import transformers.safetensors_conversion as _sc
    _sc.auto_conversion = lambda *a, **k: (None, k.get("revision", "main"), False)
except Exception:
    pass

from langchain_core.embeddings import Embeddings

from config import config


class Embedder:
    """Embedding 单例工厂，避免重复加载模型。"""

    _instance: Embeddings = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> Embeddings:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._build()
        return cls._instance

    @classmethod
    def _build(cls) -> Embeddings:
        if config.use_local_embedding:
            from langchain_huggingface import HuggingFaceEmbeddings
            print(f"[Embedder] 加载本地 Embedding 模型: {config.local_embedding_model}")
            return HuggingFaceEmbeddings(
                model_name=config.local_embedding_model,
                encode_kwargs={"normalize_embeddings": True},
                model_kwargs={"local_files_only": config.hf_hub_offline},
            )
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            base_url=config.embedding_api_base,
            api_key=config.embedding_api_key,
            model=config.embedding_model,
        )

    @classmethod
    def embed_query(cls, text: str) -> List[float]:
        return cls.get().embed_query(text)

    @classmethod
    def embed_documents(cls, texts: List[str]) -> List[List[float]]:
        return cls.get().embed_documents(texts)
