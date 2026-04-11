"""
RAG Benchmark Runner — Current System (LangChain + ChromaDB)

Runs each ground-truth question through the existing RAG pipeline,
captures answers, retrieved chunks, latency, and token usage.

Usage (from backend/ directory):
    # If running locally against Docker DB on port 5433:
    set BENCHMARK_LOCAL=true
    python -m app.evaluation.run_benchmark

    # If running inside Docker container:
    set BENCHMARK_LOCAL=false
    python -m app.evaluation.run_benchmark
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Environment setup — MUST happen before importing app modules
# ---------------------------------------------------------------------------
# Set DB and ChromaDB BEFORE load_dotenv so override=False won't overwrite them
# When running locally, point DB at localhost:5433 (Docker-exposed port)
if os.getenv("BENCHMARK_LOCAL", "true").lower() == "true":
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg://postgres:password@localhost:5433/Learning_SAMpai_db"
    )

# ChromaDB path — local mount
os.environ.setdefault(
    "CHROMA_DATA_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "chroma_data"),
)

# Load .env.docker for OpenAI key, R2, etc.
# override=False preserves DATABASE_URL and CHROMA_DATA_DIR set above
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent.parent.parent  # The Learning SAMpai v2/
_env_docker = _project_root / ".env.docker"
if _env_docker.exists():
    load_dotenv(_env_docker, override=False)

# ---------------------------------------------------------------------------
# Now safe to import app modules (they read env on import)
# ---------------------------------------------------------------------------
from app.services.langchain_vector_store import langchain_vector_store
from app.services.langchain_rag_service import langchain_rag_service
from app.services.chat_service import delete_chat_history
from app.database.session import SessionLocal
from app.models.user import User
from app.utils.token_counter import count_tokens, estimate_chat_cost


def load_ground_truth() -> dict:
    gt_path = Path(__file__).parent / "ground_truth.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_benchmark_user(db):
    """Return the first available user in the database."""
    user = db.query(User).first()
    if not user:
        raise RuntimeError(
            "No users found in the database. "
            "Sign up through the app first, then re-run."
        )
    return user


def run_benchmark():
    gt = load_ground_truth()
    metadata = gt["metadata"]
    questions = gt["questions"]

    classroom_id = metadata["classroom_id"]
    file_id = metadata["file_id"]

    print("=" * 64)
    print("  RAG BENCHMARK — Current System (LangChain + ChromaDB)")
    print("=" * 64)
    print(f"  Document  : {metadata['document_name']}")
    print(f"  Classroom : {classroom_id}  |  File : {file_id}")
    print(f"  Questions : {len(questions)}")
    print("=" * 64)
    print()

    db = SessionLocal()
    try:
        user = get_benchmark_user(db)
        print(f"Using user: {user.username} (id={user.id})\n")

        results = []

        for idx, q in enumerate(questions, start=1):
            qid = q["id"]
            question = q["question"]
            topic_id = q["topic_id"]

            print(f"[{idx}/{len(questions)}] Q{qid}: {question}")

            # ── 1. Retrieval (direct vector search) ──────────────────
            retrieval_start = time.perf_counter()
            try:
                retrieved_chunks = langchain_vector_store.search_similar_chunks(
                    classroom_id=classroom_id,
                    query=question,
                    file_id=file_id,
                    top_k=5,
                )
            except Exception as e:
                print(f"  ⚠ Retrieval error: {e}")
                retrieved_chunks = []
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

            # ── 2. Clear chat history for a clean, independent eval ──
            try:
                delete_chat_history(db=db, topic_id=topic_id, user_id=user.id)
            except Exception:
                pass

            # ── 3. Full RAG pipeline ─────────────────────────────────
            rag_start = time.perf_counter()
            try:
                rag_result = langchain_rag_service.ask_question(
                    classroom_id=classroom_id,
                    topic_id=topic_id,
                    user_id=user.id,
                    question=question,
                    db=db,
                    file_id=file_id,
                )
                answer = rag_result["answer"]
                sources = rag_result["sources"]
                confidence = rag_result["confidence"]
                chunks_used = rag_result["chunks_used"]
            except Exception as e:
                print(f"  ⚠ RAG error: {e}")
                answer = ""
                sources = []
                confidence = "error"
                chunks_used = 0
            rag_ms = (time.perf_counter() - rag_start) * 1000

            # ── 4. Token counting ────────────────────────────────────
            question_tokens = count_tokens(question)
            answer_tokens = count_tokens(answer) if answer else 0
            context_tokens = sum(
                count_tokens(c.get("content", "")) for c in retrieved_chunks
            )
            total_tokens = question_tokens + answer_tokens + context_tokens
            cost_usd = estimate_chat_cost(
                prompt_tokens=question_tokens + context_tokens,
                completion_tokens=answer_tokens,
                model="gpt-3.5-turbo",
            )

            # ── 5. Compile result ────────────────────────────────────
            result = {
                "question_id": qid,
                "question": question,
                "ground_truth": q["ground_truth"],
                "relevant_page": q["relevant_page"],
                "topic_id": topic_id,
                "category": q["category"],
                "generated_answer": answer,
                "confidence": confidence,
                "chunks_used": chunks_used,
                "sources": sources,
                "retrieved_chunks": [
                    {
                        "id": c.get("id", ""),
                        "content": c.get("content", ""),
                        "page_number": c.get("metadata", {}).get("page_number"),
                        "chunk_index": c.get("metadata", {}).get("chunk_index"),
                        "distance": c.get("distance"),
                    }
                    for c in retrieved_chunks
                ],
                "retrieval_latency_ms": round(retrieval_ms, 2),
                "rag_latency_ms": round(rag_ms, 2),
                "question_tokens": question_tokens,
                "answer_tokens": answer_tokens,
                "context_tokens": context_tokens,
                "total_estimated_tokens": total_tokens,
                "estimated_cost_usd": round(cost_usd, 6),
            }
            results.append(result)

            # Brief console feedback
            preview = (answer[:75] + "...") if len(answer) > 75 else answer
            print(f"  → {preview}")
            print(
                f"  Latency: {rag_ms:.0f}ms  |  "
                f"Tokens: {total_tokens}  |  "
                f"Cost: ${cost_usd:.6f}"
            )
            print()

        # ── Save raw results ─────────────────────────────────────────
        results_dir = Path(__file__).parent / "results"
        results_dir.mkdir(exist_ok=True)

        output = {
            "benchmark_info": {
                "system": "current_langchain_chromadb",
                "timestamp": datetime.now().isoformat(),
                "document": metadata["document_name"],
                "classroom_id": classroom_id,
                "file_id": file_id,
                "total_questions": len(questions),
                "model": "gpt-3.5-turbo",
                "temperature": 0.2,
                "top_k": 5,
            },
            "results": results,
        }

        output_path = results_dir / "current_system_raw.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print("=" * 64)
        print(f"  Benchmark complete — {len(results)} questions processed")
        print(f"  Raw results saved to: {output_path}")
        print("=" * 64)

    finally:
        db.close()


if __name__ == "__main__":
    run_benchmark()
