"""摄入工作线程：任务队列 + 串行处理管线 + 状态机驱动。

为什么单工作线程而非 Celery：
- 当前为单进程部署，Chroma 写入与 BM25 重建没有并发保护，串行摄入更安全；
- 对外保持任务队列语义（submit / get_task），阶段 6 容器化时可平滑替换为 Celery。

处理管线（每份文档的状态流转）：
    pending → parsing → 文件级去重检查
        ├─ 内容已存在 → duplicate
        ├─ 同名不同内容 → 删除旧片段后入库（增量更新/替换）
        └─ 解析 → 切分 → 片段级去重 → 入库 → available
    任何一步异常 → 回滚向量库写入 → failed
"""
import queue
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

from .dedup import DedupIndex, sha256_bytes, sha256_text
from .deps import get_dedup, get_engine, get_registry
from .observability import get_logger, start_observation

log = get_logger("ingest")


@dataclass
class IngestResult:
    status: str      # available / duplicate
    new_chunks: int
    dup_chunks: int
    detail: str


class IngestionWorker:
    """后台摄入工作线程。所有向量库写操作（文件/文本摄入）统一经此串行执行。"""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = False
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(
            target=self._run, name="ingest-worker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._queue.put(None)  # 唤醒阻塞的 get()

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None or self._stop:
                break
            try:
                job()
            except Exception:
                pass  # 任务内部已处理状态与回滚
            finally:
                self._queue.task_done()

    # ---------- 任务记录 ----------
    def _update_task(self, task_id: str, status: str, detail: str = "") -> None:
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = status
                self._tasks[task_id]["detail"] = detail

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    # ---------- 对外入口 ----------
    def submit(self, source: str, filename: str, file_path: Path) -> str:
        """提交文件摄入任务（异步），返回 task_id 供轮询。"""
        self.start()
        task_id = uuid.uuid4().hex[:12]
        with self._tasks_lock:
            # 防止无限增长：超限时丢弃最旧任务
            while len(self._tasks) >= 1000:
                self._tasks.pop(next(iter(self._tasks)))
            self._tasks[task_id] = {
                "task_id": task_id,
                "source": source,
                "filename": filename,
                "status": "pending",
                "detail": "排队中",
            }

        def job():
            self._update_task(task_id, "processing", "解析中")
            try:
                result = self._ingest_with_registry(source, path=file_path)
                self._update_task(task_id, result.status, result.detail)
            except Exception as e:
                self._update_task(task_id, "failed", f"入库失败: {e}")

        self._queue.put(job)
        return task_id

    def ingest_text_sync(self, text: str, source: str, timeout: float = 300) -> IngestResult:
        """文本摄入（同步等待结果）。与文件任务共用同一队列，保证写操作串行。"""
        self.start()
        done = threading.Event()
        box: dict = {}

        def job():
            try:
                box["result"] = self._ingest_with_registry(source, text=text)
            except Exception as e:
                box["error"] = e
            finally:
                done.set()

        self._queue.put(job)
        if not done.wait(timeout):
            raise TimeoutError("摄入任务排队超时")
        if "error" in box:
            raise box["error"]
        return box["result"]

    # ---------- 摄入管线 ----------
    def _ingest_with_registry(
        self, source: str, path: Optional[Path] = None, text: Optional[str] = None
    ) -> IngestResult:
        """管线入口：驱动状态机 pending → parsing → 终态，失败时回滚（含 Langfuse trace）。"""
        registry = get_registry()
        registry.set_status(source, "parsing")
        with start_observation(
            "document_ingestion",
            as_type="span",
            input={"source": source, "type": "file" if path else "text"},
        ) as obs:
            try:
                result = self._ingest(source, path=path, text=text)
                registry.set_status(
                    source,
                    result.status,
                    chunks=result.new_chunks if result.status == "available" else None,
                    detail=result.detail,
                    error="",
                )
                # 内容发生变化（新增/替换片段）→ 清空查询缓存，避免新内容不可见
                if result.status == "available" and result.new_chunks > 0:
                    _, retriever, _, _ = get_engine()
                    retriever.cache.clear()
                obs.update(
                    output={
                        "status": result.status,
                        "new_chunks": result.new_chunks,
                        "dup_chunks": result.dup_chunks,
                        "detail": result.detail,
                    }
                )
                log.info(
                    "ingest_done",
                    source=source,
                    status=result.status,
                    new_chunks=result.new_chunks,
                    dup_chunks=result.dup_chunks,
                )
                return result
            except Exception as e:
                self._rollback(source)
                registry.set_status(source, "failed", error=str(e), detail="")
                obs.update(level="ERROR", status_message=str(e))
                log.error("ingest_failed", source=source, error=str(e))
                raise

    def _ingest(
        self, source: str, path: Optional[Path] = None, text: Optional[str] = None
    ) -> IngestResult:
        vs, retriever, loader, splitter = get_engine()
        dedup = get_dedup()

        # 首次使用前确保去重索引已加载（跳过预热直接摄入的场景）
        if not dedup.ready:
            dedup.sync(vs.get_all())

        # 1. 文件级去重：内容字节级一致则整体跳过
        if path is not None:
            file_hash = sha256_bytes(Path(path).read_bytes())
        else:
            file_hash = sha256_text(text)
        if dedup.is_known_file(file_hash):
            return IngestResult("duplicate", 0, 0, "内容与已有文档完全相同，跳过入库")

        # 2. 同名不同内容 → 替换更新：先删除旧片段并同步去重索引，
        #    避免旧哈希残留导致新版本未变化的片段被误判为重复
        replaced = 0
        old = get_registry().get(source)
        if old and old.get("chunks"):
            vs.delete_by_source(source)
            replaced = old["chunks"]
            dedup.sync(vs.get_all())

        # 3. 解析 + 切分
        if path is not None:
            docs = loader.load(path)
        else:
            docs = [Document(page_content=text, metadata={"source": source})]
        chunks = splitter.split(docs)
        for c in chunks:
            c.metadata["file_hash"] = file_hash
            # 强制覆盖：LangChain loader 默认写入完整路径作为 source，
            # 必须统一为注册表 key（文件名），否则替换更新时 delete_by_source 失效
            c.metadata["source"] = source

        # 4. 片段级去重（就地写入 chunk_hash 元数据）
        new_chunks, dup_chunks = dedup.filter_new_chunks(chunks)

        # 5. 入库 + 重建 BM25 + 同步去重索引
        if new_chunks:
            vs.add_documents(new_chunks)
        if new_chunks or replaced:
            retriever.refresh_bm25()
            dedup.sync(vs.get_all())

        if not new_chunks and not replaced:
            return IngestResult("duplicate", 0, dup_chunks, "所有片段均已存在，跳过入库")

        detail = f"入库 {len(new_chunks)} 个新片段"
        if dup_chunks:
            detail += f"，跳过 {dup_chunks} 个重复片段"
        if replaced:
            detail += f"，替换旧版本 {replaced} 个片段"
        return IngestResult("available", len(new_chunks), dup_chunks, detail)

    @staticmethod
    def _rollback(source: str) -> None:
        """失败回滚：清除该来源可能已写入的部分片段，保持向量库干净。"""
        try:
            vs, retriever, _, _ = get_engine()
            dedup: DedupIndex = get_dedup()
            vs.delete_by_source(source)
            retriever.refresh_bm25()
            dedup.sync(vs.get_all())
        except Exception:
            pass


# ---------- 模块级单例 ----------
_worker: Optional[IngestionWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> IngestionWorker:
    global _worker
    if _worker is None:
        with _worker_lock:
            if _worker is None:
                _worker = IngestionWorker()
                _worker.start()
    return _worker
