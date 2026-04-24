"""
Real-time Knowledge Graph watcher.
Polls Neo4j every 3 seconds and prints each new node/edge as it appears.
Run BEFORE uploading a file to see the KG being built live.

Usage (from backend/ directory):
    .venv/Scripts/python.exe scripts/watch_kg.py
"""
import io
import os
import sys
import time

# Force UTF-8 output so box-drawing chars and Unicode don't crash on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USERNAME", "neo4j")
PASS = os.getenv("NEO4J_PASSWORD", "sampai_neo4j_password")
POLL = 3  # seconds between checks

MODAL_TYPES = {"image", "document_scan", "table", "equation"}

def ts():
    return datetime.now().strftime("%H:%M:%S")

def poll(driver, seen_nodes: set, seen_edges: set):
    with driver.session() as s:
        node_rows = s.run(
            "MATCH (n) WHERE n.entity_id IS NOT NULL "
            "RETURN n.entity_id AS id, n.entity_type AS t, n.description AS d "
            "LIMIT 5000"
        ).data()
        edge_rows = s.run(
            "MATCH (a)-[r:RELATED]->(b) "
            "WHERE a.entity_id IS NOT NULL AND b.entity_id IS NOT NULL "
            "RETURN a.entity_id AS src, b.entity_id AS tgt, "
            "       r.keywords AS k, r.weight AS w "
            "LIMIT 5000"
        ).data()

    new_nodes = [r for r in node_rows if r["id"] not in seen_nodes]
    new_edges = [r for r in edge_rows if (r["src"], r["tgt"]) not in seen_edges]

    for r in new_nodes:
        seen_nodes.add(r["id"])
        ntype = r["t"] or "unknown"
        desc  = (r["d"] or "")[:90].replace("\n", " ")
        modal = " [MODAL]" if ntype in MODAL_TYPES else ""
        print(f"[{ts()}] NODE +{len(seen_nodes):>3}{modal}  ({ntype})  {r['id']}  —  {desc}")

    for r in new_edges:
        seen_edges.add((r["src"], r["tgt"]))
        w = f"{r['w']:.3f}" if r["w"] is not None else "None"
        kw = (r["k"] or "")[:60]
        print(f"[{ts()}] EDGE +{len(seen_edges):>3}  {r['src']}  →  {r['tgt']}  w={w}  kw=[{kw}]")

    if new_nodes or new_edges:
        print(f"[{ts()}] --- TOTALS: {len(seen_nodes)} nodes, {len(seen_edges)} edges ---\n")
        sys.stdout.flush()


def main():
    print(f"Connecting to Neo4j at {URI}...")
    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASS))
        driver.verify_connectivity()
    except ServiceUnavailable as e:
        print(f"ERROR: Cannot connect to Neo4j — {e}")
        print("Make sure Neo4j is running: docker compose up neo4j")
        sys.exit(1)

    print("Connected. Watching KG — new nodes/edges will appear below as they are written.\n"
          "Run this BEFORE uploading a file to see the full build live.\n"
          "Press Ctrl+C to stop.\n")
    seen_nodes: set = set()
    seen_edges: set = set()

    # Snapshot current state so we only show deltas from now on
    print("Snapshotting existing graph (pre-upload baseline)...")
    poll(driver, seen_nodes, seen_edges)
    print(f"Baseline: {len(seen_nodes)} nodes, {len(seen_edges)} edges already in graph.\n"
          "Watching for NEW nodes/edges...\n")

    while True:
        try:
            poll(driver, seen_nodes, seen_edges)
        except ServiceUnavailable as e:
            print(f"[{ts()}] [poll error] Neo4j unavailable: {e}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[{ts()}] [poll error] {e}")
        time.sleep(POLL)

    print(f"\nStopped. Final: {len(seen_nodes)} nodes, {len(seen_edges)} edges.")
    driver.close()


if __name__ == "__main__":
    main()
