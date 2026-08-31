"""全局配置：从环境变量读取，提供统一访问入口。"""
import json
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

    # 文档注册表（SQLite，记录文档状态机）
    registry_db_path: Path = BASE_DIR / os.getenv("REGISTRY_DB_PATH", "./data/registry.db").lstrip("./")

    # 鉴权（阶段 5）：AUTH_ENABLED=false 时所有接口免认证（本地开发模式）
    auth_enabled: bool = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    auth_db_path: Path = BASE_DIR / os.getenv("AUTH_DB_PATH", "./data/auth.db").lstrip("./")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    api_key_prefix: str = "sk-mcprag-"

    # 文档
    docs_dir: Path = BASE_DIR / os.getenv("DOCS_DIR", "./data/docs").lstrip("./")

    # 检索参数
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    rerank_top_k: int = 3

    # API 服务
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_preload_models: bool = os.getenv("API_PRELOAD_MODELS", "true").lower() == "true"

    # 可观测性：结构化日志（console / json）与 Langfuse 追踪（不配置 keys 自动降级关闭）
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "console")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # 评估（RAGAS）质量门禁阈值：任一指标低于阈值 CI 失败
    # JSON 格式，键为指标名，值为下限；rejection_rate 为负样本拒绝率下限
    # 当前默认值基于 25 题测试集实测水位校准，可按业务要求收紧
    eval_thresholds: dict = json.loads(
        os.getenv(
            "EVAL_THRESHOLDS",
            '{"faithfulness": 0.60, "answer_relevancy": 0.65, '
            '"context_precision": 0.60, "context_recall": 0.60, "rejection_rate": 0.80}',
        )
    )


config = Config()

# 设置 HuggingFace 离线模式（如果配置），避免联网请求 HuggingFace
if config.hf_hub_offline:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# 确保目录存在
config.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
config.registry_db_path.parent.mkdir(parents=True, exist_ok=True)
config.auth_db_path.parent.mkdir(parents=True, exist_ok=True)
config.docs_dir.mkdir(parents=True, exist_ok=True)