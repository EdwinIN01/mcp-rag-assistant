"""文档注册表：SQLite 持久化的文档状态机。

状态流转：
    pending（已接收，排队中）
      → parsing（工作线程解析中）
        → available（入库成功，可检索）
        → duplicate（内容完全重复，跳过入库）
        → failed（解析/入库失败，已回滚向量库写入）

注册表与向量库解耦：Chroma 是 available 数据的事实源，注册表记录生命周期；
启动/查询时的 sync 可将向量库中存在但注册表缺失的来源自愈为 available。
"""
import datetime
import sqlite3
import threading
from pathlib import Path
from typing import Optional

STATUSES = ("pending", "parsing", "available", "duplicate", "failed")


class DocumentRegistry:
    """线程安全的 SQLite 注册表（单进程内共享一个连接 + 互斥锁）。"""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_table()

    def _create_table(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    source     TEXT PRIMARY KEY,
                    file_hash  TEXT,
                    status     TEXT NOT NULL DEFAULT 'pending',
                    chunks     INTEGER NOT NULL DEFAULT 0,
                    error      TEXT NOT NULL DEFAULT '',
                    detail     TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    # ---------- 基础 CRUD ----------
    def upsert(
        self,
        source: str,
        file_hash: Optional[str] = None,
        status: str = "pending",
        chunks: int = 0,
        error: str = "",
        detail: str = "",
    ) -> None:
        """插入或重置一条记录（重新上传同名文档时回到 pending，保留原 chunks 计数）。"""
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO documents (source, file_hash, status, chunks, error, detail, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    file_hash  = excluded.file_hash,
                    status     = excluded.status,
                    error      = excluded.error,
                    detail     = excluded.detail,
                    updated_at = excluded.updated_at
                """,
                (source, file_hash, status, chunks, error, detail, now, now),
            )
            self._conn.commit()

    def set_status(
        self,
        source: str,
        status: str,
        chunks: Optional[int] = None,
        error: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """更新状态；chunks/error/detail 传 None 表示不改动该字段。"""
        sets = ["status = ?", "updated_at = ?"]
        params: list = [status, self._now()]
        if chunks is not None:
            sets.append("chunks = ?")
            params.append(chunks)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if detail is not None:
            sets.append("detail = ?")
            params.append(detail)
        params.append(source)
        with self._lock:
            self._conn.execute(
                f"UPDATE documents SET {', '.join(sets)} WHERE source = ?", params
            )
            self._conn.commit()

    def get(self, source: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE source = ?", (source,)
            ).fetchone()
        return dict(row) if row else None

    def remove(self, source: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM documents WHERE source = ?", (source,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list_all(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- 与向量库自愈同步 ----------
    def sync_with_vectorstore(self, all_data: dict) -> int:
        """注册表 ← 向量库 双向对齐，返回发生变更的记录数。

        - 向量库存在但注册表缺失 → 补录为 available（迁移历史文档 / MCP 等旁路写入）
        - 注册表 available 但片段数与向量库不符 → 校正计数
        - 注册表 available 但向量库已不存在 → 移除（被外部删除）
        """
        counts: dict[str, int] = {}
        for meta in all_data.get("metadatas", []):
            if meta and meta.get("source"):
                source = meta["source"]
                counts[source] = counts.get(source, 0) + 1

        existing = {row["source"]: row for row in self.list_all()}
        synced = 0

        for source, cnt in counts.items():
            row = existing.get(source)
            if row is None:
                self.upsert(
                    source, status="available", chunks=cnt,
                    detail="同步：检测到向量库中已存在",
                )
                synced += 1
            elif row["status"] == "available" and row["chunks"] != cnt:
                self.set_status(source, "available", chunks=cnt)
                synced += 1

        for source, row in existing.items():
            if source not in counts and row["status"] == "available":
                self.remove(source)
                synced += 1

        return synced

    def close(self) -> None:
        with self._lock:
            self._conn.close()
