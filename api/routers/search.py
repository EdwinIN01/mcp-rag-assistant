"""检索接口：混合检索 / 四阶段过程详情 / 缓存统计。"""
from fastapi import APIRouter

from .. import services
from ..deps import get_retriever
from ..schemas import (
    RetrievedChunk,
    SearchDetailsResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/search", tags=["search"])


def _chunk(doc, score=None) -> RetrievedChunk:
    """LangChain Document 转 API 响应模型。"""
    return RetrievedChunk(
        content=doc.page_content,
        source=doc.metadata.get("source", "未知"),
        score=score,
    )


@router.post("", response_model=SearchResponse)
async def search(req: SearchRequest):
    """混合检索（向量 + BM25 + RRF 融合 + 重排，带两级缓存）。"""
    docs, latency = await services.search(req.query, req.top_k)
    return SearchResponse(
        query=req.query,
        results=[_chunk(d) for d in docs],
        latency_ms=round(latency, 1),
    )


@router.post("/details", response_model=SearchDetailsResponse)
async def search_details(req: SearchRequest):
    """检索并返回四阶段过程详情（向量 / BM25 / RRF / 重排），供可视化前端展示。"""
    details, latency = await services.search_with_details(req.query)
    return SearchDetailsResponse(
        query=req.query,
        vector_results=[_chunk(d, s) for d, s in details["vector_results"]],
        bm25_results=[_chunk(d, s) for d, s in details["bm25_results"]],
        fused_results=[_chunk(d, s) for d, s in details["fused_results"]],
        results=[_chunk(d) for d in details["reranked"]],
        latency_ms=round(latency, 1),
    )


@router.get("/cache/stats")
async def cache_stats():
    """查询两级缓存状态（LRU 精确 + FAISS 语义）。"""
    stats = get_retriever().cache.stats()
    return {
        "exact_cache_size": stats["exact_size"],
        "semantic_index_size": stats["semantic_size"],
    }
