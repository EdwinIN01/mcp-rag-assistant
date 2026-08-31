"""可观测性：structlog 结构化日志 + 请求 ID 中间件 + Langfuse 追踪。

三个能力，均支持无配置降级：
1. 结构化日志：LOG_FORMAT=console（开发，带颜色）/ json（生产，一行一条）
2. 请求 ID：每个 HTTP 请求生成/透传 X-Request-ID，自动注入所有日志行
3. Langfuse 追踪：配置 LANGFUSE_PUBLIC_KEY/SECRET_KEY 后，
   检索（retriever）/ 生成（generation）/ 摄入（span）全链路 trace；
   未配置时所有 start_observation 返回 no-op，零开销降级。
"""
import logging
import sys
import threading
import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from config import config

# ---------- 结构化日志 ----------


def setup_logging() -> None:
    """初始化 structlog + 标准库 logging（进程内调用一次）。"""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")

    shared_processors = [
        structlog.contextvars.merge_contextvars,  # 自动合并 request_id 等上下文
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if config.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "mcp-rag") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# ---------- 请求 ID 中间件 ----------


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成（或透传）X-Request-ID，绑定到日志上下文并回写响应头。"""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            get_logger("api").error(
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            raise

        # 注意：日志必须在 clear_contextvars 之前打（否则 request_id 丢失）；
        # 认证身份由 get_current_user 写入 request.state（子任务 contextvars 父任务不可见）
        response.headers["X-Request-ID"] = rid
        user = getattr(request.state, "user", None)
        get_logger("api").info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            **({"user": user.username} if user else {}),
        )
        structlog.contextvars.clear_contextvars()
        return response


# ---------- Langfuse 追踪 ----------


class _NoopObservation:
    """Langfuse 未启用时的 no-op observation，接口与真实 span 对齐。"""

    def update(self, **kwargs) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Tracer:
    """Langfuse 客户端单例：懒加载 + 线程安全 + 无 keys 自动降级（仅初始化一次）。"""

    def __init__(self):
        self._client = None
        self._initialized = False
        self._lock = threading.Lock()
        self.enabled = False

    def client(self):
        if self._initialized:
            return self._client
        with self._lock:
            if not self._initialized:
                self._client = self._build()
                self._initialized = True
        return self._client

    def _build(self):
        if not (config.langfuse_public_key and config.langfuse_secret_key):
            get_logger("observability").info(
                "langfuse_disabled", reason="LANGFUSE_PUBLIC_KEY/SECRET_KEY 未配置"
            )
            return None
        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=config.langfuse_public_key,
                secret_key=config.langfuse_secret_key,
                host=config.langfuse_host,
            )
            client.auth_check()  # 启动即校验凭证，失败直接降级
            self.enabled = True
            get_logger("observability").info("langfuse_enabled", host=config.langfuse_host)
            return client
        except Exception as e:
            get_logger("observability").warning(
                "langfuse_init_failed", error=str(e), fallback="no-op"
            )
            return None

    def flush(self) -> None:
        """进程退出前冲刷缓冲区，确保 trace 不丢。"""
        if self.enabled and self._client is not None:
            try:
                self._client.flush()
            except Exception:
                pass


_tracer = Tracer()


def get_tracer() -> Tracer:
    return _tracer


def start_observation(name: str, as_type: str = "span", **kwargs):
    """开启一个 Langfuse observation（上下文管理器）。

    as_type: span / generation / retriever / tool / chain ...
    未配置 keys 时返回 no-op，调用方无感知。
    嵌套调用自动形成父子层级（首个 observation 即 trace 根）。
    """
    client = _tracer.client()
    if client is None:
        return _NoopObservation()
    try:
        return client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
    except Exception:
        return _NoopObservation()


def get_trace_url() -> str | None:
    """当前 trace 在 Langfuse 控制台的链接（供响应返回，便于跳转排查）。"""
    if not _tracer.enabled or _tracer._client is None:
        return None
    try:
        return _tracer._client.get_trace_url()
    except Exception:
        return None
