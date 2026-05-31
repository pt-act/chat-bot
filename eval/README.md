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

1. A **populated vector store** — ingest your policy documents first (PDF/TXT/MD/DOCX/HTML,
   via URL or local upload) so retrieval has something to return. The bundled `golden.jsonl`
   matches the sample return/shipping/privacy policy used in the test fixtures.
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

## Seeding a corpus

`eval/seed_corpus.py` ingests every supported document under `eval/corpus/` (override with
`EVAL_CORPUS_DIR`) through the real ingest pipeline, falling back to a small built-in policy
when no corpus files are present:

```bash
EVAL_CORPUS_DIR=eval/corpus \
  uv run --with-requirements requirements.txt eval/seed_corpus.py
```

## Opt-in CI (`.github/workflows/eval.yml`)

A **non-PR** workflow runs this harness on demand (`workflow_dispatch`) and weekly
(`schedule`). It spins up Redis, seeds the corpus, runs `run_ragas.py --mode live`,
uploads `report.json` as an artifact, and applies conservative metric floors
(`faithfulness`/`answer_relevancy`) as an optional gate. It needs an `OPENAI_API_KEY`
repo secret for the judge. The PR pipeline (`ci.yml`) stays hermetic and never runs RAGAS.

For a fast, fully-hermetic guard that *does* run on every PR, see
`tests/test_retrieval_regression.py` (marked `@pytest.mark.retrieval`): it seeds a tiny
labeled corpus with the real FastEmbed model and asserts recall@k + a score floor, so
retrieval quality cannot silently regress.

## Notes

- Scores depend on your corpus, chunking, `top_k`, and embedding model — treat them as
  a regression signal across changes, not an absolute grade.
- To gate changes, capture a baseline `report.json`, then compare after tuning retrieval.
