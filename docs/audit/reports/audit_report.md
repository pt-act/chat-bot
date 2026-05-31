# Code-Quality Audit — `pt-act/chat-bot`

**Repository:** https://github.com/pt-act/chat-bot
**Commit audited:** `f66d369` (branch `main`)
**Date:** 2026-05-30
**Auditor:** Poncho (automated + manual review)
**Effort:** ~1 working session (≈3 hours equivalent)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Triage Summary](#2-triage-summary-stack--how-it-was-run)
3. [Detailed Findings](#3-detailed-findings)
   - [Critical](#critical)
   - [High](#high)
   - [Medium](#medium)
   - [Low](#low)
   - [Informational](#informational)
4. [Test & Coverage Results](#4-test--coverage-results)
5. [Automated Tool Evidence](#5-automated-tool-evidence)
6. [Action Plan / Roadmap](#6-action-plan--roadmap)
7. [Demo Fixes Delivered](#7-demo-fixes-delivered-branch-auditlow-risk-fixes)
8. [Appendix: Commands & Environment](#8-appendix-commands--environment)

---

## 1. Executive Summary

`chat-bot` is a **Python 3.10 / FastAPI + LangGraph RAG chatbot** with Redis-backed
conversation memory and a ChromaDB vector store. It is, for an open-source fork,
**above-average in engineering hygiene**: clean layering (controllers → services →
graph nodes → db/adapters), structured logging with correlation IDs, health/readiness
probes, a rate limiter, an SSRF guard, pinned CI action SHAs, ~97% line coverage,
and a clean `ruff` + `bandit` baseline.

However, the audit found a **latent critical runtime defect masked by over-mocked
tests**, a **real SSRF bypass**, and a **broken dependency/CI setup that means the
documented CI pipeline does not actually pass**. The high test-coverage number gives
a false sense of safety because the core LLM call path is mocked away in every test.

### Overall Quality Score: **72 / 100 — Grade C**

| Dimension | Score | Notes |
|---|---|---|
| Architecture & maintainability | 85 | Clean modular layering, low complexity (all A/B, one C), MI all "A" |
| Correctness | 55 | Critical latent crash in main chat path; 2 functional bugs |
| Security | 65 | SSRF guard present but bypassable; info disclosure; vector poisoning by design |
| Testing | 70 | 97% coverage but integration path mocked; 4 tests fail out-of-box |
| Dependencies / supply chain | 60 | Missing + unpinned deps; 1 unpatched CVE in chromadb |
| CI/CD & docs | 80 | Strong docs & CI structure, but `test` job omits Redis service |

### Top 3 Critical/High Issues

1. **[CRITICAL] `get_llm()` signature mismatch** — graph nodes call
   `get_llm(temperature=…, max_tokens=…)` but `get_llm()` takes **no arguments**.
   The real `/chat` and summarize paths raise `TypeError` at runtime. Every test
   mocks `_get_chat`, so the suite is green while the app is broken end-to-end.
2. **[HIGH] SSRF allowlist bypass via HTTP redirect** — `requests.get(...)` in the
   ingest downloader follows redirects by default, so an allowed public URL can
   `30x`-redirect to `169.254.169.254` (cloud metadata) or any private host,
   defeating `validate_download_url()` which only checks the *original* URL.
3. **[HIGH] Broken dependency & CI setup** — `langchain-google-genai` is imported in
   code (`LLM_PROVIDER=google`) but **not declared** in `requirements.txt`, and the
   CI `test` job starts **no Redis service**. As a result 8 tests fail in a clean
   environment and the documented pipeline is effectively red.

### Remediation Priority (quick view)

| Priority | Item | Effort |
|---|---|---|
| P0 | Fix `get_llm` params (CRITICAL crash) | 0.5 h ✅ *fixed in demo branch* |
| P0 | Add `langchain-google-genai`, pin LangChain deps | 0.25 h ✅ *fixed* |
| P0 | Add Redis service to CI `test` job | 0.5 h ✅ *fixed (branch 2)* |
| P1 | SSRF: `allow_redirects=False` + DNS-resolve validation | 1–2 h ✅ *both fixed (branches 1+2)* |
| P1 | Remove `.env` / `.coverage` from git tracking | 0.25 h ✅ *fixed + .gitignore'd* |
| P1 | Add integration test exercising the real graph (un-mocked adapters) | 2–3 h |
| P2 | Stop leaking `str(exc)` in 500 responses | 0.5 h ✅ *fixed (branch 3)* |
| P2 | Namespace Redis memory keys + validate `X-User-Id` | 1–2 h ✅ *fixed (branch 3)* |

> **Time to remediate all Critical + High:** ~1–1.5 engineer-days. The demo branch
> `audit/low-risk-fixes` already lands the critical crash, the redirect bypass, the
> dependency gaps, two functional bugs, and the 4 failing tests.

---

## 2. Triage Summary (stack & how it was run)

**Detected stack:** Python 3.10; FastAPI/Starlette + Uvicorn; LangGraph/LangChain;
ChromaDB (embedded/persistent); Redis (memory + rate limiting); pydantic-settings
config; pytest + ruff + bandit + pip-audit tooling. No JS/Go/Ruby components.

**How it was run (this audit):**

```bash
git clone https://github.com/pt-act/chat-bot.git
uv venv .venv --python 3.10 && . .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt httpx
# Tests need a non-empty OPENAI_API_KEY for config validation:
printf 'OPENAI_API_KEY=test-key\nEMBEDDING_PROVIDER=fastembed\nEMBEDDING_MODEL=BAAI/bge-small-en-v1.5\n' > .env
pytest --cov=. --cov-report=term-missing -v
```

**Do tests run?** Yes, but **8 of 137 fail out-of-the-box** (see §4). 4 are a missing
dependency (`langchain-google-genai`), 4 require a live Redis (test bugs / env gap).

**Immediate blockers / environment gaps (no secrets used, per scope):**
- **No live Redis or Docker** available in the audit sandbox → rate-limiter and
  readiness integration tests could not hit a real Redis (documented, not run).
- **No LLM API keys** — used placeholder keys; the real model calls were not exercised
  against providers (this is exactly why the CRITICAL bug below went unnoticed).
- `pip-audit -r requirements.txt` needs to build an isolated venv (`ensurepip`
  unavailable in sandbox); audited the **installed environment** instead — still
  surfaced the chromadb CVE.

---

## 3. Detailed Findings

Severity uses risk × likelihood. `file:line` references are against commit `f66d369`.

### Critical

#### C-1 — `get_llm()` is called with arguments it does not accept (runtime crash on main path)
- **Location:** `utils/llm_adapter.py:33` (definition) vs. `graph/nodes/generate_answer.py:15` and `graph/nodes/summarize.py:15` (callers).
- **Description:** `def get_llm():` takes no parameters, but both nodes call
  `get_llm(temperature=0, max_tokens=512/256)`. At runtime this raises
  `TypeError: get_llm() got an unexpected keyword argument 'temperature'`.
- **Why it matters:** The `/chat` endpoint (answer generation) and conversation
  summarization are the product's core. They fail for **every real request**. The
  bug is invisible because **all node tests mock `_get_chat`** (`test_graph_nodes.py`),
  so 96% coverage hides a 100%-broken integration path.
- **Reproduction:** Call `_get_chat()` (or `get_llm(temperature=0, max_tokens=512)`)
  without mocking → `TypeError`. No test exercises the unmocked path.
- **Suggested fix (implemented):** give `get_llm` the parameters and thread them through:
  ```python
  @lru_cache
  def get_llm(temperature: float = 0, max_tokens: int = 1000):
      ...
      kwargs = {"model": model, "temperature": temperature, "max_tokens": max_tokens}
  ```
- **Effort:** 0.5 h. **Priority:** P0. **Status:** ✅ fixed in `audit/low-risk-fixes`.

### High

#### H-1 — SSRF allowlist bypass through HTTP redirects
- **Location:** `ingest/policies.py:50` (`requests.get(..., stream=True)` — no `allow_redirects=False`); guard at `utils/security.py:33` `validate_download_url`.
- **Description:** `validate_download_url()` validates only the URL supplied in the
  request. `requests` follows 30x redirects by default, so an attacker-controlled (or
  compromised) allowed host can redirect the fetch to `http://169.254.169.254/…`
  (AWS/GCP metadata) or any internal address. The private-IP check never sees the
  final hop.
- **Secondary vector:** `_is_private_ip()` (`utils/security.py:12`) treats the hostname
  as a string — it does **not resolve DNS**. A public domain that resolves to a private
  IP (DNS rebinding) also bypasses the guard even without redirects.
- **Why it matters:** Server-Side Request Forgery can exfiltrate cloud credentials from
  the metadata endpoint or reach internal services. Ingest is auth-optional by default
  (`require_auth_for_ingest=False`).
- **Reproduction:** Ingest a URL on an allowed host returning `302 Location: http://169.254.169.254/…`. Pre-fix, the request is followed.
- **Suggested fix:** (a) `allow_redirects=False` *(implemented, branch 1)*; (b) resolve
  the hostname with `socket.getaddrinfo` and run every resolved IP through the
  private/reserved check before connecting *(implemented, branch 2)*; (c) if redirects
  must be supported, re-validate each hop.
- **Effort:** 1–2 h. **Priority:** P1. **Status:** ✅ redirect-following closed (branch 1)
  **and** DNS-rebinding closed (branch 2). Residual: a TOCTOU window between validation
  and the request remains (DNS can change); a fully airtight fix pins the validated IP
  for the connection.

#### H-2 — Broken dependency declaration: `langchain-google-genai` missing; `langchain-anthropic`/`langchain-groq` unpinned
- **Location:** `requirements.txt:16-21`; consumed at `utils/llm_adapter.py:72`, `config.py:70-71`.
- **Description:** `LLM_PROVIDER=google` is a first-class, validated provider, but the
  package is not in `requirements.txt`. A fresh install + `LLM_PROVIDER=google` raises
  `ModuleNotFoundError`. Three adapter tests fail for this reason. `langchain-anthropic`
  and `langchain-groq` are declared with **no version pin**, undermining reproducibility
  for a project that otherwise pins everything.
- **Why it matters:** Advertised functionality is uninstallable; unpinned LangChain
  packages can pull breaking majors (the ecosystem moves fast).
- **Suggested fix (implemented):** add `langchain-google-genai` and pin
  `langchain-anthropic==1.4.4`, `langchain-groq==1.1.2`.
- **Effort:** 0.25 h. **Priority:** P0. **Status:** ✅ fixed.

#### H-3 — CI `test` job has no Redis service → pipeline is effectively red
- **Location:** `.github/workflows/ci.yml:64-88`.
- **Description:** The `test` job installs deps and runs `pytest --cov-fail-under=95`
  but defines **no `services: redis:` container**. The readiness test and three
  rate-limiter tests connect to `localhost:6379` (the latter due to a test bug, H-4),
  and the three `google`-provider tests fail on the missing dependency (H-2). With 8
  failing tests the job fails — meaning the green-CI assumption is incorrect, or these
  tests were added in the fork without validating CI.
- **Suggested fix:** add a Redis service to the job and install the google dependency
  (covered by H-2):
  ```yaml
  test:
    services:
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s
          --health-timeout 3s --health-retries 5
  ```
  (Better still: make the affected tests fully self-contained with `fakeredis` — see M-1.)
- **Effort:** 0.5 h. **Priority:** P0. **Status:** ✅ fixed in branch 2 — added the Redis
  `services:` block **and** explicit `OPENAI_API_KEY`/provider/`REDIS_*` env so CI no
  longer silently depends on the committed `.env` (which branch 2 also untracks). The
  test suite itself is now hermetic (fakeredis), so it passes with or without the service.

### Medium

#### M-1 — Rate-limiter tests don't actually test the rate limiter (patch exits before requests run)
- **Location:** `tests/test_rate_limiter.py:51-94` (pre-fix `_make_app`).
- **Description:** `_make_app` did `with patch("…get_redis", …): return TestClient(app)`.
  The context manager exits the moment the function returns, so during the actual
  requests `get_redis` is **unpatched** → connects to real Redis → on failure the
  middleware *fails open* and returns 200. The three assertions about `429`/limits
  pass or fail by luck of the environment, never validating the logic.
- **Why it matters:** False confidence; the rate limiter is essentially untested.
- **Suggested fix (implemented):** start the patcher and stop it in `teardown_method`
  so it stays active for the request lifecycle.
- **Effort:** 0.5 h. **Priority:** P1. **Status:** ✅ fixed.

#### M-2 — `sources` always reported as `"unknown"` for real documents (metadata key mismatch)
- **Location:** writer `ingest/policies.py:105-113` (key `source_file`) vs. reader `graph/nodes/retrieve_context.py:27,34` (key `source`).
- **Description:** Ingested chunks store the filename under `metadata["source_file"]`,
  but retrieval reads `metadata.get("source", "unknown")`. Every citation for a real
  policy document therefore surfaces as `"unknown"`. (Self-ingested chunks use
  `source`, which is why this slipped through.)
- **Why it matters:** Source attribution — a selling point of RAG — is silently broken
  for the primary document type.
- **Suggested fix (implemented):** resolve via `source_file` then fall back to `source`.
- **Effort:** 0.5 h. **Priority:** P2. **Status:** ✅ fixed.

#### M-3 — Internal exception messages leaked to clients on 5xx
- **Location:** `main.py:90,96`; `controllers/chat_controller.py:23,26`; `controllers/ingest_controller.py:22,25`.
- **Description:** `ValueError`/`RuntimeError` handlers return `detail=str(exc)` to the
  client, including the 500 path. Internal messages (stack-derived text, file paths,
  upstream errors) can leak to callers.
- **Why it matters:** Information disclosure aids attackers and can expose infra detail.
- **Suggested fix (implemented):** log full detail server-side (already done) but return
  a generic message for 5xx; reserve specific detail for 4xx validation only.
- **Effort:** 0.5 h. **Priority:** P2. **Status:** ✅ fixed in branch 3 (`main.py` +
  both controllers).

#### M-4 — Conversation memory keyed by unauthenticated, unnamespaced `X-User-Id`
- **Location:** `controllers/chat_controller.py:15` (`X-User-Id` default `anonymous`); `graph/nodes/load_memory.py:14`; `graph/nodes/store_memory.py:29`.
- **Description:** `/chat` is unauthenticated and `X-User-Id` is used **verbatim** as a
  Redis key. Two problems: (1) any caller can impersonate another user's id to read/over­
  write their conversation memory (no auth, no validation); (2) memory keys share the
  Redis keyspace with operational keys (`ingest:doc_ids`, `ingest_status:*`) with no
  namespace prefix, so a crafted `X-User-Id` could collide with/overwrite app state.
- **Why it matters:** Cross-user data exposure and potential state corruption.
- **Suggested fix (implemented):** namespace memory keys (`chat:memory:{user_id}`) and
  validate/limit the header format; tie identity to auth where conversations are sensitive.
- **Effort:** 1–2 h. **Priority:** P2. **Status:** ✅ fixed in branch 3 — keys namespaced
  via `db.redis_client.memory_key()`, `X-User-Id` validated against `[A-Za-z0-9_.@-]{1,128}`.
  Residual: this sanitizes/scopes the id but does not authenticate users — gate `/chat`
  behind real auth if memory is sensitive.

#### M-5 — Self-ingestion writes synthesized LLM answers into the authoritative vector store
- **Location:** `graph/nodes/self_ingest.py:33-46` (learning mode).
- **Description:** In `learning` mode, the model's own answer is embedded and stored in
  the **same collection** as vetted policy documents. Future retrievals can surface this
  unverified, model-generated content as if authoritative — a knowledge-base poisoning /
  hallucination-amplification risk that compounds over time.
- **Why it matters:** Erodes the "answer only from approved docs" guarantee that the
  strict-mode design is built around.
- **Suggested fix (implemented):** store synthesized content in a **separate collection**;
  retrieval consults it **only in learning mode** (strict/open never see it). Human review
  before promotion and clear source labelling remain recommended follow-ups.
- **Effort:** 2–4 h. **Priority:** P2 (design). **Status:** ✅ fixed in branch 4 —
  `synthesized_collection` config + `get_synthesized_vectorstore()`; `self_ingest` writes
  there only; `retrieve_context` reads it only in learning mode.

### Low

#### L-1 — `.env` and `.coverage` are tracked in git
- **Location:** repo root (`git ls-files` shows `.env`, `.coverage`), although `.gitignore` lists them.
- **Description:** `.env` is committed (it pre-dates the `.gitignore` entry). **Git
  history confirms it only ever contained placeholders** (`your_openai_key`, `<api key>`)
  — no real secret leaked — but a tracked `.env` invites accidental secret commits and
  is regenerated/overwritten locally. `.coverage` is a build artifact that produces noisy
  binary diffs on every test run.
- **Suggested fix (implemented):** `git rm --cached .env .coverage` and add
  `.coverage`/`coverage.xml`/`.pytest_cache/` to `.gitignore` (it lacked them). `.coverage`
  was untracked in branch 1; `.env` untracking + the `.gitignore` additions land in branch 2.
- **Effort:** 0.25 h. **Priority:** P1 (hygiene). **Status:** ✅ fixed (branches 1+2).

#### L-2 — `doc_id = file_name.rstrip(".pdf")` strips a character set, not a suffix
- **Location:** `ingest/policies.py:190` (pre-fix).
- **Description:** `str.rstrip(".pdf")` removes any trailing run of `{'.', 'p', 'd', 'f'}`,
  so `"app.pdf"` → `"a"`. **Currently latent** because `schemas/ingest.py:23` rejects
  any `file_name` containing a dot, so the `.pdf` branch is unreachable via the HTTP API —
  but it is a correctness landmine for any direct/future caller (and for clarity).
- **Suggested fix (implemented):** `file_name.removesuffix(".pdf")`.
- **Effort:** 0.1 h. **Priority:** P3. **Status:** ✅ fixed.

#### L-3 — `GOOGLE_API_KEY` check runs *after* importing the provider package
- **Location:** `utils/llm_adapter.py:72-75` (pre-fix order).
- **Description:** The `from langchain_google_genai import …` ran before the key check,
  so a missing key produced `ModuleNotFoundError` (when the dep is absent) instead of the
  intended `ValueError("GOOGLE_API_KEY is required")` (confirmed by a failing test).
- **Suggested fix (implemented):** validate the key before the import.
- **Effort:** 0.1 h. **Priority:** P3. **Status:** ✅ fixed.

#### L-4 — Rate limiter fails open on Redis errors
- **Location:** `middlewares/rate_limiter.py:107-109`.
- **Description:** On any Redis exception the limiter logs a warning and allows the
  request. This is a deliberate availability trade-off, but it means a Redis outage
  silently disables all rate limiting (DoS amplification window).
- **Suggested fix:** keep fail-open but add a metric/alert; consider a short in-process
  fallback bucket. **Effort:** 1 h. **Priority:** P3.

### Informational

- **I-1** Dead code: `db/vector.py:17` `chroma()` is unused; `graph/nodes/__init__.py`
  `__all__` omits `self_ingest`. ✅ **fixed in branch 3** (removed `chroma()`; added
  `self_ingest`). (`get_vectorstore_repo()` is also unused but kept as a legitimate
  public factory.)
- **I-2** `controllers/ingest_controller.py` defined module constants
  (`_ALL_DOCS_KEY`, `_CONTENT_HASHES_KEY`) **after** the functions that use them
  (works due to late binding, but harms readability) — and they duplicated the same
  constants in `ingest/policies.py:20-21`. ✅ **fixed in branch 3** — centralized in
  `ingest/keys.py` (key strings unchanged; no data migration needed).
- **I-3** `allowed_hosts` (config) is only used for the SSRF allowlist; despite the
  name, no `TrustedHostMiddleware` is installed, so it does **not** validate the HTTP
  Host header. Rename or add the middleware to avoid confusion.
- **I-4** `lru_cache` on `get_settings`/`get_llm`/`get_embeddings`/`get_redis` means
  config changes require process restart and tests must call `.cache_clear()` (some do).
  Fine for prod; document it.
- **I-5** Complexity is healthy: radon CC all A/B except `retrieve_context` (C, 12);
  maintainability index "A" across the board. No action required.
- **I-6** Docs are strong (36 KB README, CONTRIBUTING, CHANGELOG, MIT LICENSE). Consider
  documenting the required `OPENAI_API_KEY` for running tests and the provider→dependency
  matrix.

---

## 4. Test & Coverage Results

**Out-of-the-box (commit `f66d369`, deps from `requirements*.txt` only):**

```
8 failed, 129 passed — 96% line coverage
```

| Failing test | Root cause | Class |
|---|---|---|
| `test_adapters.py::test_google_provider` | `langchain-google-genai` not declared | H-2 |
| `test_adapters.py::test_google_provider_missing_key_raises` | import before key check | H-2 / L-3 |
| `test_adapters.py::test_alias_gemini_to_google` | missing google dep | H-2 |
| `test_adapters.py::test_huggingface_provider` | optional `langchain-huggingface` absent; test doesn't skip | env gap |
| `test_api.py::test_ready_all_deps_ok` | test forgot to mock `main.get_redis` → needs live Redis | M-1-adjacent |
| `test_rate_limiter.py::test_request_within_limit_succeeds` | patch scope bug (M-1) + real-Redis cleanup | M-1 |
| `test_rate_limiter.py::test_request_exceeds_limit_returns_429` | patch scope bug → fail-open | M-1 |
| `test_rate_limiter.py::test_different_ips_have_separate_limits` | patch scope bug → fail-open | M-1 |

**After demo fixes (branch `audit/low-risk-fixes`, google/hf deps installed):**

```
144 passed, 0 failed — 97% line coverage
```

> **Coverage caveat:** the 96–97% figure overstates safety. The LLM call path
> (`_get_chat → get_llm → ChatOpenAI.invoke`) is mocked in every test, which is exactly
> why C-1 (a guaranteed runtime crash) carried 96% coverage. Add at least one
> integration test that drives the compiled graph with a fake-but-real LLM object.

Raw logs: [`logs/pytest.log`](logs/pytest.log) (pre-fix),
[`logs/pytest-final.log`](logs/pytest-final.log) (post-fix),
coverage XML: [`coverage.xml`](coverage.xml) / [`coverage-postfix.xml`](coverage-postfix.xml).

---

## 5. Automated Tool Evidence

| Tool | Result | Artifact |
|---|---|---|
| **ruff** (lint) | ✅ All checks passed | [`logs/ruff-check.txt`](logs/ruff-check.txt), [`ruff.sarif`](ruff.sarif) |
| **ruff format --check** | ✅ 45 files already formatted | [`logs/ruff-format.txt`](logs/ruff-format.txt) |
| **bandit** (SAST) | ✅ 0 issues (incl. low; md5 correctly `usedforsecurity=False`) | [`bandit.json`](bandit.json), [`logs/bandit.txt`](logs/bandit.txt) |
| **pip-audit** (deps) | ⚠️ 1 vuln: **chromadb 1.5.9 → CVE-2026-45829** | [`pip-audit.json`](pip-audit.json), [`logs/pip-audit-env.txt`](logs/pip-audit-env.txt) |
| **radon cc / mi** (complexity) | ✅ All A/B + one C; MI all "A" | [`logs/radon-cc.txt`](logs/radon-cc.txt), [`logs/radon-mi.txt`](logs/radon-mi.txt) |
| **secret scan** (regex + git history) | ✅ No real secrets; `.env` history is placeholders only | [`logs/secret-scan.txt`](logs/secret-scan.txt) |

### Dependency vulnerability detail

**`chromadb==1.5.9` — CVE-2026-45829 (GHSA-f4j7-r4q5-qw2c)** — *pre-authentication code
injection*: an unauthenticated attacker can run arbitrary code on a Chroma **server** by
sending a malicious model repository with `trust_remote_code=true` to the collections
endpoint. **No fixed version is published yet** (`fix_versions: []`).

- **Exposure in this app:** Chroma is used as an **embedded/persistent local store**
  (`langchain_chroma.Chroma(persist_directory=…)`), not as a network server, so the
  remote attack surface is limited *as currently deployed*.
- **Action:** do **not** expose the Chroma server API on the network; pin/track the
  advisory and upgrade as soon as a patched release ships; if a server mode is ever
  introduced, disable `trust_remote_code` and require auth.

---

## 6. Action Plan / Roadmap

### Short-term (quick wins, ≤1 day) — delivered across the two demo branches
- ✅ C-1 `get_llm` parameters (P0, crash fix). *(branch 1)*
- ✅ H-2 add/pin LangChain deps (P0). *(branch 1)*
- ✅ H-3 add Redis service + explicit env to CI `test` job (P0). *(branch 2)*
- ✅ H-1 `allow_redirects=False` *(branch 1)* **and** DNS-resolution check *(branch 2)*.
- ✅ L-1 untrack `.env`/`.coverage` + `.gitignore` them (P1). *(branches 1+2)*
- ✅ M-1 fix rate-limiter test scope; ✅ readiness test Redis mock (P1). *(branch 1)*
- ✅ M-2 source metadata; ✅ L-2 `removesuffix`; ✅ L-3 key-check ordering. *(branch 1)*

### Medium-term (1–2 weeks)
- ✅ M-3 generic 5xx responses (stop leaking `str(exc)`). *(branch 3)*
- ✅ M-4 namespace + validate `X-User-Id` for memory *(branch 3)*; ☐ add real auth for
  `/chat` if memory is sensitive (follow-up).
- ✅ Add an **integration test** that compiles the graph and invokes it through the real
  `get_llm` path (not a mocked `_get_chat`) so the real wiring is covered. *(branch 5)*
- ☐ Make `langchain-huggingface` tests `skipif` when the optional package is absent.

### Long-term (architecture)
- ✅ M-5 separate synthesized/self-ingested content from authoritative documents
  (distinct collection + learning-mode-only retrieval). *(branch 4)* Review-workflow /
  response labelling remain optional follow-ups.
- ☐ Confirm Chroma deployment model and add a network-exposure guardrail; track
  CVE-2026-45829 for a patched release.
- ☐ Consider a typed Redis repository layer (mirroring `VectorStoreRepository`) to
  centralize key naming/namespacing and prevent keyspace collisions.

---

## 7. Fixes Delivered (five stacked branches)

Five stacked local branches implement the remediations and add regression tests, taking
the suite from **129 passing / 8 failing** to **162 passing / 0 failing** at **97.8%**
coverage. Every Critical/High/Medium finding and the informational cleanups are now
addressed; only optional follow-ups remain (review workflow for synthesized content,
real `/chat` auth, and tracking the external chromadb CVE). Each branch is attached as a
patch and applies cleanly onto the previous one (apply order: 1 → 5).

### Branch 1 — `audit/low-risk-fixes` (off `main`)
- **Patch:** [`audit-low-risk-fixes.patch`](audit-low-risk-fixes.patch) — `git apply audit-low-risk-fixes.patch`.
- **PR draft:** [`PR_DRAFT.md`](PR_DRAFT.md).
- **Files:** `utils/llm_adapter.py`, `ingest/policies.py`,
  `graph/nodes/retrieve_context.py`, `requirements.txt`, `tests/test_api.py`,
  `tests/test_rate_limiter.py`, new `tests/test_audit_fixes.py`, untrack `.coverage`.
- Covers: C-1, H-1 (redirect), H-2, M-1, M-2, L-2, L-3.
- **Validation:** `ruff` clean, **144 passed / 0 failed**, 97% coverage.

### Branch 5 — `audit/graph-integration-test` (off branch 4)
- **Patch:** [`audit-graph-integration-test.patch`](audit-graph-integration-test.patch);
  **PR draft:** [`PR_DRAFT_5.md`](PR_DRAFT_5.md).
- **Files:** new `tests/test_graph_integration.py`.
- Covers: the missing integration coverage that allowed C-1 to hide behind mocks.
- **Validation:** **162 passed / 0 failed**, 97.8% coverage.

### Branch 4 — `audit/synthesized-isolation` (off branch 3)
- **Patch:** [`audit-synthesized-isolation.patch`](audit-synthesized-isolation.patch);
  **PR draft:** [`PR_DRAFT_4.md`](PR_DRAFT_4.md).
- **Files:** `config.py`, `db/vector.py`, `graph/nodes/self_ingest.py`,
  `graph/nodes/retrieve_context.py`, `tests/test_graph_nodes.py`, new
  `tests/test_synthesized_isolation.py`.
- Covers: M-5.
- **Validation:** **161 passed / 0 failed**.

### Branch 3 — `audit/hardening-batch-2` (off branch 2)
- **Patch:** [`audit-hardening-batch-2.patch`](audit-hardening-batch-2.patch) — apply
  **after** branches 1 and 2; verified to apply cleanly onto `audit/ci-and-ssrf-hardening`.
- **PR draft:** [`PR_DRAFT_3.md`](PR_DRAFT_3.md).
- **Files:** `main.py`, `controllers/chat_controller.py`,
  `controllers/ingest_controller.py`, `db/redis_client.py`, `graph/nodes/load_memory.py`,
  `graph/nodes/store_memory.py`, `db/vector.py`, `graph/nodes/__init__.py`, new
  `ingest/keys.py`, `ingest/policies.py`, `tests/test_main.py`, new `tests/test_audit_fixes_2.py`.
- Covers: M-3, M-4, I-1, I-2.
- **Validation:** `ruff` clean, `ruff format` clean, **157 passed / 0 failed**, 98% coverage.

### Branch 2 — `audit/ci-and-ssrf-hardening` (off branch 1)
- **Patch:** [`audit-ci-and-ssrf-hardening.patch`](audit-ci-and-ssrf-hardening.patch) —
  apply **after** branch 1 (`git apply audit-ci-and-ssrf-hardening.patch`); verified to
  apply cleanly onto `audit/low-risk-fixes`.
- **PR draft:** [`PR_DRAFT_2.md`](PR_DRAFT_2.md).
- **Files:** `utils/security.py` (DNS-resolution SSRF guard), `tests/test_security.py`
  (+4 DNS-rebinding tests), `tests/conftest.py` (hermetic DNS mock for ingest),
  `.github/workflows/ci.yml` (Redis service + explicit env), `.gitignore`, untrack `.env`.
- Covers: H-1 (DNS-rebinding), H-3, L-1 completion.
- **Validation:** `ruff` clean, `ruff format` clean, **148 passed / 0 failed**, 97% coverage.

New regression tests:
1. `get_llm` forwards `temperature`/`max_tokens` (guards C-1). *(branch 1)*
2. `google` provider raises `ValueError` (not `ImportError`) on missing key (L-3). *(branch 1)*
3. `_source_of` prefers `source_file`, falls back to `source` (M-2). *(branch 1)*
4. `doc_id` from `"app.pdf"` → `"app"` (L-2). *(branch 1)*
5. Download does **not** follow a redirect to `169.254.169.254` (H-1). *(branch 1)*
6. Public host resolving to `169.254.169.254` / RFC1918 is blocked; unresolvable host
   fails closed; explicitly allowlisted host skips DNS (H-1 DNS-rebinding). *(branch 2)*

---

## 8. Appendix: Commands & Environment

**Environment** (`logs/environment.txt`):

```
os: Linux x86_64    python: 3.10.12 (venv via uv)
ruff 0.15.15   bandit 1.9.4   pip-audit 2.10.0   radon 6.0.1   pytest 9.0.3
```

**Commands executed (representative):**

```bash
# setup
uv venv .venv --python 3.10 && . .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt httpx
# (to reproduce the 4 google/hf failures' root cause)
uv pip install langchain-google-genai langchain-huggingface

# tests + coverage
pytest --cov=. --cov-report=xml --cov-report=term-missing -v

# automated analysis
ruff check . ; ruff check . --output-format=sarif > ruff.sarif
ruff format --check .
bandit -r . -x ./tests,./.venv -f json -o bandit.json
pip-audit --format=json > pip-audit.json        # audited installed env (sandbox lacks ensurepip)
radon cc -s -n B . ; radon mi -s .
detect-secrets / regex secret scan + git log -p --all -- .env
```

> **Scope note on secrets:** the project requires `OPENAI_API_KEY` (and provider keys)
> to run; per the engagement rules no real credentials were requested or used. Tests
> were run with placeholder keys and `EMBEDDING_PROVIDER=fastembed` to avoid external
> calls. Where credentials are required, supply them via environment variables / a
> secrets manager — never commit them (see L-1).
