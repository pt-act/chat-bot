# PR Draft 3

**Branch:** `audit/hardening-batch-2` (stacked on `audit/ci-and-ssrf-hardening`) → `main`
**Title:** `harden: generic 5xx bodies, namespaced+validated memory keys, cleanup`

> Draft only — not pushed. Apply in order after PRs 1 and 2:
> `git apply audit-low-risk-fixes.patch && git apply audit-ci-and-ssrf-hardening.patch && git apply audit-hardening-batch-2.patch`

## Summary

Third batch from the audit: closes the remaining medium findings (information
disclosure, memory-key safety) and the informational cleanups.

## Changes

- **MEDIUM (M-3) — information disclosure on 5xx:** `main.runtime_error_handler` and the
  `RuntimeError` branches of both controllers no longer return `str(exc)` to the client;
  they log full detail server-side and return a generic message. 4xx validation feedback
  is unchanged (still useful and safe).
- **MEDIUM (M-4) — memory-key safety:**
  - Per-user memory is now namespaced via `db.redis_client.memory_key()` →
    `chat:memory:{user_id}`, so a caller-controlled `X-User-Id` can no longer collide
    with operational keys (`ingest:*`, `rate_limit:*`).
  - `chat_controller` validates `X-User-Id` against `[A-Za-z0-9_.@-]{1,128}`
    (blank → `anonymous`, invalid → `400`).
  - *Note:* this scopes/sanitizes the identifier; it does not by itself authenticate
    users. If conversations are sensitive, gate `/chat` behind real auth (tracked
    separately).
- **INFO (I-1):** remove the unused `db.vector.chroma()` alias; add `self_ingest` to
  `graph.nodes.__all__`.
- **INFO (I-2):** centralize duplicated ingest Redis keys in `ingest/keys.py`
  (`ALL_DOCS_KEY`, `CONTENT_HASHES_KEY`, `ingest_status_key`, `doc_chunks_key`);
  `ingest/policies.py` and the ingest controller import from it. Key **strings are
  unchanged**, so existing data and tests are unaffected.
- **Tests:** new `tests/test_audit_fixes_2.py` (user-id validation, namespacing,
  round-trip, no-leak, dead-code removed); the 500-handler test now asserts the message
  is *not* leaked.

## Validation

```
ruff check .            # All checks passed
ruff format --check .   # clean
pytest -q               # 157 passed, 0 failed (98% coverage)
```

## Still open (maintainer decision)

- **M-5** — separate self-ingested synthesized answers from authoritative vector data
  (distinct collection / retrieval filter / review workflow). Larger design change;
  intentionally not bundled here.
- Real authentication for `/chat` if conversation memory is sensitive (M-4 follow-up).
- Track chromadb **CVE-2026-45829**; never expose the Chroma server API on the network.
