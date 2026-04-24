"""
PostgreSQL-backed KV storage for the RAG engine.
Replaces LightRAG's JSON file storage with JSONB rows in PostgreSQL.
Uses asyncpg directly (not SQLAlchemy) for non-blocking I/O.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.rag.base import BaseKVStorage
from app.rag.utils import logger

# Module-level pool shared across all storage instances connecting to the same DB
_pool: asyncpg.Pool | None = None
# Lock is recreated each time the pool is closed so it stays bound to the
# current event loop (important for test isolation with per-function loops).
_pool_lock: asyncio.Lock | None = None


def _get_pool_lock() -> asyncio.Lock:
    """Return the current pool lock, creating it if needed for this event loop."""
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def close_pool() -> None:
    """Close the shared asyncpg pool. Call once on application shutdown or between tests."""
    global _pool, _pool_lock
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL asyncpg pool closed")
    # Reset the lock so the next pool creation binds to the current event loop
    _pool_lock = None


async def _get_pool() -> asyncpg.Pool:
    """Lazily initialize and return the shared asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    lock = _get_pool_lock()
    async with lock:
        if _pool is not None:
            return _pool

        database_url = os.environ["DATABASE_URL"]
        # asyncpg expects postgresql:// not postgresql+psycopg://
        dsn = database_url.replace("postgresql+psycopg://", "postgresql://").replace(
            "postgresql+asyncpg://", "postgresql://"
        )

        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        host_part = dsn.split("@")[-1] if "@" in dsn else dsn
        logger.info("PostgreSQL asyncpg pool ready — host=%s (min=1, max=10)", host_part)
    return _pool


@dataclass
class PostgresKVStorage(BaseKVStorage):
    """
    KV storage backed by the rag_kv_store PostgreSQL table.

    Table schema (created by Alembic migration):
        workspace  VARCHAR(100)
        namespace  VARCHAR(100)
        key        VARCHAR(512)
        value      JSONB
        PRIMARY KEY (workspace, namespace, key)
    """

    embedding_func: Any = field(default=None)

    async def initialize(self):
        await _get_pool()

    async def finalize(self):
        pass  # Pool is shared; don't close it here

    async def index_done_callback(self) -> None:
        pass  # PostgreSQL persists immediately; no-op

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM rag_kv_store WHERE workspace=$1 AND namespace=$2 AND key=$3",
                self.workspace,
                self.namespace,
                id,
            )
        if row is None:
            return None
        val = row["value"]
        return val if isinstance(val, dict) else json.loads(val)

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value FROM rag_kv_store WHERE workspace=$1 AND namespace=$2 AND key = ANY($3)",
                self.workspace,
                self.namespace,
                ids,
            )
        result_map = {}
        for row in rows:
            val = row["value"]
            result_map[row["key"]] = val if isinstance(val, dict) else json.loads(val)
        # Return in the same order as input ids
        return [result_map[i] for i in ids if i in result_map]

    async def filter_keys(self, keys: set[str]) -> set[str]:
        """Return keys that do NOT exist in storage (new keys to be inserted)."""
        if not keys:
            return set()
        logger.debug("[%s/%s] filter_keys: checking %d keys", self.workspace, self.namespace, len(keys))
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key FROM rag_kv_store WHERE workspace=$1 AND namespace=$2 AND key = ANY($3)",
                self.workspace,
                self.namespace,
                list(keys),
            )
        existing = {row["key"] for row in rows}
        new_keys = keys - existing
        logger.debug(
            "[%s/%s] filter_keys: %d new, %d already exist",
            self.workspace, self.namespace, len(new_keys), len(existing),
        )
        return new_keys

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        if not data:
            return
        logger.debug("[%s/%s] upsert: %d key(s)", self.workspace, self.namespace, len(data))
        try:
            pool = await _get_pool()
            now = datetime.now(timezone.utc)
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for key, value in data.items():
                        await conn.execute(
                            """
                            INSERT INTO rag_kv_store (workspace, namespace, key, value, created_at, updated_at)
                            VALUES ($1, $2, $3, $4::jsonb, $5, $5)
                            ON CONFLICT (workspace, namespace, key)
                            DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                            """,
                            self.workspace,
                            self.namespace,
                            key,
                            json.dumps(value),
                            now,
                        )
        except Exception as e:
            logger.error(
                "[%s/%s] upsert FAILED for %d key(s): %s",
                self.workspace, self.namespace, len(data), e, exc_info=True,
            )
            raise

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        logger.debug("[%s/%s] delete: %d key(s)", self.workspace, self.namespace, len(ids))
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM rag_kv_store WHERE workspace=$1 AND namespace=$2 AND key = ANY($3)",
                self.workspace,
                self.namespace,
                ids,
            )

    async def is_empty(self) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM rag_kv_store WHERE workspace=$1 AND namespace=$2",
                self.workspace,
                self.namespace,
            )
        return row["cnt"] == 0

    async def drop(self) -> dict[str, str]:
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM rag_kv_store WHERE workspace=$1 AND namespace=$2",
                    self.workspace,
                    self.namespace,
                )
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(f"PostgresKVStorage drop error: {e}")
            return {"status": "error", "message": str(e)}
