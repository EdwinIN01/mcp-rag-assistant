"""文档管理接口：上传（任务队列异步摄入）/ 纯文本入库 / 列表（状态机）/ 删除 / 任务查询。

所有向量库写操作统一经 IngestionWorker 串行执行（含去重与状态机流转）。
"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from rag_engine.loader import DocumentLoader
from config import config
from ..dedup import sha256_bytes
from ..deps import get_dedup, get_engine, get_registry
from ..schemas import (
    DeleteResponse,
    DocumentInfo,
    DocumentListResponse,
    IngestResponse,
    IngestTextRequest,
    IngestTextResponse,
)
from ..worker import get_worker

router = APIRouter(prefix="/documents", tags=["documents"])


async def _sync_state() -> dict:
    """拉取向量库全量数据，同步注册表与去重索引（自愈旁路写入），返回 chroma 计数。"""
    vs, _, _, _ = get_engine()
    all_data = await asyncio.to_thread(vs.get_all)
    registry = get_registry()
    registry.sync_with_vectorstore(all_data)
    get_dedup().sync(all_data)
    counts: dict[str, int] = {}
    for meta in all_data.get("metadatas", []):
        if meta and meta.get("source"):
            counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return counts


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """列出知识库中所有文档及其状态（pending/parsing/available/duplicate/failed）。"""
    vs, _, _, _ = get_engine()
    counts = await _sync_state()
    docs = [
        DocumentInfo(**row) for row in get_registry().list_all()
    ]
    total = await asyncio.to_thread(vs.count)
    return DocumentListResponse(total_chunks=total, documents=docs)


@router.post("", response_model=IngestResponse, status_code=202)
async def upload_document(file: UploadFile):
    """上传文档入库（PDF/Markdown/docx/txt）。

    文件接收后立即返回 task_id，解析入库由后台工作线程串行执行
    （含文件级/片段级去重、同名替换更新、失败回滚），
    通过 GET /documents/tasks/{task_id} 轮询结果。
    """
    # 清洗文件名，防路径穿越
    filename = Path(file.filename or "upload.bin").name
    if Path(filename).suffix.lower() not in DocumentLoader.SUPPORTED:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型: {filename}，仅支持 {sorted(DocumentLoader.SUPPORTED)}",
        )

    content = await file.read()
    file_hash = sha256_bytes(content)
    dest = config.docs_dir / filename
    await asyncio.to_thread(dest.write_bytes, content)

    # 注册 pending 状态并提交到摄入队列
    get_registry().upsert(source=filename, file_hash=file_hash, status="pending")
    task_id = get_worker().submit(filename, filename, dest)
    return IngestResponse(
        task_id=task_id,
        filename=filename,
        source=filename,
        status="pending",
        detail="文件已接收，正在后台解析入库",
    )


@router.post("/text", response_model=IngestTextResponse)
async def ingest_text(req: IngestTextRequest):
    """纯文本直接入库（同步返回，经同一摄入队列串行执行，含去重与状态机）。"""
    vs, _, _, _ = get_engine()
    try:
        result = await asyncio.to_thread(
            get_worker().ingest_text_sync, req.text, req.source
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文本入库失败: {e}")
    total = await asyncio.to_thread(vs.count)
    return IngestTextResponse(
        source=req.source,
        status=result.status,
        new_chunks=result.new_chunks,
        dup_chunks=result.dup_chunks,
        total_chunks=total,
        detail=result.detail,
    )


@router.delete("/{source}", response_model=DeleteResponse)
async def delete_document(source: str):
    """按来源删除文档（向量库 + 注册表 + BM25 重建 + 去重索引同步）。"""
    counts = await _sync_state()
    registry = get_registry()
    row = registry.get(source)

    in_vectorstore = source in counts
    if not in_vectorstore and row is None:
        raise HTTPException(status_code=404, detail=f"来源不存在: {source}")

    vs, retriever, _, _ = get_engine()
    if in_vectorstore:
        await asyncio.to_thread(vs.delete_by_source, source)
        await asyncio.to_thread(retriever.refresh_bm25)
        get_dedup().sync(await asyncio.to_thread(vs.get_all))
        # 清空查询缓存，避免已删除内容从缓存泄漏
        retriever.cache.clear()
    registry.remove(source)

    removed = counts.get(source, row["chunks"] if row else 0)
    return DeleteResponse(deleted=True, detail=f"已删除来源 {source} 的 {removed} 个片段")


@router.get("/tasks/{task_id}", response_model=IngestResponse)
async def get_task(task_id: str):
    """查询摄入任务状态（pending / processing / available / duplicate / failed）。"""
    task = get_worker().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return IngestResponse(**task)
