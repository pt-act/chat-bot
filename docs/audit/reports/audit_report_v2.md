# Re-Audit Report (Post-Remediation) — `pt-act/chat-bot`

**Repository:** https://github.com/pt-act/chat-bot
**Baseline audited:** `f66d369` (`main`) — see [`audit_report.md`](audit_report.md)
**Re-audited state:** branch `audit/graph-integration-test` @ `68239cd`
(contains all 5 stacked remediation branches)
**Date:** 2026-05-30
**Auditor:** Poncho (automated + manual verification)

---

## Table of Contents

1. [Verdict & Executive Summary](#1-verdict--executive-summary)
2. [Score Change](#2-score-change)
3. [Finding-by-Finding Verification](#3-finding-by-finding-verification)
4. [Fresh Tool Evidence (re-run)](#4-fresh-tool-evidence-re-run)
5. [Test & Coverage](#5-test--coverage)
6. [Residual Risks & New Observations](#6-residual-risks--new-observations)
7. [Push-Readiness Checklist](#7-push-readiness-checklist)
8. [Appendix: Commands](#8-appendix-commands)

---

## 1. Verdict & Executive Summary

**Verdict: READY TO PUSH** — with one *accept-with-mitigation* item (an upstream
ChromaDB CVE that has no fixed release yet; see §6).

Every Critical, High, and Medium finding from the baseline audit — plus both
Informational cleanups — is **resolved and verified** on the re-audited branch. The
test suite went from **129 passing / 8 failing** (baseline) to **162 passing / 0
failing** at **97.8% line coverage**, and is now **hermetic** (passes with no live
Redis and no network). `ruff`, `ruff format`, and `bandit` are all clean.

Most importantly, the latent **critical** defect (the `get_llm()` signature crash that
hid behind mocked tests) is fixed **and** now guarded by a real end-to-end integration
test that exercises the un-mocked `get_llm` path — so it cannot silently regress.

What changed since the baseline, at a glance:

- **Correctness:** core chat path no longer crashes; `doc_id` suffix bug, source-metadata
  mismatch fixed; integration coverage added.
- **Security:** SSRF closed on both vectors (redirects + DNS rebinding); 5xx responses no
  longer leak internals; conversation-memory keys namespaced + validated; self-ingested
  content isolated from authoritative RAG data.
- **Supply chain / CI:** missing provider dependency added and LangChain deps pinned; CI
  `test` job now provisions Redis and explicit env; `.env`/`.coverage` untracked + ignored.

---

## 2. Score Change

### Overall: **72 / 100 (C)** → **87 / 100 (A−)**

Held back from the A range solely by the unpatched upstream **chromadb CVE-2026-45829**
(no fixed version exists yet) and the deliberate "no auth on `/chat` by default" posture.

| Dimension | Baseline | Now | Why it moved |
|---|---:|---:|---|
| Architecture & maintainability | 85 | 88 | Centralized keys, small helpers, clearer layering; one function nudged to CC "C" (see §6) |
| Correctness | 55 | 92 | Critical crash fixed + integration-tested; functional bugs fixed |
| Security | 65 | 85 | SSRF (both vectors), info-leak, memory namespacing, RAG isolation all closed |
| Testing | 70 | 90 | 162 pass / 0 fail, hermetic, real-path integration test, 97.8% cov |
| Dependencies / supply chain | 60 | 70 | Deps added/pinned; capped by the unpatched chromadb CVE |
| CI/CD & docs | 80 | 90 | CI now has Redis + explicit env; no longer depends on committed `.env` |

---

## 3. Finding-by-Finding Verification

Status legend: ✅ Fixed & verified · ⚠️ Accepted/Residual · ⛔ Open

| ID | Severity | Title | Status | Evidence (re-audit) |
|----|----------|-------|--------|---------------------|
| **C-1** | Critical | `get_llm()` called with args it didn't accept (crash) | ✅ Fixed | `get_llm(temperature, max_tokens)`; `utils/llm_adapter.py` 100% cov; new `tests/test_graph_integration.py` drives the real path |
| **H-1** | High | SSRF allowlist bypass (redirect **+** DNS rebinding) | ✅ Fixed | `allow_redirects=False`; `validate_download_url` resolves DNS & blocks private IPs; `tests/test_security.py` (incl. rebinding cases) |
| **H-2** | High | Missing `langchain-google-genai`; unpinned LangChain deps | ✅ Fixed | `requirements.txt` adds google + pins anthropic/groq; google adapter tests pass |
| **H-3** | High | CI `test` job had no Redis / depended on committed `.env` | ✅ Fixed | `.github/workflows/ci.yml` adds `redis:7-alpine` + explicit env; suite is hermetic regardless |
| **M-1** | Medium | Rate-limiter tests didn't actually test (patch scope) | ✅ Fixed | `tests/test_rate_limiter.py` keeps patch active via `teardown_method`; passes without live Redis |
| **M-2** | Medium | Sources reported `"unknown"` (metadata key mismatch) | ✅ Fixed | `_source_of` prefers `source_file`; covered |
| **M-3** | Medium | Internal exception text leaked on 5xx | ✅ Fixed | `main.py` + both controllers return generic 5xx; `tests/test_main.py` asserts no leak |
| **M-4** | Medium | Memory keyed by raw, unvalidated `X-User-Id` | ✅ Fixed | `memory_key()` → `chat:memory:{id}`; controller validates `[A-Za-z0-9_.@-]{1,128}` |
| **M-5** | Medium | Self-ingest poisoned authoritative vector store | ✅ Fixed | separate `synthesized_answers` collection; learning-mode-only retrieval; `tests/test_synthesized_isolation.py` |
| **L-1** | Low | `.env` / `.coverage` tracked in git | ✅ Fixed | untracked + added to `.gitignore`; `git ls-files` shows neither |
| **L-2** | Low | `rstrip(".pdf")` strips a char set | ✅ Fixed | `removesuffix(".pdf")`; covered |
| **L-3** | Low | Google key check ran after the import | ✅ Fixed | validation precedes import; test asserts `ValueError` |
| **L-4** | Low | Rate limiter fails open on Redis errors | ⚠️ Accepted | Deliberate availability trade-off; recommend a metric/alert (unchanged) |
| **I-1** | Info | Dead `chroma()`; `__all__` missing `self_ingest` | ✅ Fixed | `chroma()` removed; `__all__` updated; `test_audit_fixes_2.py` asserts removal |
| **I-2** | Info | Duplicated ingest Redis-key constants | ✅ Fixed | centralized in `ingest/keys.py` (key strings unchanged) |
| **DEP** | High* | `chromadb 1.5.9` CVE-2026-45829 (pre-auth RCE) | ⚠️ Residual | No fixed version published; embedded (non-server) usage limits exposure — see §6 |

\* Severity is upstream/CVSS-driven; **exposure in this app is low** because Chroma runs
embedded, not as a network server.

---

## 4. Fresh Tool Evidence (re-run)

All outputs regenerated against `68239cd` and saved under [`reaudit/`](reaudit/).

| Tool | Baseline | Now | Artifact |
|---|---|---|---|
| **ruff** (lint) | clean | ✅ All checks passed | [`reaudit/logs/ruff-check.txt`](reaudit/logs/ruff-check.txt), [`reaudit/ruff.sarif`](reaudit/ruff.sarif) |
| **ruff format --check** | clean | ✅ 50 files formatted | [`reaudit/logs/ruff-format.txt`](reaudit/logs/ruff-format.txt) |
| **bandit** (SAST) | 0 issues | ✅ 0 issues (1,370 LOC) | [`reaudit/bandit.json`](reaudit/bandit.json) |
| **pip-audit** | 1 (chromadb) | ⚠️ 1 (chromadb, unchanged — no fix upstream) | [`reaudit/pip-audit.json`](reaudit/pip-audit.json), [`reaudit/logs/pip-audit.txt`](reaudit/logs/pip-audit.txt) |
| **radon cc** | all A/B + one C(12) | A/B + one C(13) `retrieve_context` (see §6) | [`reaudit/logs/radon-cc.txt`](reaudit/logs/radon-cc.txt) |
| **radon mi** | all A | ✅ all A (lowest `ingest/policies.py` 44.5) | [`reaudit/logs/radon-mi.txt`](reaudit/logs/radon-mi.txt) |
| **secret scan** | clean | ✅ 0 matches; `.env`/`.coverage` untracked | [`reaudit/logs/secret-scan.txt`](reaudit/logs/secret-scan.txt) |

---

## 5. Test & Coverage

```
162 passed, 0 failed — 97.8% line coverage   (baseline: 8 failed / 129 passed, 96%)
```

- Suite is **hermetic**: passes with no live Redis and no network (fakeredis + mocked
  DNS/boundaries). The 8 baseline failures (missing google dep, live-Redis dependence,
  patch-scope bug) are all resolved.
- **New tests added during remediation:** `tests/test_audit_fixes.py`,
  `tests/test_audit_fixes_2.py`, `tests/test_synthesized_isolation.py`,
  `tests/test_graph_integration.py`, plus DNS-rebinding cases in `tests/test_security.py`.
- **Coverage caveat resolved:** the baseline's 96% masked the C-1 crash because every
  test mocked `_get_chat`. The new integration test exercises the real `get_llm` path, so
  that blind spot is closed.

Remaining uncovered lines are low-risk: thin service wrappers
(`services/chat_service.py`, `services/ingest_service.py`), defensive `except` branches
(e.g. `retrieve_context._search_synthesized`, marked `# pragma: no cover`), the
`logging_setup` JSON branch, and one alternate SSRF rejection message
(`utils/security.py:94`). None are critical paths.

Raw log: [`reaudit/logs/pytest.log`](reaudit/logs/pytest.log) ·
coverage XML: [`reaudit/coverage.xml`](reaudit/coverage.xml).

---

## 6. Residual Risks & New Observations

1. **`chromadb 1.5.9` — CVE-2026-45829 (pre-auth RCE) [residual HIGH, external].**
   No fixed release exists yet, so it cannot be remediated by upgrade today.
   *Mitigation (in place / recommended):* Chroma is used **embedded** (persistent local
   store), not as a network server, so the remote attack surface is effectively absent in
   the current deployment. **Do not** expose the Chroma server API on the network; if a
   server mode is ever introduced, disable `trust_remote_code` and require auth. Track the
   advisory and bump as soon as a patched version ships. *This is the only item keeping
   the grade out of the A range and is the single conscious risk acceptance for the push.*

2. **No authentication on `/chat` (by design).** M-4 namespaced and validated
   `X-User-Id`, eliminating key-collision and injection, but it does not *authenticate*
   the caller. If conversation memory is sensitive, gate `/chat` behind real auth. Tracked
   as a follow-up, not a regression.

3. **Complexity nudge:** `retrieve_context` moved from CC **C(12) → C(13)** because of the
   learning-mode synthesized-store branch added for M-5. Still within acceptable range and
   maintainability stays "A". Optional cleanup: extract the below-threshold branch into a
   helper to bring it back to "B". (New informational item; non-blocking.)

4. **Rate limiter fail-open (L-4)** remains a deliberate trade-off — recommend emitting a
   metric/alert when Redis is unavailable so the open window is observable.

No new defects, secrets, or lint/SAST findings were introduced by the remediation work.

---

## 7. Push-Readiness Checklist

| Gate | Status |
|---|---|
| All Critical/High findings fixed | ✅ (chromadb CVE is external, no fix available — accepted w/ mitigation) |
| All Medium findings fixed | ✅ |
| Lint (`ruff`) + format clean | ✅ |
| SAST (`bandit`) clean | ✅ |
| Dependency scan reviewed | ✅ (1 residual, documented) |
| Secret scan clean; no secrets tracked | ✅ |
| Full test suite green, hermetic | ✅ 162/0 |
| Regression tests for fixed bugs | ✅ |
| No new findings introduced | ✅ |

**Recommendation: proceed with the push.** Open an issue to track CVE-2026-45829 and the
optional `/chat` auth follow-up.

### Branch stack to push (apply/PR order 1 → 5)
```
main
 └─ audit/low-risk-fixes
     └─ audit/ci-and-ssrf-hardening
         └─ audit/hardening-batch-2
             └─ audit/synthesized-isolation
                 └─ audit/graph-integration-test
```

---

## 8. Appendix: Commands

Re-audit environment (`reaudit/logs/environment.txt`): Linux x86_64, Python 3.10.12,
ruff 0.15.15, bandit 1.9.4, pip-audit 2.10.0, radon 6.0.1, pytest 9.0.3.

```bash
# run on branch audit/graph-integration-test (HEAD 68239cd)
ruff check . ; ruff format --check . ; ruff check . --output-format=sarif > ruff.sarif
bandit -r . -x ./tests,./.venv -f json -o bandit.json
pytest --cov=. --cov-report=xml --cov-report=term-missing -q     # 162 passed, 97.8%
pip-audit --format=json                                          # 1 residual: chromadb
radon cc -s -n B . ; radon mi -s .
# secret scan: high-signal regex over tracked files + git history (clean)
```

> Scope note: no real credentials were used; tests ran with a placeholder
> `OPENAI_API_KEY` and `EMBEDDING_PROVIDER=fastembed` to avoid external calls.
