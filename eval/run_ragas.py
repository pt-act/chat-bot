#!/usr/bin/env python
"""Offline RAGAS evaluation harness for the RAG pipeline.

This is a standalone tool — it is intentionally NOT part of the hermetic CI suite,
because RAGAS judges answers with an LLM (and embeddings), which needs network access
and an API key, and is non-deterministic.

Two modes:

  live   (default) — for each question in the dataset, run the real retrieval +
                     generation path to produce an answer and its retrieved contexts,
                     then score with RAGAS. Requires a populated Chroma collection
                     (ingest your policy PDFs first) and configured LLM/embeddings.

  score            — skip generation; read precomputed records
                     ({question, answer, contexts[], ground_truth}) from --answers
                     and only compute RAGAS metrics. Useful for scoring captured
                     production traffic.

Metrics: faithfulness, answer_relevancy, context_precision, context_recall.

Usage:
    uv run --with-requirements requirements-eval.txt eval/run_ragas.py
    uv run --with-requirements requirements-eval.txt eval/run_ragas.py --mode score --answers answers.jsonl
    OPENAI_API_KEY=sk-... uv run --with-requirements requirements-eval.txt eval/run_ragas.py --output eval/report.json

See eval/README.md for details.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _answer_and_contexts(question: str, mode: str) -> tuple[str, list[str]]:
    """Run retrieval + generation without the memory/Redis layer (eval-only path)."""
    from graph.nodes.retrieve_context import retrieve_context
    from prompts.answer import build_answer_prompt
    from utils.llm_adapter import get_llm

    state = retrieve_context({"question": question, "chat_mode": mode})
    docs = state.get("docs", "") or ""
    contexts = [c for c in docs.split("\n\n") if c.strip()] or [""]

    prompt = build_answer_prompt(summary="", history="", docs=docs, question=question, lang="English", chat_mode=mode)
    answer = get_llm(temperature=0, max_tokens=512).invoke(prompt).content
    return answer, contexts


def _build_records(dataset: list[dict], mode: str, generate_mode: str) -> list[dict]:
    if mode == "score":
        for r in dataset:
            r.setdefault("contexts", [])
        return dataset

    records = []
    for row in dataset:
        question = row["question"]
        print(f"  • generating: {question!r}")
        answer, contexts = _answer_and_contexts(question, generate_mode)
        records.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": row.get("ground_truth", ""),
            }
        )
    return records


def _evaluate(records: list[dict]) -> dict:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError:
        print(
            "RAGAS is not installed. Install the eval extras:\n"
            "  uv run --with-requirements requirements-eval.txt eval/run_ragas.py\n"
            "or: pip install -r requirements-eval.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    ds = Dataset.from_dict(
        {
            "question": [r["question"] for r in records],
            "answer": [r["answer"] for r in records],
            "contexts": [r["contexts"] for r in records],
            "ground_truth": [r["ground_truth"] for r in records],
        }
    )
    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    # RAGAS returns a Result object; coerce to a plain {metric: float} dict.
    try:
        return {k: float(v) for k, v in dict(result).items()}
    except Exception:  # pragma: no cover - version differences
        return {"raw": str(result)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation on the RAG pipeline.")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "golden.jsonl")
    parser.add_argument("--mode", choices=["live", "score"], default="live")
    parser.add_argument("--answers", type=Path, help="Precomputed records (required for --mode score).")
    parser.add_argument("--output", type=Path, help="Write the metrics report as JSON here.")
    parser.add_argument(
        "--generate-mode",
        choices=["strict", "open", "learning", "learning_review"],
        default="open",
        help="Chat mode used when generating answers in live mode (open recommended for eval coverage).",
    )
    args = parser.parse_args()

    if args.mode == "score":
        if not args.answers:
            parser.error("--answers is required when --mode score")
        dataset = _load_jsonl(args.answers)
    else:
        dataset = _load_jsonl(args.dataset)
        if "OPENAI_API_KEY" not in os.environ and not os.environ.get("RAGAS_DISABLE_KEY_CHECK"):
            print(
                "Warning: OPENAI_API_KEY is not set. RAGAS uses OpenAI by default to judge "
                "answers; set it (or configure RAGAS) before running.",
                file=sys.stderr,
            )

    print(f"Preparing {len(dataset)} records (mode={args.mode})...")
    records = _build_records(dataset, args.mode, args.generate_mode)

    print("Scoring with RAGAS (this calls the judge LLM)...")
    scores = _evaluate(records)

    print("\n=== RAGAS scores ===")
    for metric, value in scores.items():
        print(f"  {metric:20s} {value:.4f}" if isinstance(value, float) else f"  {metric}: {value}")

    if args.output:
        args.output.write_text(json.dumps({"scores": scores, "n": len(records)}, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
