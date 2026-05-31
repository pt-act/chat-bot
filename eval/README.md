# RAGAS evaluation harness

Offline, on-demand evaluation of retrieval and answer quality with
[RAGAS](https://docs.ragas.io). This is **deliberately not part of CI**: RAGAS judges
answers with an LLM (plus embeddings), which requires network access and an API key
and is non-deterministic — the opposite of the hermetic unit/contract suite.

## What it measures

| Metric | Question it answers |
|--------|---------------------|
| `faithfulness` | Is the answer grounded in the retrieved context (no hallucination)? |
| `answer_relevancy` | Does the answer actually address the question? |
| `context_precision` | Are the retrieved chunks relevant (signal vs. noise)? |
| `context_recall` | Did retrieval surface the information needed for the ground truth? |

## Prerequisites

1. A **populated vector store** — ingest your policy PDFs first so retrieval has
   something to return. The bundled `golden.jsonl` matches the sample return/shipping/
   privacy policy used in the test fixtures.
2. **LLM + embeddings configured** for both the app (to generate answers) and RAGAS
   (to judge them). RAGAS uses OpenAI by default, so set `OPENAI_API_KEY`.

## Dataset format

`golden.jsonl` — one JSON object per line:

```json
{"question": "How many days do I have to return an item?", "ground_truth": "Customers may return any item within 30 days..."}
```

## Run it

Live mode (generates answers through the real retrieval + generation path, then scores):

```bash
OPENAI_API_KEY=sk-... \
  uv run --with-requirements requirements-eval.txt eval/run_ragas.py \
  --dataset eval/golden.jsonl --output eval/report.json
```

Score mode (skip generation; score precomputed records — e.g. captured production
traffic — with fields `{question, answer, contexts[], ground_truth}`):

```bash
uv run --with-requirements requirements-eval.txt eval/run_ragas.py \
  --mode score --answers my_answers.jsonl
```

Options: `--generate-mode {strict,open,learning}` (default `open`), `--output` to write
a JSON report.

## Notes

- Scores depend on your corpus, chunking, `top_k`, and embedding model — treat them as
  a regression signal across changes, not an absolute grade.
- To gate changes, capture a baseline `report.json`, then compare after tuning
  retrieval. Wiring this into a scheduled (non-PR) CI job is a future option.
