"""
PostgreSQL-backed document status storage for the RAG engine.
Tracks per-document processing state (pending/processing/processed/failed)
in the rag_doc_status table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.rag.base import DocProcessingStatus, DocStatus, DocStatusStorage
from app.rag.storage.postgres_kv import _get_pool
from app.rag.utils import logger


def _row_to_status(row: dict) -> DocProcessingStatus:
    chunks_list = row.get("chunks_list") or []
    if isinstance(chunks_list, str):
        chunks_list = json.loads(chunks_list)
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    return DocProcessingStatus(
        content_summary=row.get("content_summary", ""),
        content_length=row.get("content_length", 0),
        file_path=row.get("file_path", ""),
        status=DocStatus(row["status"]),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        track_id=row.get("doc_id"),
        chunks_count=row.get("chunks_count"),
        chunks_list=chunks_list,
        error_msg=row.get("error_msg"),
        metadata=meta,
    )


@dataclass
class PostgresDocStatusStorage(DocStatusStorage):
    """
    Document status storage backed by the rag_doc_status PostgreSQL table.

    Table schema (created by Alembic migration):
        workspace       VARCHAR(100)
        doc_id          VARCHAR(512)
        status          VARCHAR(50) DEFAULT 'pending'
        file_path       TEXT
        content_summary TEXT
        content_length  INTEGER     DEFAULT 0
        chunks_count    INTEGER
        chunks_list     JSONB
        error_msg       TEXT
        metadata        JSONB       DEFAULT '{}'
        created_at      TIMESTAMPTZ DEFAULT NOW()
        updated_at      TIMESTAMPTZ DEFAULT NOW()
        PRIMARY KEY (workspace, doc_id)
    """

    embedding_func: Any = field(default=None)

    async def initialize(self):
        await _get_pool()

    async def finalize(self):
        pass

    async def index_done_callback(self) -> None:
        pass

    # ------------------------------------------------------------------
    # BaseKVStorage interface (doc_id is the "key")
    # ------------------------------------------------------------------

    @staticmethod
    def _deserialize_row(row) -> dict[str, Any]:
        """Deserialize JSONB fields that asyncpg returns as strings."""
        d = dict(row)
        if isinstance(d.get("chunks_list"), str):
            d["chunks_list"] = json.loads(d["chunks_list"])
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        return d

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM rag_doc_status WHERE workspace=$1 AND doc_id=$2",
                self.workspace,
                id,
            )
        if row is None:
            return None
        return self._deserialize_row(row)

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM rag_doc_status WHERE workspace=$1 AND doc_id = ANY($2)",
                self.workspace,
                ids,
            )
        id_map = {row["doc_id"]: self._deserialize_row(row) for row in rows}
        return [id_map[i] for i in ids if i in id_map]

    async def filter_keys(self, keys: set[str]) -> set[str]:
        """Return doc_ids that do NOT yet exist in rag_doc_status."""
        if not keys:
            return set()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT doc_id FROM rag_doc_status WHERE workspace=$1 AND doc_id = ANY($2)",
                self.workspace,
                list(keys),
            )
        existing = {row["doc_id"] for row in rows}
        return keys - existing

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """Upsert document status records. Key = doc_id, value = status dict."""
        if not data:
            return
        pool = await _get_pool()
        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            async with conn.transaction():
                for doc_id, value in data.items():
                    await conn.execute(
                        """
                        INSERT INTO rag_doc_status (
                            workspace, doc_id, status, file_path,
                            content_summary, content_length,
                            chunks_count, chunks_list,
                            error_msg, metadata, created_at, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb, $11, $11
                        )
                        ON CONFLICT (workspace, doc_id) DO UPDATE SET
                            status          = EXCLUDED.status,
                            file_path       = EXCLUDED.file_path,
                            content_summary = EXCLUDED.content_summary,
                            content_length  = EXCLUDED.content_length,
                            chunks_count    = EXCLUDED.chunks_count,
                            chunks_list     = EXCLUDED.chunks_list,
                            error_msg       = EXCLUDED.error_msg,
                            metadata        = EXCLUDED.metadata,
                            updated_at      = EXCLUDED.updated_at
                        """,
                        self.workspace,
                        doc_id,
                        value.get("status", DocStatus.PENDING.value),
                        value.get("file_path", ""),
                        value.get("content_summary", ""),
                        value.get("content_length", 0),
                        value.get("chunks_count"),
                        json.dumps(value.get("chunks_list") or []),
                        value.get("error_msg"),
                        json.dumps(value.get("metadata") or {}),
                        now,
                    )

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM rag_doc_status WHERE workspace=$1 AND doc_id = ANY($2)",
                self.workspace,
                ids,
            )

    async def is_empty(self) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM rag_doc_status WHERE workspace=$1",
                self.workspace,
            )
        return row["cnt"] == 0

    async def drop(self) -> dict[str, str]:
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM rag_doc_status WHERE workspace=$1",
                    self.workspace,
                )
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(f"PostgresDocStatusStorage drop error: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # DocStatusStorage interface
    # ------------------------------------------------------------------

    async def get_status_counts(self) -> dict[str, int]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT status, COUNT(*) AS cnt FROM rag_doc_status WHERE workspace=$1 GROUP BY status",
                self.workspace,
            )
        return {row["status"]: row["cnt"] for row in rows}

    async def get_docs_by_status(
        self, status: DocStatus
    ) -> dict[str, DocProcessingStatus]:
        return await self.get_docs_by_statuses([status])

    async def get_docs_by_statuses(
        self, statuses: list[DocStatus]
    ) -> dict[str, DocProcessingStatus]:
        if not statuses:
            return {}
        pool = await _get_pool()
        status_values = [s.value for s in statuses]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM rag_doc_status WHERE workspace=$1 AND status = ANY($2)",
                self.workspace,
                status_values,
            )
        return {row["doc_id"]: _row_to_status(dict(row)) for row in rows}

    async def get_doc_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM rag_doc_status WHERE workspace=$1 AND file_path=$2",
                self.workspace,
                file_path,
            )
        return self._deserialize_row(row) if row else None

    # ------------------------------------------------------------------
    # Convenience helpers for the engine
    # ------------------------------------------------------------------

    async def set_status(
        self,
        doc_id: str,
        status: DocStatus,
        *,
        file_path: str = "",
        content_summary: str = "",
        content_length: int = 0,
        chunks_count: int | None = None,
        chunks_list: list[str] | None = None,
        error_msg: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Upsert a single document's status."""
        await self.upsert(
            {
                doc_id: {
                    "status": status.value,
                    "file_path": file_path,
                    "content_summary": content_summary,
                    "content_length": content_length,
                    "chunks_count": chunks_count,
                    "chunks_list": chunks_list or [],
                    "error_msg": error_msg,
                    "metadata": metadata or {},
                }
            }
        )
