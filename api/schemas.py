"""API 请求 / 响应模型（Pydantic）。"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- 通用 ----------
class RetrievedChunk(BaseModel):
    """检索到的文档片段。"""
    content: str
    source: str = "未知"
    score: Optional[float] = Field(None, description="相关性得分（各阶段量纲不同，仅作排序参考）")


# ---------- 检索 ----------
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="返回片段数，默认取配置 rerank_top_k")


class SearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    latency_ms: float


class SearchDetailsResponse(SearchResponse):
    """四阶段检索过程详情（向量 / BM25 / RRF 融合 / 重排）。"""
    vector_results: list[RetrievedChunk]
    bm25_results: list[RetrievedChunk]
    fused_results: list[RetrievedChunk]


# ---------- 对话 ----------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户问题")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="历史对话（时间升序），超过 3 轮自动摘要压缩",
    )
    top_k: Optional[int] = Field(None, ge=1, le=10, description="检索片段数")


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    latency_ms: float


# ---------- 文档 ----------
class DocumentInfo(BaseModel):
    """注册表中的文档记录（状态机）。"""
    source: str
    status: str = Field(description="pending / parsing / available / duplicate / failed")
    chunks: int = 0
    file_hash: Optional[str] = None
    error: str = ""
    detail: str = ""
    updated_at: str = ""


class DocumentListResponse(BaseModel):
    total_chunks: int
    documents: list[DocumentInfo]


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="纯文本内容")
    source: str = Field("api_text.txt", description="来源标识（用于后续删除和引用展示）")


class IngestTextResponse(BaseModel):
    source: str
    status: str = Field(description="available / duplicate")
    new_chunks: int
    dup_chunks: int = 0
    total_chunks: int
    detail: str = ""


class IngestResponse(BaseModel):
    task_id: str
    filename: str
    source: str
    status: str = Field(
        description="pending / processing / available / duplicate / failed"
    )
    detail: str = ""


class DeleteResponse(BaseModel):
    deleted: bool
    detail: str
