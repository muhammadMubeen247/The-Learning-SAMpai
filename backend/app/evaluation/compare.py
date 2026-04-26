"""
Print a side-by-side comparison table: LangChain + ChromaDB vs LightRAG + Neo4j.

Usage (from backend/):
    # Preferred — old metrics as a JSON file:
    .venv\\Scripts\\python.exe app/evaluation/compare.py \\
        --new app/evaluation/results/lightrag_metrics.json \\
        --old app/evaluation/results/old_metrics.json

    # Alternative — old metrics as an inline JSON string:
    .venv\\Scripts\\python.exe app/evaluation/compare.py \\
        --new app/evaluation/results/lightrag_metrics.json \\
        --old-values '{\"rouge_l\": 0.28, \"bertscore_f1\": 0.82, ...}'
"""
import argparse
import json
import pathlib
import sys

NA = "N/A *"


def _flt(v, d: int = 4) -> str:
    return NA if v is None else f"{float(v):.{d}f}"


def _int(v) -> str:
    return NA if v is None else str(int(float(v)))


def _cost(v) -> str:
    return NA if v is None else f"${float(v):.4f}"


def _get(d: dict, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _load_new(path: str) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"New metrics file not found: {p}")
    with open(p) as f:
        return json.load(f)


def _load_old(path: str | None, values_str: str | None) -> dict:
    if path:
        p = pathlib.Path(path)
        if not p.exists():
            sys.exit(f"Old metrics file not found: {p}")
        with open(p) as f:
            return json.load(f)
    if values_str:
        try:
            return json.loads(values_str)
        except json.JSONDecodeError as exc:
            sys.exit(f"--old-values is not valid JSON: {exc}")
    return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new", required=True, help="Path to lightrag_metrics.json")
    parser.add_argument("--old", default=None, help="Path to old system metrics JSON")
    parser.add_argument(
        "--old-values",
        default=None,
        help='Inline JSON string of old metrics, e.g. \'{"rouge_l": 0.28, ...}\'',
    )
    args = parser.parse_args()

    if not args.old and not args.old_values:
        sys.exit("Provide --old <file> or --old-values '<json>'")

    new = _load_new(args.new)
    old = _load_old(args.old, args.old_values)

    rows = [
        (
            "ROUGE-L F1",
            _flt(_get(old, "rouge_l")),
            _flt(_get(new, "rouge_l")),
        ),
        (
            "BERTScore F1",
            _flt(_get(old, "bertscore", "bertscore_f1")),
            _flt(_get(new, "bertscore_f1")),
        ),
        (
            "Semantic Similarity",
            _flt(_get(old, "semantic_sim", "semantic_similarity")),
            _flt(_get(new, "semantic_sim")),
        ),
        (
            "Avg Latency (s)",
            _flt(_get(old, "avg_latency", "avg_latency_s"), d=3),
            _flt(_get(new, "avg_latency_s"), d=3),
        ),
        (
            "Avg Output Tokens",
            _int(_get(old, "avg_output_tokens")),
            _int(_get(new, "avg_output_tokens")),
        ),
        (
            "Estimated Cost (40 Qs)",
            _cost(_get(old, "cost", "total_cost_usd", "total_cost_usd_estimated")),
            _cost(_get(new, "total_cost_usd_estimated")),
        ),
        (
            "Hit Rate@5",
            _flt(_get(old, "hit_rate", "hit_rate_at_5")),
            NA,
        ),
        (
            "MRR",
            _flt(_get(old, "mrr")),
            NA,
        ),
        (
            "Precision@5",
            _flt(_get(old, "precision", "precision_at_5")),
            NA,
        ),
    ]

    c0 = max(len(r[0]) for r in rows) + 2
    c1 = max(len("LangChain + ChromaDB"), max(len(r[1]) for r in rows)) + 2
    c2 = max(len("LightRAG (Naive)"), max(len(r[2]) for r in rows)) + 2

    header = f"{'Metric':<{c0}} | {'LangChain + ChromaDB':>{c1}} | {'LightRAG (Naive)':>{c2}}"
    sep = f"{'-' * c0}-+-{'-' * c1}-+-{'-' * c2}"

    print(header)
    print(sep)
    for label, old_v, new_v in rows:
        print(f"{label:<{c0}} | {old_v:>{c1}} | {new_v:>{c2}}")

    print()
    print("* Retrieval attribution metrics not applicable for the new system.")
    print(
        "  LightRAG naive mode does not expose chunk-level page provenance."
    )
    print("  The new system returns file-level citations (R2 URLs) only.")


if __name__ == "__main__":
    main()
