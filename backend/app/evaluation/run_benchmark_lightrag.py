"""
Run the LightRAG benchmark: ask all 30 ground-truth questions through the
classroom engine and save raw answers + latency to results/lightrag_raw.json.

Usage (from backend/):
    .venv\\Scripts\\python.exe app/evaluation/run_benchmark_lightrag.py \\
        --classroom-id 3 \\
        --file-url "https://..." \\
        [--resume]
"""
# ── sys.path fix: add backend/ so 'app' package is importable ──────────────
import sys
import pathlib as _pl

_backend_dir = _pl.Path(__file__).resolve().parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# ── Bootstrap: patches NumPy aliases + sets service URLs + loads .env.docker ─
# Must run before any app.* import (chromadb is imported transitively).
import app.evaluation._bootstrap  # noqa: F401

# ── Standard imports ─────────────────────────────────────────────────────────
import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import tiktoken
from tqdm import tqdm

from app.evaluation.preflight import run_all as run_preflight

RESULTS_DIR = _pl.Path(__file__).parent / "results"
OUTPUT_FILE = RESULTS_DIR / "lightrag_raw.json"
GT_FILE = _pl.Path(__file__).parent / "ground_truth.json"


def _load_questions() -> list[dict]:
    with open(GT_FILE) as f:
        data = json.load(f)
    questions = data["questions"]
    required = {"id", "question", "ground_truth", "category"}
    for q in questions:
        missing = required - q.keys()
        if missing:
            raise ValueError(f"Q{q.get('id')} missing fields: {missing}")
    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question IDs in ground_truth.json")
    return questions


def _load_partial(classroom_id: int, file_url: str) -> tuple[dict, set[int]]:
    """Return (existing_doc, set_of_completed_ids) if a matching run exists."""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            doc = json.load(f)
        info = doc.get("benchmark_info", {})
        if info.get("classroom_id") == classroom_id and info.get("file_url") == file_url:
            return doc, {r["id"] for r in doc.get("results", [])}
    return {}, set()


def _save(doc: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
    tmp.replace(OUTPUT_FILE)


async def main() -> None:
    parser = argparse.ArgumentParser(description="LightRAG benchmark runner")
    parser.add_argument("--classroom-id", type=int, required=True)
    parser.add_argument("--file-url", type=str, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip questions already saved in the output file.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    for _log in ("app.rag", "app.services", "httpx", "neo4j", "chromadb", "openai"):
        logging.getLogger(_log).setLevel(logging.WARNING)

    await run_preflight(args.classroom_id, args.file_url)

    questions = _load_questions()
    enc = tiktoken.get_encoding("cl100k_base")

    partial_doc, done_ids = _load_partial(args.classroom_id, args.file_url)
    if args.resume and done_ids:
        print(f"[resume] Skipping {len(done_ids)} already-completed question(s).")
        output_doc = partial_doc
    else:
        done_ids = set()
        output_doc = {
            "benchmark_info": {
                "system": "lightrag_naive",
                "classroom_id": args.classroom_id,
                "file_url": args.file_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "results": [],
        }

    from app.services.classroom_rag import classroom_rag_service
    from app.rag.base import QueryParam

    print("Initializing LightRAG engine (first call may take a few seconds)...")
    engine = await classroom_rag_service.get_engine(args.classroom_id)

    pending = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(pending)} question(s)...\n")

    for q in tqdm(pending, unit="q", ncols=80):
        param = QueryParam(
            mode="naive",
            chunk_top_k=20,
            conversation_history=[],
            file_filter=args.file_url,
        )
        try:
            t0 = time.perf_counter()
            result = await engine.aquery(q["question"], param)
            latency = time.perf_counter() - t0
            answer = result.content or ""
        except Exception as exc:
            tqdm.write(f"  [ERROR] Q{q['id']}: {exc}")
            answer = ""
            latency = 0.0

        output_doc["results"].append(
            {
                "id": q["id"],
                "question": q["question"],
                "ground_truth": q["ground_truth"],
                "generated_answer": answer,
                "latency_s": round(latency, 3),
                "output_tokens": len(enc.encode(answer)),
                "category": q["category"],
                "empty_answer": not answer.strip(),
            }
        )
        _save(output_doc)  # incremental save after every question

    print("\nShutting down engine...")
    await classroom_rag_service.finalize_all()
    from app.rag.storage.postgres_kv import close_pool

    await close_pool()

    n_total = len(output_doc["results"])
    n_empty = sum(1 for r in output_doc["results"] if r.get("empty_answer"))
    print(
        f"Done. {n_total} total answers ({n_empty} empty). "
        f"Saved to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    asyncio.run(main())
