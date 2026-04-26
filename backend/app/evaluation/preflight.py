"""
Pre-flight checks: verify all services are reachable and the target file is
ingested before burning API tokens on the benchmark.
"""
import asyncio
import os
import sys


def _pg_dsn() -> str:
    return (
        os.environ["DATABASE_URL"]
        .replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


async def _check_postgres() -> None:
    import asyncpg

    dsn = _pg_dsn()
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5)
        await conn.close()
    except Exception as exc:
        sys.exit(f"[preflight] Postgres unreachable: {exc}")


async def _check_neo4j() -> None:
    from neo4j import AsyncGraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))
    try:
        await asyncio.wait_for(driver.verify_connectivity(), timeout=5)
    except Exception as exc:
        await driver.close()
        sys.exit(f"[preflight] Neo4j unreachable at {uri}: {exc}")
    await driver.close()


async def _check_chroma() -> None:
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3
        )
        writer.close()
        await writer.wait_closed()
    except Exception as exc:
        sys.exit(f"[preflight] ChromaDB unreachable at {host}:{port}: {exc}")


def _check_openai_key() -> None:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or key.startswith("your_") or key == "sk-test-placeholder":
        sys.exit(
            "[preflight] OPENAI_API_KEY is missing or is a placeholder. "
            "Set it in .env.docker or your environment."
        )


async def _check_file_ingested(classroom_id: int, file_url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_pg_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT f.processing_status, cl.id AS classroom_id
            FROM files f
            JOIN folders fo ON fo.id = f.folder_id
            JOIN classrooms cl ON cl.id = fo.classroom_id
            WHERE f.file_url = $1
            """,
            file_url,
        )
    finally:
        await conn.close()

    if row is None:
        sys.exit(f"[preflight] No file found with file_url={file_url!r}")
    if str(row["processing_status"]).upper() != "COMPLETED":
        sys.exit(
            f"[preflight] File processing_status={row['processing_status']!r} — "
            "must be COMPLETED before benchmarking."
        )
    if row["classroom_id"] != classroom_id:
        sys.exit(
            f"[preflight] file_url belongs to classroom {row['classroom_id']}, "
            f"but --classroom-id={classroom_id} was passed."
        )


async def run_all(classroom_id: int, file_url: str) -> None:
    print("[preflight] Checking services and file status...")
    _check_openai_key()
    await asyncio.gather(_check_postgres(), _check_neo4j(), _check_chroma())
    await _check_file_ingested(classroom_id, file_url)
    print("[preflight] All checks passed.\n")
