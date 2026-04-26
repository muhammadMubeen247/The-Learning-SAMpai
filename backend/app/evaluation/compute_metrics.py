"""
Compute 6 evaluation metrics from lightrag_raw.json.

Batches BERTScore and SentenceTransformer calls for efficiency.
Writes two output files:
  results/{system}_metrics.json            — overall averages + by-category
  results/{system}_metrics_per_question.json — per-question breakdown

Usage (from backend/):
    .venv\\Scripts\\python.exe app/evaluation/compute_metrics.py \\
        --input app/evaluation/results/lightrag_raw.json \\
        --system lightrag
"""
import argparse
import json
import pathlib
import sys

RESULTS_DIR = pathlib.Path(__file__).parent / "results"

GPT4O_OUTPUT_PER_TOKEN = 15.0 / 1_000_000   # $15 / 1M output tokens
GPT4O_INPUT_PER_TOKEN = 5.0 / 1_000_000     # $5 / 1M input tokens
INPUT_MULTIPLIER = 10  # LightRAG builds large context; input ≈ 10× output


def _rouge(preds: list[str], refs: list[str]) -> list[float]:
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    return [scorer.score(r, p)["rougeL"].fmeasure for p, r in zip(preds, refs)]


def _bertscore(preds: list[str], refs: list[str]) -> list[float]:
    from bert_score import BERTScorer

    scorer = BERTScorer(
        model_type="distilbert-base-uncased",
        lang="en",
        rescale_with_baseline=False,
    )
    _, _, f1 = scorer.score(preds, refs)
    return f1.tolist()


def _semantic_sim(preds: list[str], refs: list[str]) -> list[float]:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    all_embs = model.encode(preds + refs, batch_size=32, show_progress_bar=False)
    pred_embs = all_embs[: len(preds)]
    ref_embs = all_embs[len(preds) :]

    sims = []
    for p, r in zip(pred_embs, ref_embs):
        dot = float(np.dot(p, r))
        norm = float(np.linalg.norm(p) * np.linalg.norm(r))
        sims.append(dot / norm if norm > 1e-8 else 0.0)
    return sims


def _avg(xs: list) -> float:
    return sum(float(x) for x in xs) / len(xs) if xs else 0.0


def _by_category(per_q: list[dict]) -> dict:
    groups: dict[str, list] = {}
    for r in per_q:
        groups.setdefault(r.get("category", "unknown"), []).append(r)
    return {
        cat: {
            "n": len(items),
            "rouge_l": round(_avg([i["rouge_l"] for i in items]), 4),
            "bertscore_f1": round(_avg([i["bertscore_f1"] for i in items]), 4),
            "semantic_sim": round(_avg([i["semantic_sim"] for i in items]), 4),
            "avg_latency_s": round(_avg([i["latency_s"] for i in items]), 3),
            "avg_output_tokens": round(_avg([i["output_tokens"] for i in items])),
        }
        for cat, items in groups.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to lightrag_raw.json")
    parser.add_argument("--system", default="lightrag", help="Tag for output filenames")
    args = parser.parse_args()

    raw_path = pathlib.Path(args.input)
    if not raw_path.exists():
        sys.exit(f"Input not found: {raw_path}")

    with open(raw_path) as f:
        data = json.load(f)

    results = data["results"]
    if not results:
        sys.exit("No results in input file.")

    # Replace empty answers with a single space so scorers don't crash;
    # they score as ~0 which correctly penalises the system.
    preds = [r["generated_answer"].strip() or " " for r in results]
    refs = [r["ground_truth"] for r in results]

    print(f"Computing metrics for {len(results)} questions...")
    print("  ROUGE-L...")
    rouge = _rouge(preds, refs)

    print("  BERTScore (distilbert-base-uncased)...")
    bert = _bertscore(preds, refs)

    print("  Semantic Similarity (all-MiniLM-L6-v2)...")
    sem = _semantic_sim(preds, refs)

    per_q = []
    for i, r in enumerate(results):
        out_tok = r["output_tokens"]
        in_tok_est = out_tok * INPUT_MULTIPLIER
        cost = out_tok * GPT4O_OUTPUT_PER_TOKEN + in_tok_est * GPT4O_INPUT_PER_TOKEN
        per_q.append(
            {
                "id": r["id"],
                "category": r["category"],
                "question": r["question"],
                "generated_answer": r["generated_answer"],
                "ground_truth": r["ground_truth"],
                "rouge_l": round(float(rouge[i]), 4),
                "bertscore_f1": round(float(bert[i]), 4),
                "semantic_sim": round(float(sem[i]), 4),
                "latency_s": r["latency_s"],
                "output_tokens": r["output_tokens"],
                "cost_usd": round(cost, 6),
                "empty_answer": r.get("empty_answer", False),
            }
        )

    n = len(per_q)
    total_out = sum(r["output_tokens"] for r in per_q)
    total_cost = sum(r["cost_usd"] for r in per_q)

    summary = {
        "system": args.system,
        "n_questions": n,
        "rouge_l": round(_avg(rouge), 4),
        "bertscore_f1": round(_avg(bert), 4),
        "semantic_sim": round(_avg(sem), 4),
        "avg_latency_s": round(_avg([r["latency_s"] for r in results]), 3),
        "avg_output_tokens": round(total_out / n),
        "total_output_tokens": total_out,
        "total_input_tokens_estimated": total_out * INPUT_MULTIPLIER,
        "total_cost_usd_estimated": round(total_cost, 4),
        "cost_note": (
            f"Input tokens estimated as {INPUT_MULTIPLIER}× output. "
            "GPT-4o pricing: $5/1M input, $15/1M output."
        ),
        "by_category": _by_category(per_q),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = RESULTS_DIR / f"{args.system}_metrics.json"
    per_q_path = RESULTS_DIR / f"{args.system}_metrics_per_question.json"

    with open(metrics_path, "w") as f:
        json.dump(summary, f, indent=2)
    with open(per_q_path, "w") as f:
        json.dump(per_q, f, indent=2)

    w = 26
    print(f"\n{'=' * 60}")
    print(f"  {args.system.upper()} — {n} questions")
    print(f"{'=' * 60}")
    print(f"  {'ROUGE-L F1':<{w}} {summary['rouge_l']:.4f}")
    print(f"  {'BERTScore F1':<{w}} {summary['bertscore_f1']:.4f}")
    print(f"  {'Semantic Similarity':<{w}} {summary['semantic_sim']:.4f}")
    print(f"  {'Avg Latency (s)':<{w}} {summary['avg_latency_s']:.3f}")
    print(f"  {'Avg Output Tokens':<{w}} {summary['avg_output_tokens']}")
    print(f"  {'Est. Cost (all Qs)':<{w}} ${summary['total_cost_usd_estimated']:.4f}")
    print(f"  {'Cost note':<{w}} {summary['cost_note']}")
    print(f"\n  By category:")
    for cat, vals in summary["by_category"].items():
        print(
            f"    {cat:<14} ROUGE={vals['rouge_l']:.4f}  "
            f"BERT={vals['bertscore_f1']:.4f}  "
            f"SemSim={vals['semantic_sim']:.4f}"
        )
    print(f"\n  Saved: {metrics_path}")
    print(f"  Saved: {per_q_path}")


if __name__ == "__main__":
    main()
