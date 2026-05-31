# PR Draft 4

**Branch:** `audit/synthesized-isolation` (stacked on `audit/hardening-batch-2`) → `main`
**Title:** `harden(rag): isolate self-ingested synthesized answers (M-5)`

> Draft only — not pushed. Apply after PRs 1–3.

## Problem

In `learning` mode the model's own synthesized answers were embedded into the **same**
ChromaDB collection as authoritative policy documents (`self_ingest` →
`get_vectorstore()`). Future retrievals could then surface that unverified,
model-generated content as if it were authoritative — knowledge-base poisoning /
hallucination amplification that compounds over time and breaks the strict-mode
"answer only from approved docs" guarantee.

## Changes

- **`config.py`:** add `synthesized_collection` (default `"synthesized_answers"`).
- **`db/vector.py`:** `get_vectorstore(collection_name=None)` plus
  `get_synthesized_vectorstore()` (same persist dir, separate collection).
- **`graph/nodes/self_ingest.py`:** write synthesized docs to the synthesized
  collection only — never the authoritative one.
- **`graph/nodes/retrieve_context.py`:** `learning` mode additionally consults the
  synthesized store (best-effort; fails safe to `[]`). **`strict` and `open` never
  touch it**, so synthesized content can never appear in authoritative answers.
- **Tests:** `tests/test_synthesized_isolation.py` (separate-collection assertion +
  per-mode isolation: learning includes, open/strict exclude). Updated the existing
  `self_ingest` / learning-retrieval tests to the new accessor.

## Behavioural contract

| Mode | Authoritative store | Synthesized store |
|------|---------------------|-------------------|
| strict | yes (with threshold) | **never** |
| open | yes (weak allowed) | **never** |
| learning | yes (weak allowed) | yes (fallback) |

## Validation

```
ruff check . && ruff format --check .   # clean
pytest -q                                # 161 passed, 0 failed
```

## Follow-ups (not in this PR)
- Optional human-review/promotion workflow before synthesized content is reused.
- Surface a clear "synthesized / unofficial" label in responses that draw on it.
