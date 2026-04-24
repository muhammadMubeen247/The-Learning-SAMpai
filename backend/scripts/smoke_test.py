"""
Smoke test — verify every infrastructure layer is reachable before running
the full backend.  Run this from the backend/ directory:

    python scripts/smoke_test.py

Each check prints PASS / FAIL / SKIP with a short explanation.
Exit code 0 = all enabled checks passed.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

# NumPy 2.x compatibility — patch before chromadb import
import numpy as np
if not hasattr(np, "float_"):
    np.float_ = np.float64   # type: ignore[attr-defined]
if not hasattr(np, "int_"):
    np.int_ = np.intp        # type: ignore[attr-defined]

# ── load .env early ──────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    from dotenv import load_dotenv
    load_dotenv(_env_path)
    print(f"Loaded env from {_env_path}")
else:
    print(f"No .env found at {_env_path} — using shell environment")

# ── helpers ──────────────────────────────────────────────────────────────────

PASS  = "\033[92mPASS\033[0m"
FAIL  = "\033[91mFAIL\033[0m"
SKIP  = "\033[93mSKIP\033[0m"
INFO  = "\033[94mINFO\033[0m"

failures: list[str] = []


def check(name: str, fn, *, required: bool = True):
    """Run a sync callable and print result."""
    try:
        msg = fn()
        print(f"  [{PASS}] {name}: {msg or 'ok'}")
    except Exception as e:
        tag = FAIL if required else SKIP
        print(f"  [{tag}] {name}: {e}")
        if required:
            failures.append(name)


async def acheck(name: str, fn, *, required: bool = True):
    """Run an async callable and print result."""
    try:
        msg = await fn()
        print(f"  [{PASS}] {name}: {msg or 'ok'}")
    except Exception as e:
        tag = FAIL if required else SKIP
        print(f"  [{tag}] {name}: {e}")
        if required:
            failures.append(name)


# ── individual checks ────────────────────────────────────────────────────────

def check_python():
    v = sys.version_info
    assert v >= (3, 11), f"Python {v.major}.{v.minor} < 3.11"
    return f"Python {v.major}.{v.minor}.{v.micro}"


def check_env_vars():
    missing = [v for v in [
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "CHROMA_DATA_DIR",
    ] if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")
    return "all required vars present"


def check_imports():
    """Verify all key packages are importable."""
    pkgs = [
        "fastapi", "uvicorn", "sqlalchemy", "asyncpg",
        "openai", "tiktoken", "chromadb", "neo4j",
        "docling", "numpy", "json_repair",
    ]
    failed = []
    for pkg in pkgs:
        try:
            __import__(pkg)
        except ImportError:
            failed.append(pkg)
    if failed:
        raise ImportError(f"Missing packages: {', '.join(failed)}")
    return f"{len(pkgs)} packages ok"


async def check_postgres():
    import asyncpg
    raw_url = os.environ["DATABASE_URL"]
    dsn = raw_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    t0 = time.monotonic()
    conn = await asyncpg.connect(dsn=dsn, timeout=5)
    row = await conn.fetchrow("SELECT version()")
    await conn.close()
    elapsed = time.monotonic() - t0
    return f"{row['version'][:40]}… ({elapsed*1000:.0f}ms)"


async def check_postgres_rag_tables():
    import asyncpg
    raw_url = os.environ["DATABASE_URL"]
    dsn = raw_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(dsn=dsn, timeout=5)
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN ('rag_kv_store','rag_doc_status')"
    )
    await conn.close()
    names = {r["table_name"] for r in tables}
    missing = {"rag_kv_store", "rag_doc_status"} - names
    if missing:
        raise RuntimeError(
            f"RAG tables missing: {missing}. Run: alembic upgrade head"
        )
    return "rag_kv_store + rag_doc_status exist"


async def check_neo4j():
    from neo4j import AsyncGraphDatabase
    uri      = os.environ["NEO4J_URI"]
    user     = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    t0 = time.monotonic()
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session(database=database) as session:
        result = await session.run("RETURN 1 AS n")
        record = await result.single()
        assert record["n"] == 1
    await driver.close()
    elapsed = time.monotonic() - t0
    return f"connected to {uri} ({elapsed*1000:.0f}ms)"


def check_chromadb():
    import chromadb
    from chromadb.config import Settings
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))
    client = chromadb.HttpClient(
        host=host,
        port=port,
        settings=Settings(anonymized_telemetry=False),
    )
    cols = client.list_collections()
    return f"{len(cols)} existing collections at http://{host}:{port}"


async def check_openai_embedding():
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    t0 = time.monotonic()
    resp = await client.embeddings.create(
        input=["smoke test"],
        model="text-embedding-3-small",
    )
    elapsed = time.monotonic() - t0
    dim = len(resp.data[0].embedding)
    assert dim == 1536, f"expected 1536, got {dim}"
    return f"1536-dim embedding ({elapsed*1000:.0f}ms)"


async def check_openai_llm():
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say OK"}],
        max_tokens=5,
    )
    elapsed = time.monotonic() - t0
    content = resp.choices[0].message.content or ""
    return f"response='{content.strip()}' ({elapsed*1000:.0f}ms)"


# ── main ─────────────────────────────────────────────────────────────────────

async def main():
    print("\n=== Learning SAMpai — Infrastructure Smoke Test ===\n")

    print("[ Environment ]")
    check("Python version",  check_python)
    check("Required env vars", check_env_vars)
    check("Package imports", check_imports)

    print("\n[ PostgreSQL ]")
    await acheck("Connection",   check_postgres)
    await acheck("RAG tables",   check_postgres_rag_tables)

    print("\n[ Neo4j ]")
    if os.getenv("NEO4J_URI"):
        await acheck("Connection", check_neo4j, required=True)
    else:
        print(f"  [{SKIP}] Neo4j: NEO4J_URI not set — skipping")

    print("\n[ ChromaDB ]")
    check("Local client", check_chromadb)

    print("\n[ OpenAI API ]")
    await acheck("Embedding (text-embedding-3-small)", check_openai_embedding)
    await acheck("LLM (gpt-4o-mini)",                  check_openai_llm)

    print()
    if failures:
        print(f"  [{FAIL}] {len(failures)} check(s) failed: {', '.join(failures)}")
        print("  Fix the above issues before starting the server.\n")
        sys.exit(1)
    else:
        print(f"  [{PASS}] All checks passed — ready to start the server.\n")
        print("  Next steps:")
        print("    uvicorn app.main:app --reload")
        print("    pytest app/tests/test_rag_unit.py -v")
        print("    pytest app/tests/test_rag_integration.py -v\n")


if __name__ == "__main__":
    asyncio.run(main())
