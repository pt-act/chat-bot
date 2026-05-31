# PR Draft 2

**Branch:** `audit/ci-and-ssrf-hardening` (stacked on `audit/low-risk-fixes`) → `main`
**Title:** `harden: DNS-rebinding SSRF defense + CI Redis service & self-sufficient env`

> Draft only — not pushed. Apply **after** PR draft 1 (or apply both patches in order):
> `git apply audit-low-risk-fixes.patch && git apply audit-ci-and-ssrf-hardening.patch`.

## Summary

Second, security/infra-focused batch from the audit. Closes the remaining SSRF vector
(DNS rebinding) and makes the CI `test` job correct and independent of a committed `.env`.

## Changes

- **HIGH — `utils/security.py` (DNS-rebinding defense):** `validate_download_url()` now
  resolves the hostname via `socket.getaddrinfo` and rejects it if **any** resolved IP is
  private / loopback / link-local / multicast / reserved / unspecified. The previous guard
  only inspected the hostname *string*, so a public-looking domain pointing at
  `169.254.169.254` (cloud metadata) or an RFC1918 address slipped through. Resolution
  failures **fail closed**. Explicitly allowlisted hosts remain operator-trusted (not
  resolved). Combined with `allow_redirects=False` (PR 1) this closes both bypass vectors.
  - *Residual:* a TOCTOU window remains (DNS can change between check and request); a fully
    airtight fix pins the validated IP for the connection. Documented in the code.
- **CI — `.github/workflows/ci.yml`:** add a `redis:7-alpine` service (health-checked) to
  the `test` job, and set `OPENAI_API_KEY` / `LLM_PROVIDER` / `EMBEDDING_PROVIDER` /
  `EMBEDDING_MODEL` / `REDIS_*` as job `env` so CI no longer depends on the committed
  `.env`. The suite is hermetic (fakeredis) and passes with or without the service; the
  service keeps CI correct for future non-mocked integration tests.
- **Hygiene — `.gitignore` / tracking:** add `.coverage`, `coverage.xml`,
  `.pytest_cache/` to `.gitignore` (they were missing) and stop tracking `.env`
  (kept locally).
- **Tests:** `tests/test_security.py` gains DNS-rebinding cases (metadata IP, RFC1918,
  unresolvable→fail-closed, allowlisted-skips-DNS), all hermetic via mocked
  `socket.getaddrinfo`. `tests/conftest.py` pins ingest-test DNS to a public IP so the
  existing download tests stay offline-safe.

## Validation

```
ruff check .            # All checks passed
ruff format --check .   # clean
pytest -q               # 148 passed, 0 failed (97% coverage)
```

## Still open (maintainer decision, not in these patches)

- Generic 5xx error bodies (stop returning `str(exc)`) — M-3.
- Namespacing/authenticating `X-User-Id` Redis memory keys — M-4.
- Separating self-ingested synthesized answers from authoritative vector data — M-5.
- Tracking chromadb CVE-2026-45829 for a patched release; ensure Chroma is never exposed
  as a network server.
