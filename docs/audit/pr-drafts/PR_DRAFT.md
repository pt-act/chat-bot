# PR Draft

**Branch:** `audit/low-risk-fixes` → `main`
**Title:** `fix: critical LLM param crash, SSRF redirect bypass, broken deps & tests`

> Draft only — not pushed. No repo credentials were provided and remote actions
> (push / open PR / open issues) require explicit permission per the audit scope.
> Apply locally with `git apply audit-low-risk-fixes.patch`.

## Summary

Low-risk remediations surfaced by a code-quality audit. Each change is small,
isolated, and covered by a regression test in `tests/test_audit_fixes.py`.

## Changes

- **CRITICAL — `utils/llm_adapter.py`:** `get_llm()` now accepts
  `temperature` / `max_tokens`. The graph nodes already called
  `get_llm(temperature=…, max_tokens=…)`, but the function took no arguments, so the
  real `/chat` and summarize paths raised `TypeError` (hidden because every test mocks
  `_get_chat`). Also validate `GOOGLE_API_KEY` before importing the optional Google
  provider package.
- **HIGH — `ingest/policies.py`:** add `allow_redirects=False` to the download request
  to close an SSRF allowlist bypass (an allowed host could 30x-redirect to a
  private/metadata address, defeating `validate_download_url`). Also `removesuffix(".pdf")`
  instead of `rstrip(".pdf")` (the latter strips a character set, e.g. `"app.pdf"`→`"a"`).
- **HIGH — `requirements.txt`:** add `langchain-google-genai` (the `google` provider is
  imported in code but was undeclared) and pin `langchain-anthropic` / `langchain-groq`.
- **MEDIUM — `graph/nodes/retrieve_context.py`:** resolve sources via `source_file`
  (written at ingest) with a fallback to `source`, so real documents stop reporting
  `"unknown"`.
- **MEDIUM — `tests/test_rate_limiter.py`:** the `with patch(...): return TestClient(app)`
  pattern exited the patch before any request ran, so the middleware hit a real Redis and
  the rate-limit assertions never tested anything. Keep the patch active via
  `teardown_method`.
- **`tests/test_api.py`:** mock `main.get_redis` in the readiness test (it previously
  required a live Redis).
- **`tests/test_audit_fixes.py`:** new regression tests for all of the above.
- Stop tracking the build artifact `.coverage`.

## Validation

```
ruff check .            # All checks passed
ruff format --check .   # clean
pytest -q               # 144 passed, 0 failed (97% coverage)
```

## Not included (needs maintainer decision)

- Add a Redis `services:` block to the CI `test` job (or make those tests fully
  self-contained with `fakeredis`).
- DNS-resolution check in the SSRF guard (resolve host → check each IP).
- Generic 5xx error bodies (stop returning `str(exc)`).
- Namespacing/authenticating `X-User-Id` Redis memory keys.
- Separating self-ingested synthesized answers from authoritative vector data.
