"""全局配置：从环境变量读取，提供统一访问入口。"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # LLM
    llm_api_base: str = os.getenv("LLM_API_BASE", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")

    # Embedding
    use_local_embedding: bool = os.getenv("USE_LOCAL_EMBEDDING", "true").lower() == "true"
    local_embedding_model: str = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-base-zh-v1.5")
    embedding_api_base: str = os.getenv("EMBEDDING_API_BASE", "")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

    # HuggingFace 离线模式
    hf_hub_offline: bool = os.getenv("HF_HUB_OFFLINE", "0").lower() in ("1", "true", "yes")

    # 重排模型（空字符串表示禁用重排）
    reranker_model: str = os.getenv("RERANKER_MODEL", "")

    # 向量库
    chroma_persist_dir: Path = BASE_DIR / os.getenv("CHROMA_PERSIST_DIR", "./data/chroma").lstrip("./")

    # 文档
    docs_dir: Path = BASE_DIR / os.getenv("DOCS_DIR", "./data/docs").lstrip("./")

    # 检索参数
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    rerank_top_k: int = 3


config = Config()

# 设置 HuggingFace 离线模式（如果配置），避免联网请求 HuggingFace
if config.hf_hub_offline:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# 确保目录存在
config.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
config.docs_dir.mkdir(parents=True, exist_ok=True)
