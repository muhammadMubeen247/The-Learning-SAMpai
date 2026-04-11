"""
Compute Evaluation Metrics from Benchmark Raw Results

Reads current_system_raw.json (produced by run_benchmark.py) and computes:

Answer Quality  (pure math, no LLM judge)
  • ROUGE-L F1
  • BERTScore F1
  • Semantic Similarity (sentence-transformers cosine)

Retrieval Quality
  • Hit Rate @ 5
  • MRR  (Mean Reciprocal Rank)
  • Precision @ 5

System Performance
  • Avg / Median Latency (ms)
  • Avg Tokens per query
  • Avg / Total Cost (USD)

Usage (from backend/ directory):
    python -m app.evaluation.compute_metrics
"""

import json
import sys
from pathlib import Path
from typing import List

import numpy as np
from rouge_score import rouge_scorer
from bert_score import score as bert_score_fn
from sentence_transformers import SentenceTransformer

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"


def load_raw_results(filename: str = "current_system_raw.json") -> dict:
    path = RESULTS_DIR / filename
    if not path.exists():
        print(f"ERROR: {path} not found. Run run_benchmark.py first.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Answer-quality metrics
# ------------------------------------------------------------------

def _rouge_l_scores(generated: List[str], references: List[str]) -> List[float]:
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    return [
        scorer.score(ref, gen)["rougeL"].fmeasure
        for gen, ref in zip(generated, references)
    ]


def _bert_scores(generated: List[str], references: List[str]) -> List[float]:
    _, _, F1 = bert_score_fn(generated, references, lang="en", verbose=True)
    return F1.tolist()


def _semantic_similarity(generated: List[str], references: List[str]) -> List[float]:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    gen_emb = model.encode(generated, show_progress_bar=False)
    ref_emb = model.encode(references, show_progress_bar=False)
    sims = []
    for g, r in zip(gen_emb, ref_emb):
        cos = float(np.dot(g, r) / (np.linalg.norm(g) * np.linalg.norm(r) + 1e-10))
        sims.append(cos)
    return sims


# ------------------------------------------------------------------
# Retrieval-quality metrics
# ------------------------------------------------------------------

def _hit_rate(results: list, k: int = 5) -> List[int]:
    hits = []
    for r in results:
        relevant = r["relevant_page"]
        pages = [c.get("page_number") for c in r["retrieved_chunks"][:k]]
        hits.append(1 if relevant in pages else 0)
    return hits


def _mrr(results: list) -> List[float]:
    rrs = []
    for r in results:
        relevant = r["relevant_page"]
        rr = 0.0
        for rank, chunk in enumerate(r["retrieved_chunks"], start=1):
            if chunk.get("page_number") == relevant:
                rr = 1.0 / rank
                break
        rrs.append(rr)
    return rrs


def _precision_at_k(results: list, k: int = 5) -> List[float]:
    precs = []
    for r in results:
        relevant = r["relevant_page"]
        pages = [c.get("page_number") for c in r["retrieved_chunks"][:k]]
        precs.append(sum(1 for p in pages if p == relevant) / k)
    return precs


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def compute_metrics(raw_file: str = "current_system_raw.json"):
    data = load_raw_results(raw_file)
    results = data["results"]
    info = data["benchmark_info"]

    # Filter out questions where the RAG pipeline failed
    valid = [r for r in results if r["generated_answer"]]
    if not valid:
        print("ERROR: No valid answers found — cannot compute metrics.")
        sys.exit(1)

    generated = [r["generated_answer"] for r in valid]
    references = [r["ground_truth"] for r in valid]

    print()
    print("=" * 64)
    print("  COMPUTING METRICS")
    print("=" * 64)
    print(f"  System    : {info['system']}")
    print(f"  Document  : {info['document']}")
    print(f"  Questions : {info['total_questions']}  (valid answers: {len(valid)})")
    print("=" * 64)
    print()

    # ── Answer quality ────────────────────────────────────────────
    print("[1/6] ROUGE-L …")
    rouge = _rouge_l_scores(generated, references)

    print("[2/6] BERTScore …")
    bert = _bert_scores(generated, references)

    print("[3/6] Semantic Similarity …")
    semsim = _semantic_similarity(generated, references)

    # ── Retrieval quality ─────────────────────────────────────────
    print("[4/6] Hit Rate @ 5 …")
    hr = _hit_rate(results)

    print("[5/6] MRR …")
    mrr = _mrr(results)

    print("[6/6] Precision @ 5 …")
    prec = _precision_at_k(results)

    # ── System performance (already captured in raw results) ──────
    latencies = [r["rag_latency_ms"] for r in results]
    tokens = [r["total_estimated_tokens"] for r in results]
    costs = [r["estimated_cost_usd"] for r in results]

    # ── Assemble metrics dict ─────────────────────────────────────
    metrics = {
        "benchmark_info": info,
        "answer_quality": {
            "rouge_l": {
                "mean": round(float(np.mean(rouge)), 4),
                "std": round(float(np.std(rouge)), 4),
                "per_question": [round(v, 4) for v in rouge],
            },
            "bert_score_f1": {
                "mean": round(float(np.mean(bert)), 4),
                "std": round(float(np.std(bert)), 4),
                "per_question": [round(v, 4) for v in bert],
            },
            "semantic_similarity": {
                "mean": round(float(np.mean(semsim)), 4),
                "std": round(float(np.std(semsim)), 4),
                "per_question": [round(v, 4) for v in semsim],
            },
        },
        "retrieval_quality": {
            "hit_rate_at_5": {
                "mean": round(float(np.mean(hr)), 4),
                "per_question": hr,
            },
            "mrr": {
                "mean": round(float(np.mean(mrr)), 4),
                "per_question": [round(v, 4) for v in mrr],
            },
            "precision_at_5": {
                "mean": round(float(np.mean(prec)), 4),
                "per_question": [round(v, 4) for v in prec],
            },
        },
        "system_performance": {
            "avg_latency_ms": round(float(np.mean(latencies)), 2),
            "median_latency_ms": round(float(np.median(latencies)), 2),
            "avg_tokens_per_query": round(float(np.mean(tokens)), 1),
            "avg_cost_per_query_usd": round(float(np.mean(costs)), 6),
            "total_cost_usd": round(float(sum(costs)), 6),
        },
    }

    # ── Print summary table ───────────────────────────────────────
    aq = metrics["answer_quality"]
    rq = metrics["retrieval_quality"]
    sp = metrics["system_performance"]

    print()
    print("=" * 64)
    print("  BENCHMARK RESULTS")
    print("=" * 64)
    print(f"  System : {info['system']}")
    print(f"  Model  : {info['model']}  |  Temp: {info['temperature']}  |  top_k: {info['top_k']}")
    print(f"  Qs     : {info['total_questions']}  |  Valid: {len(valid)}")
    print("-" * 64)
    print("  ANSWER QUALITY                   Mean      Std")
    print(f"    ROUGE-L F1               {aq['rouge_l']['mean']:>8.4f}   {aq['rouge_l']['std']:>7.4f}")
    print(f"    BERTScore F1             {aq['bert_score_f1']['mean']:>8.4f}   {aq['bert_score_f1']['std']:>7.4f}")
    print(f"    Semantic Similarity      {aq['semantic_similarity']['mean']:>8.4f}   {aq['semantic_similarity']['std']:>7.4f}")
    print("-" * 64)
    print("  RETRIEVAL QUALITY                Mean")
    print(f"    Hit Rate @ 5             {rq['hit_rate_at_5']['mean']:>8.4f}")
    print(f"    MRR                      {rq['mrr']['mean']:>8.4f}")
    print(f"    Precision @ 5            {rq['precision_at_5']['mean']:>8.4f}")
    print("-" * 64)
    print("  SYSTEM PERFORMANCE")
    print(f"    Avg Latency              {sp['avg_latency_ms']:>8.0f} ms")
    print(f"    Median Latency           {sp['median_latency_ms']:>8.0f} ms")
    print(f"    Avg Tokens / Query       {sp['avg_tokens_per_query']:>8.0f}")
    print(f"    Avg Cost / Query         ${sp['avg_cost_per_query_usd']:.6f}")
    print(f"    Total Cost               ${sp['total_cost_usd']:.6f}")
    print("=" * 64)

    # ── Save ──────────────────────────────────────────────────────
    system_tag = info["system"]  # e.g. "current_langchain_chromadb"
    out_path = RESULTS_DIR / f"{system_tag}_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"\n  Metrics saved to: {out_path}")


if __name__ == "__main__":
    compute_metrics()
