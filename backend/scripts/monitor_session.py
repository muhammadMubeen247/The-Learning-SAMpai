"""
E2E session monitor — checks Neo4j + Postgres every 30 seconds.
Flags anomalies and prints a final report when you Ctrl+C.

Usage (from backend/ directory, with env vars set or after start_dev.bat):
    .venv\Scripts\python.exe scripts\monitor_session.py
"""
import io
import os
import sys
import time
import asyncio
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# When stdout is redirected on Windows, Python picks cp1252 and chokes on the
# box-drawing characters we print. Force UTF-8 so redirected runs don't spew
# 'charmap' codec errors.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── connection settings ────────────────────────────────────────────────────────
NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sampai_neo4j_password")
PG_DSN     = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:password@localhost:5433/Learning_SAMpai_db"
).replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")

POLL_INTERVAL = 30  # seconds

# ── session state ──────────────────────────────────────────────────────────────
session_start = datetime.now()
events: list[str] = []           # timestamped log lines
anomalies: list[str] = []        # flagged problems
seen_doc_statuses: dict = {}     # workspace -> status, to detect transitions
node_history: list[tuple] = []   # (ts, total_nodes, total_edges)
entity_type_history: list = []   # list of dicts


def ts():
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str, flag: bool = False):
    line = f"[{ts()}] {'!!! ' if flag else ''}{msg}"
    print(line, flush=True)
    events.append(line)
    if flag:
        anomalies.append(line)


# ── Neo4j helpers ──────────────────────────────────────────────────────────────
_neo4j_driver = None


def get_neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    return _neo4j_driver


def neo4j_query(cypher: str, **params):
    d = get_neo4j()
    with d.session() as s:
        return s.run(cypher, **params).data()


# ── Postgres helpers ───────────────────────────────────────────────────────────
_pg_pool = None


async def get_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3, command_timeout=10)
    return _pg_pool


async def pg_query(sql: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql)


# ── check functions ────────────────────────────────────────────────────────────

def check_neo4j_nodes() -> tuple[int, int, dict]:
    """Returns (total_nodes, total_edges, entity_type_counts)."""
    try:
        rows = neo4j_query(
            "MATCH (n) WHERE n.entity_id IS NOT NULL "
            "RETURN n.entity_type AS t, count(n) AS c ORDER BY c DESC"
        )
        total = sum(r["c"] for r in rows)
        by_type = {r["t"] or "null": r["c"] for r in rows}

        edge_rows = neo4j_query("MATCH ()-[r:RELATED]->() RETURN count(r) AS c")
        edges = edge_rows[0]["c"] if edge_rows else 0

        return total, edges, by_type
    except Exception as e:
        log(f"Neo4j node check failed: {e}", flag=True)
        return -1, -1, {}


def check_image_entities_without_edges():
    """Returns list of image entities (NOT document_scan) with zero RELATED edges."""
    try:
        rows = neo4j_query(
            "MATCH (img) WHERE img.entity_type = 'image' "
            "AND NOT (img)-[:RELATED]-() "
            "RETURN img.entity_id AS id, img.description AS d"
        )
        return rows
    except Exception as e:
        log(f"Image entity edge check failed: {e}", flag=True)
        return []


def check_null_entity_types():
    try:
        rows = neo4j_query(
            "MATCH (n) WHERE n.entity_type IS NULL AND n.entity_id IS NOT NULL "
            "RETURN n.entity_id AS id LIMIT 20"
        )
        return [r["id"] for r in rows]
    except Exception as e:
        log(f"Null entity-type check failed: {e}", flag=True)
        return []


def check_zero_weight_edges():
    try:
        rows = neo4j_query(
            "MATCH ()-[r:RELATED]->() WHERE r.weight IS NULL OR r.weight = 0 "
            "RETURN count(r) AS c"
        )
        return rows[0]["c"] if rows else 0
    except Exception as e:
        log(f"Zero-weight edge check failed: {e}", flag=True)
        return -1


async def check_postgres():
    """Returns (doc_status_rows, stuck_files)."""
    try:
        status_rows = await pg_query(
            "SELECT workspace, status, count(*) AS cnt "
            "FROM rag_doc_status GROUP BY workspace, status ORDER BY workspace, status"
        )
        now = datetime.now(timezone.utc)
        five_min_ago = now - timedelta(minutes=5)
        stuck = await pg_query(
            f"SELECT id, filename AS name, processing_status AS status, processed_at AS updated_at FROM files "
            f"WHERE processing_status = 'PROCESSING' AND processed_at < '{five_min_ago.isoformat()}'"
        )
        failed = await pg_query(
            "SELECT id, filename AS name, processing_status AS status, processed_at AS updated_at FROM files "
            "WHERE processing_status = 'FAILED'"
        )
        return list(status_rows), list(stuck), list(failed)
    except Exception as e:
        log(f"Postgres check failed: {e}", flag=True)
        return [], [], []


async def check_workspace_mismatch(doc_status_rows):
    """Flag workspaces that are COMPLETED in Postgres but have 0 Neo4j nodes."""
    completed_workspaces = [
        r["workspace"] for r in doc_status_rows if r["status"] == "completed"
    ]
    for ws in completed_workspaces:
        label = ws  # e.g. classroom_1
        try:
            rows = neo4j_query(f"MATCH (n:`{label}`) RETURN count(n) AS c")
            count = rows[0]["c"] if rows else 0
            if count == 0:
                log(f"MISMATCH: workspace '{ws}' is COMPLETED in Postgres but has 0 Neo4j nodes!", flag=True)
        except Exception as e:
            log(f"Workspace mismatch check failed for {ws}: {e}", flag=True)


# ── single poll cycle ──────────────────────────────────────────────────────────

async def poll(cycle: int):
    print(f"\n{'─'*60}")
    print(f"[{ts()}] CHECK #{cycle}")
    print(f"{'─'*60}")

    # Neo4j
    total_nodes, total_edges, by_type = check_neo4j_nodes()
    if total_nodes >= 0:
        node_history.append((datetime.now(), total_nodes, total_edges))
        entity_type_history.append(by_type)
        prev_nodes = node_history[-2][1] if len(node_history) > 1 else 0
        prev_edges = node_history[-2][2] if len(node_history) > 1 else 0
        delta_n = total_nodes - prev_nodes
        delta_e = total_edges - prev_edges
        print(f"  Neo4j  — nodes: {total_nodes:>4} (+{delta_n:>3})  |  edges: {total_edges:>4} (+{delta_e:>3})")
        if by_type:
            type_str = "  |  ".join(f"{t}: {c}" for t, c in sorted(by_type.items()))
            print(f"           types: {type_str}")

    # Image entities without edges
    isolated = check_image_entities_without_edges()
    if isolated:
        log(f"IMAGE ENTITIES WITH NO EDGES ({len(isolated)}): "
            + ", ".join(r["id"] for r in isolated), flag=True)

    # Null entity types
    nulls = check_null_entity_types()
    if nulls:
        log(f"ENTITIES WITH NULL entity_type: {nulls}", flag=True)

    # Zero-weight edges
    zw = check_zero_weight_edges()
    if zw > 0:
        log(f"EDGES with weight=NULL or 0: {zw}", flag=True)

    # Postgres
    doc_rows, stuck, failed = await check_postgres()

    if doc_rows:
        print(f"  Postgres doc_status:")
        for r in doc_rows:
            print(f"    {r['workspace']:30s}  {r['status']:12s}  x{r['cnt']}")
    else:
        print(f"  Postgres doc_status: (empty)")

    # Detect status transitions
    for r in doc_rows:
        key = f"{r['workspace']}:{r['status']}"
        if key not in seen_doc_statuses:
            seen_doc_statuses[key] = True
            log(f"STATUS TRANSITION → workspace='{r['workspace']}' status='{r['status']}'")

    if failed:
        for f in failed:
            log(f"FAILED FILE: id={f['id']} name={f['name']} updated_at={f['updated_at']}", flag=True)

    if stuck:
        for f in stuck:
            log(f"STUCK IN PROCESSING >5min: id={f['id']} name={f['name']} since={f['updated_at']}", flag=True)

    # Workspace/Neo4j mismatch
    await check_workspace_mismatch(doc_rows)


# ── final report ───────────────────────────────────────────────────────────────

def print_report():
    elapsed = datetime.now() - session_start
    print(f"\n{'='*60}")
    print(f"SESSION REPORT — {elapsed.seconds // 60}m {elapsed.seconds % 60}s elapsed")
    print(f"{'='*60}\n")

    print(f"Total checks run: {len(node_history)}")
    if node_history:
        final_nodes, final_edges = node_history[-1][1], node_history[-1][2]
        print(f"Final KG state:  {final_nodes} nodes, {final_edges} edges")

        # Entity type distribution at end
        if entity_type_history:
            last_types = entity_type_history[-1]
            print("\nEntity type distribution (final):")
            for t, c in sorted(last_types.items(), key=lambda x: -x[1]):
                bar = "█" * min(c, 40)
                print(f"  {t:25s} {c:>4}  {bar}")

        # KG growth timeline
        print("\nKG growth timeline:")
        for snapshot_time, n, e in node_history:
            print(f"  {snapshot_time.strftime('%H:%M:%S')}  nodes={n:>4}  edges={e:>4}")

    print(f"\nTotal anomalies flagged: {len(anomalies)}")
    if anomalies:
        print("\nAll anomalies:")
        for a in anomalies:
            print(f"  {a}")
    else:
        print("  None — pipeline ran clean.")

    print(f"\n{'='*60}")


# ── main loop ──────────────────────────────────────────────────────────────────

async def main():
    print(f"Session Monitor started at {ts()}")
    print(f"Neo4j: {NEO4J_URI}  |  Postgres: {PG_DSN.split('@')[-1]}")
    print(f"Poll interval: {POLL_INTERVAL}s  |  Ctrl+C to stop and see final report.\n")

    # Check Neo4j connectivity
    try:
        get_neo4j().verify_connectivity()
        print(f"[{ts()}] Neo4j connection: OK")
    except Exception as e:
        print(f"[{ts()}] Neo4j not reachable yet ({e}) — will keep trying each cycle.")

    cycle = 0
    try:
        while True:
            cycle += 1
            try:
                await poll(cycle)
            except Exception as e:
                log(f"Poll #{cycle} error: {e}", flag=True)
            await asyncio.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print(f"\n[{ts()}] Stopped by user.")
    finally:
        print_report()
        if _pg_pool:
            await _pg_pool.close()
        if _neo4j_driver:
            _neo4j_driver.close()


if __name__ == "__main__":
    asyncio.run(main())
