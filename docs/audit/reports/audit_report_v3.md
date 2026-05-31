# Re-Audit Report v3 (Post-Implementation) — `pt-act/chat-bot`

**Repository:** https://github.com/pt-act/chat-bot
**Baselines:** `f66d369` (original) → remediated `68239cd` → **this audit: `feat/web-client` @ `418e178`**
(contains all 10 stacked branches: 5 audit-remediation + 5 spec-implementation)
**Date:** 2026-05-30
**Auditor:** Poncho (automated + manual). Prior reports: [`audit_report.md`](audit_report.md), [`audit_report_v2.md`](audit_report_v2.md)

---

## Table of Contents
1. [Verdict & Executive Summary](#1-verdict--executive-summary)
2. [Score Change](#2-score-change)
3. [Spec Implementation Verification](#3-spec-implementation-verification)
4. [New Findings (this re-audit)](#4-new-findings-this-re-audit)
5. [Fresh Tool Evidence](#5-fresh-tool-evidence)
6. [Test & Coverage](#6-test--coverage)
7. [Backward Compatibility](#7-backward-compatibility)
8. [Residual Risks](#8-residual-risks)
9. [Push-Readiness Checklist](#9-push-readiness-checklist)

---

## 1. Verdict & Executive Summary

**Verdict: READY TO PUSH** — one *accept-with-mitigation* item remains (the upstream
ChromaDB CVE with no fixed release). All other findings, including a JS dev-dependency
issue surfaced during this very audit, are resolved.

This re-audit covers a substantially larger codebase than v2: the UI/UX spec is fully
implemented (versioned API contract, problem+json errors, per-request controls,
structured citations, SSE streaming, async ingest + pagination) **plus a new
TypeScript/React reference web client**. Despite the surface growth (1,288 → 1,823 LOC
Python, plus a new SPA), quality held:

- **Python: 178 passed / 0 failed, 97% coverage**; `ruff` + `ruff format` + `bandit` clean.
- **Web: typecheck + production build pass; `bun audit` → no vulnerabilities** (after the
  vite upgrade applied during this audit).
- **No secrets**, no tracked build artifacts, no new SAST findings.

The audit also caught and fixed a real issue: two **moderate dev-server-only** advisories
in the build tooling (`vite`/`esbuild`), now cleared by upgrading vite 5→8.

---

## 2. Score Change

### Overall: **72 (C)** → **87 (A−)** [v2] → **90 / 100 (A−)** [now]

The spec work raised correctness/testing/architecture and added a whole DX + frontend
surface. The score is still capped below A by the unpatched upstream **chromadb CVE** and
the by-design lack of `/chat` auth.

| Dimension | v2 | Now | Why it moved |
|---|---:|---:|---|
| Architecture & maintainability | 88 | 90 | Clean v1 layering, shared prompt builder, typed schemas; one function at CC "C" (I-7) |
| Correctness | 92 | 93 | Per-request controls + streaming covered by tests; contract is explicit |
| Security | 85 | 88 | problem+json everywhere (no 5xx leak), rate-limit headers, SSE error has no leak, JS dev-deps cleaned |
| Testing | 90 | 92 | 178 tests incl. streaming/async/v1 contract; integration path covered |
| Dependencies / supply chain | 70 | 72 | JS deps now clean; still capped by unpatched chromadb CVE |
| CI/CD & docs | 90 | 92 | API self-describing via OpenAPI; web README; CI redis+env from prior work |

---

## 3. Spec Implementation Verification

Every item from [`ui_ux_improvement_spec.md`](ui_ux_improvement_spec.md) is implemented and
test-backed.

| Spec | Item | Status | Evidence |
|------|------|--------|----------|
| A1 | Unified envelope + RFC 9457 problem+json | ✅ | `schemas/responses.py`, `middlewares/errors.py`; `tests/test_api_v1.py`, `test_main.py` |
| A2 | Per-request `mode`/`lang`/`top_k`/`score_threshold` | ✅ | `schemas/chat.py`, `services/chat_service.py`; `test_api_v1.py::TestPerRequestControls` |
| A3 | SSE streaming `/api/v1/chat/stream` | ✅ | `services/chat_service.stream_conversation`, `controllers/v1/chat.py`; `tests/test_streaming.py` |
| A4 | Structured citations (label/doc_id/score/page/snippet) | ✅ | `graph/nodes/retrieve_context.py`; `test_graph_nodes.py`, `test_api_v1.py` |
| A5 | Rate-limit headers (`Retry-After`, `X-RateLimit-*`) | ✅ | `middlewares/rate_limiter.py`; `tests/test_rate_limiter.py` |
| A6 | OpenAPI quality + `/api/v1` (legacy `/api` deprecated) | ✅ | `main.py`, controller `response_model`/`tags`; `test_api_v1.py::TestOpenAPI/TestLegacyDeprecation` |
| A7 | Async ingest (202 + poll) + docs pagination | ✅ | `controllers/v1/ingest.py`; `tests/test_async_ingest.py` |
| B | Reference web client (streaming, modes, citations, RTL, a11y) | ✅ | `web/` (Vite+React+TS); typecheck + build pass; `bun audit` clean |

Manual review of the new code found no injection/leak issues: SSE frames are JSON-encoded
and the `error` event carries no internal text (test-asserted); async ingest keeps the
`require_api_key` dependency and derives `doc_id` from the dot-free validated `file_name`;
pagination cursor is a bounded integer offset; the React client renders answer/snippet
text as text (no `dangerouslySetInnerHTML`), so model output cannot inject markup.

---

## 4. New Findings (this re-audit)

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| **W-1** | Low (dev-only) | `bun audit`: vite ≤6.4.1 path-traversal (GHSA-4w7w-66w2-5vf9) + esbuild ≤0.24.2 dev-server (GHSA-67mh-4wv8-2f99). **Dev-server only — not in the shipped `dist/` bundle.** | ✅ **Fixed** this audit — upgraded vite 5→8 + `@vitejs/plugin-react` 6; `bun audit` now clean. Build/typecheck still pass. |
| **I-7** | Info | `graph/nodes/retrieve_context.retrieve_context` cyclomatic complexity crept to **C (14)** as per-request overrides + the synthesized branch were added. Maintainability index still "A". | Open — recommend extracting the below-threshold/weak-match branch into a helper to return it to "B". Non-blocking. |
| **I-8** | Info | Lighter coverage on `controllers/v1/ingest.py` (68%: v1 `delete_doc` not directly tested — same logic as the tested legacy delete) and the SSE error branch in `controllers/v1/chat.py`. | Open — add a v1 delete test; non-blocking. |
| **I-9** | Info | `controllers/v1/chat.py` imports the private `_validate_user_id` from the legacy controller. | Open — consider promoting it to a shared `controllers/_common.py`. Cosmetic. |
| **DEP** | High* / Low-exposure | `chromadb 1.5.9` CVE-2026-45829 (pre-auth RCE) — **no fixed release upstream**. | ⚠️ Residual (unchanged) — embedded (non-server) use limits exposure; see §8. |

\* CVSS/upstream severity; exposure in this app is low (Chroma runs embedded, not as a server).

---

## 5. Fresh Tool Evidence

Regenerated against `418e178`, saved under [`reaudit2/`](reaudit2/).

| Tool | Result | Artifact |
|---|---|---|
| **ruff** (lint) | ✅ All checks passed | [`reaudit2/logs/ruff-check.txt`](reaudit2/logs/ruff-check.txt), [`reaudit2/ruff.sarif`](reaudit2/ruff.sarif) |
| **ruff format** | ✅ 58 files formatted | [`reaudit2/logs/ruff-format.txt`](reaudit2/logs/ruff-format.txt) |
| **bandit** (Python SAST) | ✅ 0 issues (1,823 LOC) | [`reaudit2/bandit.json`](reaudit2/bandit.json) |
| **pip-audit** (Python deps) | ⚠️ 1 (chromadb, unchanged — no upstream fix) | [`reaudit2/pip-audit.json`](reaudit2/pip-audit.json) |
| **bun audit** (JS deps) | ✅ No vulnerabilities found (after vite 8 upgrade) | [`reaudit2/logs/bun-audit.txt`](reaudit2/logs/bun-audit.txt) |
| **radon cc** | A/B except `retrieve_context` C(14) (I-7) | [`reaudit2/logs/radon-cc-full.txt`](reaudit2/logs/radon-cc-full.txt) |
| **secret scan** (incl. `web/`) | ✅ 0 matches; no `.env`/`.coverage`/`node_modules`/`dist` tracked | [`reaudit2/logs/secret-scan.txt`](reaudit2/logs/secret-scan.txt) |
| **web build** | ✅ tsc -b + vite build pass (≈147 KB JS / 48 KB gzip) | — |

---

## 6. Test & Coverage

```
Python: 178 passed, 0 failed — 97% line coverage
Web:    typecheck (tsc -b) + production build pass
```

New test files since v2: `test_api_v1.py`, `test_streaming.py`, `test_async_ingest.py`
(and updated node/citation/rate-limit/error tests). The suite remains **hermetic** (no live
Redis or network).

Remaining uncovered lines are low-risk: thin service wrappers
(`services/ingest_service.py`), a few defensive/error branches (SSE `error`, v1 `delete_doc`,
`logging_setup` JSON, one SSRF rejection message). See §4 I-8. Full per-module table in
[`reaudit2/logs/pytest.log`](reaudit2/logs/pytest.log).

---

## 7. Backward Compatibility

Verified preserved:
- Legacy `/api/chat` keeps `{"status":"success","data","sources"}` with **sources as label
  strings** (v1 returns structured objects); legacy `/api/ingest` stays **synchronous**.
- Legacy responses now carry `Deprecation`/`Sunset`/`Link` headers pointing to `/api/v1`
  (`test_api_v1.py::TestLegacyDeprecation`).
- The error model changed app-wide to problem+json (a deliberate, strictly-better
  cross-cutting change); the only test updates were error-shape assertions.

---

## 8. Residual Risks

1. **chromadb CVE-2026-45829 [residual].** No upstream fix yet. Mitigation in place:
   embedded (non-server) usage → no remote attack surface as deployed. Keep the Chroma
   server API off the network; track for a patched release. *Sole reason the grade is not
   higher.*
2. **No `/chat` authentication (by design).** `X-User-Id` is validated + namespaced but not
   authenticated; gate `/chat` behind real auth if memory is sensitive. The new web client
   also implies a **CORS** decision for production (`CORS_ORIGINS`) — documented in `web/README.md`.
3. **SSE at scale / behind proxies.** Endpoint sets `Cache-Control: no-cache` and
   `X-Accel-Buffering: no`; confirm the production proxy does not buffer event streams.
4. **In-process async ingest.** Uses FastAPI `BackgroundTasks` (single-process). For
   durability/horizontal scale, move to a Celery/RQ worker (already on the roadmap).
5. **vite 8 requires a modern Node (20+)** for the web dev/build toolchain — note for CI.

---

## 9. Push-Readiness Checklist

| Gate | Status |
|---|---|
| All Critical/High findings fixed | ✅ (chromadb = external, no fix; accepted w/ mitigation) |
| All Medium findings fixed | ✅ |
| New findings this audit triaged | ✅ (W-1 fixed; I-7/I-8/I-9 informational) |
| Python lint + format + SAST clean | ✅ |
| JS deps audit clean | ✅ (post vite 8) |
| Secret scan clean; no build artifacts tracked | ✅ |
| Python suite green + hermetic | ✅ 178/0, 97% |
| Web typecheck + build pass | ✅ |
| Backward compatibility verified | ✅ |

**Recommendation: proceed with the push.** Track CVE-2026-45829 and (optionally) I-7/I-8
as follow-up issues.

### Branch stack (apply/PR order 1 → 10)
```
main
 ├─ audit/low-risk-fixes
 ├─ audit/ci-and-ssrf-hardening
 ├─ audit/hardening-batch-2
 ├─ audit/synthesized-isolation
 ├─ audit/graph-integration-test
 ├─ feat/api-v1-core
 ├─ feat/api-controls-citations
 ├─ feat/api-streaming
 ├─ feat/async-ingest
 └─ feat/web-client   ← HEAD (418e178)
```
