"""
reset_all_dbs.py — wipe all stateful stores before an E2E run.

  1. Postgres: DROP SCHEMA public CASCADE; CREATE SCHEMA public; then alembic upgrade head
  2. Neo4j: MATCH (n) DETACH DELETE n
  3. ChromaDB: delete every collection on the running HTTP server
  4. Local chroma_data directory (leftovers from the old PersistentClient era, if any)

R2 is intentionally left alone — uploaded keys are scoped by folder_id,
which is re-issued after a Postgres reset, so old R2 objects can't collide.

Usage (from backend/ directory):
    .venv\\Scripts\\python.exe scripts/reset_all_dbs.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import asyncio

# NumPy 2.x shim before chromadb import
import numpy as np
if not hasattr(np, "float_"):
    np.float_ = np.float64   # type: ignore[attr-defined]
if not hasattr(np, "int_"):
    np.int_ = np.intp        # type: ignore[attr-defined]

# Load .env from backend/
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=True)


def _to_asyncpg_dsn(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
           .replace("postgresql+asyncpg://", "postgresql://")
    )


# Latest Alembic head — update this whenever a new migration is added.
_CURRENT_HEAD = "a1b2c3d4e5f6"

_RAG_KV_STORE_DDL = """
CREATE TABLE IF NOT EXISTS rag_kv_store (
    workspace  VARCHAR(100) NOT NULL,
    namespace  VARCHAR(100) NOT NULL,
    key        VARCHAR(512) NOT NULL,
    value      JSONB        NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace, namespace, key)
);
CREATE INDEX IF NOT EXISTS idx_rag_kv_ws_ns ON rag_kv_store (workspace, namespace);
"""

_RAG_DOC_STATUS_DDL = """
CREATE TABLE IF NOT EXISTS rag_doc_status (
    workspace        VARCHAR(100) NOT NULL,
    doc_id           VARCHAR(512) NOT NULL,
    status           VARCHAR(50)  NOT NULL DEFAULT 'pending',
    file_path        TEXT,
    content_summary  TEXT,
    content_length   INTEGER,
    chunks_count     INTEGER,
    chunks_list      JSONB,
    error_msg        TEXT,
    metadata         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_rag_doc_status_ws ON rag_doc_status (workspace);
CREATE INDEX IF NOT EXISTS idx_rag_doc_status_fp ON rag_doc_status (file_path);
"""

# Seed the SAMpai system user (normally done by alembic migration a6b7c8d9e0f1).
# ON CONFLICT DO NOTHING makes this idempotent if the script is re-run.
_SAMPAI_SEED_SQL = """
INSERT INTO users (username, email, hashed_password, is_system)
VALUES ('SAMpai', 'sampai@system.local', '!locked!', TRUE)
ON CONFLICT (username) DO NOTHING
"""

# Stamp the alembic_version table so that running 'alembic upgrade head' after
# this script doesn't try to re-create tables that already exist.
# Update _CURRENT_HEAD above whenever a new migration is added.
_ALEMBIC_STAMP_DDL = f"""
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num)
VALUES ('{_CURRENT_HEAD}')
ON CONFLICT (version_num) DO NOTHING;
"""


async def reset_postgres() -> None:
    """
    Alembic needs psycopg (SAC-blocked on this Windows box). The app itself
    uses asyncpg (unblocked), so we reproduce the migration outcome manually:
      1. Drop + recreate the `public` schema via asyncpg
      2. Create ORM tables via SQLAlchemy's Base.metadata.create_all (async)
      3. Apply the RAG-tables DDL straight through asyncpg
    """
    import asyncpg
    dsn = _to_asyncpg_dsn(os.environ["DATABASE_URL"])
    print("[pg]   connecting to", dsn.split("@")[-1])
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute("DROP SCHEMA public CASCADE;")
        await conn.execute("CREATE SCHEMA public;")
        await conn.execute("GRANT ALL ON SCHEMA public TO public;")
        print("[pg]   public schema dropped + recreated")
    finally:
        await conn.close()

    # ORM tables (users, classrooms, folders, files w/ rag_doc_id, chat_messages)
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from app.database.init_db import init_db
    from app.database.session import async_engine
    await init_db()
    print("[pg]   ORM tables created via Base.metadata.create_all")

    # RAG tables + SAMpai seed + Alembic version stamp
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(_RAG_KV_STORE_DDL)
        await conn.execute(_RAG_DOC_STATUS_DDL)
        print("[pg]   rag_kv_store + rag_doc_status created")
        await conn.execute(_SAMPAI_SEED_SQL)
        print("[pg]   SAMpai system user seeded")
        await conn.execute(_ALEMBIC_STAMP_DDL)
        print(f"[pg]   Alembic version stamped → {_CURRENT_HEAD}")
    finally:
        await conn.close()

    # Close the SQLAlchemy engine so we don't leak a pool between reset runs
    await async_engine.dispose()


async def reset_neo4j() -> None:
    from neo4j import AsyncGraphDatabase
    uri  = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USERNAME"]
    pwd  = os.environ["NEO4J_PASSWORD"]
    db   = os.environ.get("NEO4J_DATABASE", "neo4j")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))
    try:
        async with driver.session(database=db) as session:
            # Drop nodes + relations
            result = await session.run("MATCH (n) DETACH DELETE n")
            await result.consume()

            # Drop workspace-isolation constraints the engine re-creates on init
            result = await session.run(
                "SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names"
            )
            rec = await result.single()
            names = rec["names"] if rec else []
            for n in names:
                try:
                    await session.run(f"DROP CONSTRAINT `{n}` IF EXISTS")
                except Exception as e:
                    print(f"[neo4j] could not drop constraint {n}: {e}")
            print(f"[neo4j] nodes deleted, {len(names)} constraint(s) dropped")
    finally:
        await driver.close()


def reset_chroma() -> None:
    import chromadb
    from chromadb.config import Settings

    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))

    client = chromadb.HttpClient(
        host=host, port=port,
        settings=Settings(anonymized_telemetry=False),
    )
    cols = client.list_collections()
    for c in cols:
        client.delete_collection(c.name)
    print(f"[chroma] deleted {len(cols)} collections on http://{host}:{port}")

    # Nuke any leftover local chroma_data dir from the PersistentClient era
    local_dir = os.path.join(
        os.path.dirname(__file__), "..",
        os.environ.get("CHROMA_DATA_DIR", "chroma_data"),
    )
    if os.path.exists(local_dir):
        shutil.rmtree(local_dir, ignore_errors=True)
        print(f"[chroma] removed local dir {local_dir}")


async def main() -> int:
    print("=== reset_all_dbs.py ===")
    try:
        await reset_postgres()
    except Exception as e:
        print(f"[pg]   FAILED: {e}")
        return 1
    try:
        await reset_neo4j()
    except Exception as e:
        print(f"[neo4j] FAILED: {e}")
        return 1
    try:
        reset_chroma()
    except Exception as e:
        print(f"[chroma] FAILED: {e}")
        return 1
    print("=== all stores reset ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
