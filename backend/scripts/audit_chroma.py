"""ChromaDB audit script for classroom_1 workspace after E2E test."""
from __future__ import annotations

import sys

import chromadb
from chromadb.config import Settings


WORKSPACE = "classroom_1"
EXPECTED_COLLECTIONS = [
    f"{WORKSPACE}__entities",
    f"{WORKSPACE}__relationships",
    f"{WORKSPACE}__chunks",
]
TARGET_PPTX = "Chapter1_HRM_With_Cartoons_Icons_and_Video.pptx"
MODAL_TYPES = {"image", "table", "equation"}


def truncate(s: str, n: int = 200) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= n else s[:n] + "...[truncated]"


def main() -> int:
    client = chromadb.HttpClient(
        host="localhost",
        port=8001,
        settings=Settings(anonymized_telemetry=False),
    )

    failures: list[str] = []

    # List existing collections to give context if something is missing.
    try:
        existing = [c.name for c in client.list_collections()]
    except Exception as exc:
        print(f"ERROR: could not list collections: {exc!r}")
        return 2
    print(f"Existing collections on server ({len(existing)}):")
    for name in existing:
        print(f"  - {name}")
    print()

    collection_counts: dict[str, int] = {}
    modal_entity_count = 0
    pptx_chunk_count = 0

    for cname in EXPECTED_COLLECTIONS:
        print("=" * 72)
        print(f"Collection: {cname}")
        print("=" * 72)
        if cname not in existing:
            print(f"  MISSING: collection '{cname}' not present on server")
            failures.append(f"collection missing: {cname}")
            collection_counts[cname] = 0
            print()
            continue

        coll = client.get_collection(cname)
        try:
            count = coll.count()
        except Exception as exc:
            print(f"  ERROR calling .count(): {exc!r}")
            failures.append(f"count error on {cname}: {exc!r}")
            collection_counts[cname] = 0
            print()
            continue
        collection_counts[cname] = count
        print(f"  count() = {count}")
        if count <= 0:
            failures.append(f"count is 0 for {cname}")

        # First 2 items
        try:
            sample = coll.get(limit=2)
        except Exception as exc:
            print(f"  ERROR calling .get(limit=2): {exc!r}")
            failures.append(f"get error on {cname}: {exc!r}")
            print()
            continue

        ids = sample.get("ids") or []
        docs = sample.get("documents") or []
        metas = sample.get("metadatas") or []

        print(f"  first {min(2, len(ids))} items:")
        for i, rid in enumerate(ids[:2]):
            doc = docs[i] if i < len(docs) else None
            meta = metas[i] if i < len(metas) else None
            print(f"    [{i}] id = {rid}")
            print(f"        metadata = {meta}")
            print(f"        document = {truncate(doc, 200)}")

        # Entities-specific: modal entity scan
        if cname.endswith("__entities"):
            print()
            print("  scanning for modal entities (entity_type in image/table/equation)...")
            try:
                all_items = coll.get(
                    include=["metadatas", "documents"],
                )
            except Exception as exc:
                print(f"  ERROR scanning entities: {exc!r}")
                failures.append(f"entities scan error: {exc!r}")
            else:
                a_ids = all_items.get("ids") or []
                a_docs = all_items.get("documents") or []
                a_metas = all_items.get("metadatas") or []
                modal_hits: list[tuple[str, dict, str]] = []
                for i, rid in enumerate(a_ids):
                    meta = a_metas[i] if i < len(a_metas) else None
                    doc = a_docs[i] if i < len(a_docs) else None
                    if meta and meta.get("entity_type") in MODAL_TYPES:
                        modal_hits.append((rid, meta, doc or ""))
                modal_entity_count = len(modal_hits)
                print(f"  modal entity count = {modal_entity_count}")
                if modal_hits:
                    rid0, meta0, doc0 = modal_hits[0]
                    print(f"    first modal entity:")
                    print(f"      id           = {rid0}")
                    print(f"      entity_name  = {meta0.get('entity_name')}")
                    print(f"      entity_type  = {meta0.get('entity_type')}")
                    print(f"      content(200) = {truncate(doc0, 200)}")
                else:
                    failures.append("no modal entities (image/table/equation) found")

        # Chunks-specific: count chunks whose file_path mentions the target pptx
        if cname.endswith("__chunks"):
            print()
            print(f"  scanning for chunks referencing {TARGET_PPTX}...")
            try:
                all_chunks = coll.get(include=["metadatas"])
            except Exception as exc:
                print(f"  ERROR scanning chunks: {exc!r}")
                failures.append(f"chunks scan error: {exc!r}")
            else:
                c_metas = all_chunks.get("metadatas") or []
                hits = 0
                sample_paths: set[str] = set()
                for meta in c_metas:
                    if not meta:
                        continue
                    fp = meta.get("file_path") or meta.get("file_url") or ""
                    if isinstance(fp, list):
                        fp_str = ",".join(str(x) for x in fp)
                    else:
                        fp_str = str(fp)
                    if TARGET_PPTX in fp_str:
                        hits += 1
                    if len(sample_paths) < 5 and fp_str:
                        sample_paths.add(fp_str)
                pptx_chunk_count = hits
                print(f"  chunks matching '{TARGET_PPTX}' = {hits}")
                if sample_paths:
                    print(f"  sample file_path values seen:")
                    for sp in sample_paths:
                        print(f"    - {truncate(sp, 200)}")
                if hits <= 0:
                    failures.append(f"no chunks link to {TARGET_PPTX}")
        print()

    # Verdict
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for cname in EXPECTED_COLLECTIONS:
        print(f"  {cname}: count={collection_counts.get(cname, 0)}")
    print(f"  modal_entity_count     = {modal_entity_count}")
    print(f"  pptx_chunk_count       = {pptx_chunk_count}")
    print()

    if failures:
        print("VERDICT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("VERDICT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
