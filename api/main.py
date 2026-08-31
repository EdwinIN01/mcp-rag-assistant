"""FastAPI 服务入口：把 RAG 引擎封装为 REST API。

启动：
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    或
    python -m api.main

接口文档（Swagger）：http://127.0.0.1:8000/docs

可观测性（阶段 3）：
- structlog 结构化日志（LOG_FORMAT=console/json），请求 ID 贯穿全链路
- Langfuse 追踪（配置 LANGFUSE_* 后自动启用，未配置零开销降级）
"""
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import get_current_user
from api.observability import RequestIdMiddleware, get_logger, get_tracer, setup_logging
from api.routers import auth, chat, documents, search
from config import config

setup_logging()
logger = get_logger("api")


def _preload_models() -> None:
    """预热模型：Embedding / BM25 / Reranker（由 lifespan 在线程池中调用）。"""
    from rag_engine.embedder import Embedder

    from api.deps import get_retriever

    retriever = get_retriever()
    Embedder.get()
    retriever._ensure_bm25()
    if config.reranker_model:
        retriever.warmup_reranker()


def _sync_state() -> None:
    """启动时同步注册表与去重索引（迁移历史入库文档 / MCP 等旁路写入）。"""
    from api.deps import get_dedup, get_engine, get_registry

    vs, _, _, _ = get_engine()
    all_data = vs.get_all()
    synced = get_registry().sync_with_vectorstore(all_data)
    get_dedup().sync(all_data)
    logger.info("registry_synced", updated_records=synced)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.worker import get_worker

    worker = get_worker()
    worker.start()
    # 提前初始化 Langfuse（无 keys 时打印一条降级日志后保持 no-op）
    get_tracer().client()
    if config.api_preload_models:
        logger.info("preloading_models", est_seconds=15)
        await asyncio.to_thread(_preload_models)
        await asyncio.to_thread(_sync_state)
        logger.info("service_ready")
    else:
        logger.info("preload_disabled")
    yield
    worker.stop()
    get_tracer().flush()
    logger.info("service_stopped")


app = FastAPI(
    title="MCP-RAG API",
    description="RAG 知识库服务：混合检索 / 多轮对话 / 文档管理",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：当前放开（本地开发/前端联调），阶段 5 引入鉴权时收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求 ID：生成/透传 X-Request-ID，注入日志上下文并回写响应头
app.add_middleware(RequestIdMiddleware)

app.include_router(auth.router, prefix="/api/v1")

# 业务接口统一要求认证（JWT / API Key 双通道；AUTH_ENABLED=false 时自动放行）
# /api/v1/auth/* 自身在路由内控制（注册、登录公开，me 与 API Key 管理需认证）
if config.auth_enabled:
    logger.info("auth_enabled", scheme="jwt+api_key")
    app.include_router(
        search.router, prefix="/api/v1", dependencies=[Depends(get_current_user)]
    )
    app.include_router(
        chat.router, prefix="/api/v1", dependencies=[Depends(get_current_user)]
    )
    app.include_router(
        documents.router, prefix="/api/v1", dependencies=[Depends(get_current_user)]
    )
else:
    logger.warning("auth_disabled", hint="AUTH_ENABLED=false，所有接口免认证（仅限本地开发）")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    """健康检查。"""
    return {
        "status": "ok",
        "version": app.version,
        "llm_configured": bool(config.llm_api_key),
        "reranker_enabled": bool(config.reranker_model),
        "tracing_enabled": get_tracer().enabled,
        "auth_enabled": config.auth_enabled,
    }


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "MCP-RAG API",
        "docs": "/docs",
        "endpoints": [
            "POST /api/v1/search",
            "POST /api/v1/search/details",
            "GET  /api/v1/search/cache/stats",
            "POST /api/v1/chat",
            "POST /api/v1/chat/stream",
            "GET  /api/v1/documents",
            "POST /api/v1/documents",
            "POST /api/v1/documents/text",
            "DELETE /api/v1/documents/{source}",
            "GET  /api/v1/documents/tasks/{task_id}",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host=config.api_host, port=config.api_port)
