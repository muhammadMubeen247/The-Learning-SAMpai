"""KG audit script for e2e test verification.

Connects to Neo4j and reports on nodes/edges under workspace label 'classroom_1'.
"""
from __future__ import annotations

import sys

from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "sampai_neo4j_password"
DATABASE = "neo4j"
LABEL = "classroom_1"


def run(session, query, **params):
    return list(session.run(query, **params))


def main() -> int:
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    failures: list[str] = []

    try:
        with driver.session(database=DATABASE) as session:
            # 1. Total node count
            total_nodes = run(session, f"MATCH (n:`{LABEL}`) RETURN count(n) AS c")[0]["c"]
            print(f"1. Total nodes with label :{LABEL} = {total_nodes}")

            # 2. Total :RELATED edge count (both endpoints under this workspace)
            total_edges = run(
                session,
                f"MATCH (a:`{LABEL}`)-[r:RELATED]-(b:`{LABEL}`) RETURN count(DISTINCT r) AS c",
            )[0]["c"]
            print(f"2. Total :RELATED edges (within workspace) = {total_edges}")

            # 3. Node counts grouped by entity_type
            print("3. Node counts by entity_type:")
            rows = run(
                session,
                f"""
                MATCH (n:`{LABEL}`)
                RETURN coalesce(n.entity_type, '<null>') AS etype, count(n) AS c
                ORDER BY c DESC
                """,
            )
            type_counts = {r["etype"]: r["c"] for r in rows}
            for etype, c in type_counts.items():
                print(f"   - {etype}: {c}")
            modal_total = sum(type_counts.get(t, 0) for t in ("image", "table", "equation"))
            print(f"   image={type_counts.get('image', 0)} "
                  f"table={type_counts.get('table', 0)} "
                  f"equation={type_counts.get('equation', 0)} "
                  f"(modal total={modal_total})")

            # 4. Isolated modal entities (0 :RELATED edges)
            isolated_modal = run(
                session,
                f"""
                MATCH (n:`{LABEL}`)
                WHERE n.entity_type IN ['image','table','equation']
                  AND NOT (n)-[:RELATED]-()
                RETURN count(n) AS c
                """,
            )[0]["c"]
            print(f"4. Isolated modal entities (image/table/equation with 0 :RELATED) = {isolated_modal}")

            # 5. Null entity_type
            null_etype = run(
                session,
                f"""
                MATCH (n:`{LABEL}`)
                WHERE n.entity_type IS NULL
                RETURN count(n) AS c
                """,
            )[0]["c"]
            print(f"5. Nodes with null entity_type = {null_etype}")

            # 6. :RELATED edges with null/0 weight
            bad_weight_edges = run(
                session,
                f"""
                MATCH (a:`{LABEL}`)-[r:RELATED]-(b:`{LABEL}`)
                WHERE r.weight IS NULL OR r.weight = 0
                RETURN count(DISTINCT r) AS c
                """,
            )[0]["c"]
            print(f"6. :RELATED edges with weight IS NULL or weight = 0 = {bad_weight_edges}")

            # 7. Sample 3 image nodes
            print("7. Sample up to 3 image nodes:")
            image_samples = run(
                session,
                f"""
                MATCH (n:`{LABEL}`)
                WHERE n.entity_type = 'image'
                OPTIONAL MATCH (n)-[r:RELATED]-(m:`{LABEL}`)
                WITH n, count(DISTINCT m) AS neighbors
                RETURN n.entity_id AS entity_id,
                       n.description AS description,
                       neighbors
                LIMIT 3
                """,
            )
            if not image_samples:
                print("   (no image nodes found)")
            for row in image_samples:
                desc = row["description"] or ""
                if len(desc) > 120:
                    desc = desc[:120] + "..."
                desc = desc.replace("\n", " ")
                print(f"   - entity_id={row['entity_id']!r} neighbors={row['neighbors']} desc={desc!r}")

            # 8. Sample 3 edges between image and non-image
            print("8. Sample up to 3 image<->non-image :RELATED edges:")
            cross_edges = run(
                session,
                f"""
                MATCH (a:`{LABEL}`)-[r:RELATED]-(b:`{LABEL}`)
                WHERE a.entity_type = 'image'
                  AND (b.entity_type IS NULL OR b.entity_type <> 'image')
                RETURN a.entity_id AS src_id,
                       a.entity_type AS src_type,
                       b.entity_id AS tgt_id,
                       b.entity_type AS tgt_type,
                       r.weight AS weight
                LIMIT 3
                """,
            )
            if not cross_edges:
                print("   (no image<->non-image edges found)")
            for row in cross_edges:
                print(
                    f"   - ({row['src_id']!r}, {row['src_type']!r}) -> "
                    f"({row['tgt_id']!r}, {row['tgt_type']!r}) weight={row['weight']}"
                )

            # Verdict
            if total_nodes < 5:
                failures.append(f"total nodes {total_nodes} < 5")
            if total_edges < 3:
                failures.append(f"total edges {total_edges} < 3")
            if modal_total < 1:
                failures.append(f"modal entities (image/table/equation) count {modal_total} < 1")
            if isolated_modal != 0:
                failures.append(f"isolated modal entities = {isolated_modal} (expected 0)")
            if null_etype != 0:
                failures.append(f"null entity_type nodes = {null_etype} (expected 0)")
            if bad_weight_edges != 0:
                failures.append(f"null/0-weight edges = {bad_weight_edges} (expected 0)")

            print()
            if failures:
                print("VERDICT: FAIL")
                for f in failures:
                    print(f"  - {f}")
                return 1
            print("VERDICT: PASS")
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
