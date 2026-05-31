# chat-bot — Implementation Plan (9 items)

**Date:** 2026-05-31 · **Scope:** top-5 proposals + 4 honorable mentions · **Target app version after all phases:** 2.4.0
**Companion to:** `improvement-proposals.md`, `docs/audit/web_UX_SPEC.md`

---

## 0. Global conventions (apply to every item)

- **Config-first & backward-compatible.** Every behavior change lands behind a `config.Settings` flag; defaults preserve today's behavior unless a change is explicitly an improvement that can't regress (and is covered by tests).
- **Hermetic tests, 95% gate.** New code ships with `pytest` unit/contract tests using the existing `conftest.py` fixtures (`fake_redis`, `vectorstore`, `ingest_env`, pdf fixtures). Keep `--cov-fail-under=95`, `ruff check`, `ruff format --check` green. No live network in the default suite.
- **Two run paths must stay in sync.** Anything added to the LangGraph (`graph/builder.py`) must also be reflected in the **streaming** path (`services/chat_service.stream_conversation`), which runs nodes manually.
- **Docs per item.** Update `README.md`, `CHANGELOG.md` (`[2.4.0]`), `PTD.md`, `.env.example` as part of each item's "definition of done."

### Phasing (dependency-ordered)

| Phase | Items | Theme |
|------|-------|-------|
| **1** | #14 resilience · #1 query rewriting · #19 regression test + eval CI | Quality core + the harness that proves it |
| **2** | #2 groundedness · #3 feedback loop | Trust substance + improvement flywheel |
| **3** | #4 durable ingestion · #5 persona config | Reliability + adoptability |
| **4** | Hybrid retrieval + rerank · #29 reviewer UI | Advanced quality (measured) + finishing the review feature |

Rationale for order: #14 hardens every LLM call that #1/#2 will add; #19 must exist *before* #1 so we can prove the lift and prevent silent regressions; hybrid/rerank is last because #19 gates whether it's worth its complexity.

### Consolidated additions (reference)

**New `config.Settings` keys** (grouped):
```
# Retrieval
query_rewrite_enabled: bool = True
groundedness_enabled: bool = True
groundedness_mode: str = "heuristic"      # heuristic | llm
groundedness_min_score: float = 0.5
strict_refuse_on_ungrounded: bool = True
retrieval_strategy: str = "mmr"           # mmr | hybrid | hybrid_rerank
# Resilience
provider_max_retries: int = 3
provider_retry_base_delay: float = 0.5
circuit_breaker_enabled: bool = True
cb_failure_threshold: int = 5
cb_reset_seconds: int = 30
# Ingestion
ingest_mode: str = "inline"               # inline | queue
ingest_max_attempts: int = 3
# Persona / branding
assistant_name: str = "our company's assistant"
knowledge_domain: str = ""                # e.g. "returns & shipping policy"
escalation_message: str = "Please contact support."
```
**New `graph/state.py` fields:** `search_query: str`, `grounded: str`, `grounded_score: float`.
**New `ChatMeta` fields (`schemas/responses.py`):** `grounded: str | None`, `grounded_score: float | None`.
**New deps:** `tenacity` (#14, tiny) · `rank-bm25` (hybrid) · reranker dep TBD (hybrid, optional).

---

## Phase 1

### #14 — Provider retry/backoff + circuit breaker

**Objective.** A transient `429`/`5xx`/timeout from an LLM or embedding provider must not fail a turn.

**Design.** New `utils/resilience.py` exposing `@resilient_call` (tenacity exponential backoff, retry only on transient errors: `TimeoutError`, connection errors, HTTP 429/5xx wrapped exceptions) plus a small in-process `CircuitBreaker` (open after `cb_failure_threshold` consecutive failures, half-open after `cb_reset_seconds`). Wrap the **synchronous** LLM `.invoke()` calls (`generate_answer`, `summarize`, and the new condense/verify calls). For **streaming** `.stream()`, retry only the *initial connection* (before any token is yielded) — once tokens flow we cannot safely replay; document this.

**Files.** New `utils/resilience.py`; touch `graph/nodes/generate_answer.py`, `graph/nodes/summarize.py`, `services/chat_service.py` (stream pre-roll), `config.py`, `requirements.txt` (`tenacity`).

**Tests** (`tests/test_resilience.py`): invoke that fails twice then succeeds → retried and returns; exceeds `max_retries` → raises; circuit opens after threshold (subsequent calls fast-fail) and half-opens after a monkeypatched clock advance; non-transient error (e.g. `ValueError`) is **not** retried.

**Acceptance.** A mocked provider 429 on the first attempt yields a successful chat turn; persistent failures surface as the existing 500/`error` SSE; opened circuit fast-fails without hammering the provider.

**Risks/mitigations.** Masking real outages → cap retries + circuit breaker + structured logging of retries with `correlation_id`. Streaming mid-flight failure still ends the stream gracefully (existing `error` frame). **Effort: S.**

---

### #1 — Context-aware query rewriting (condense)

**Objective.** Retrieve on a self-contained query derived from conversation context, not the raw last message.

**Design.** New node `graph/nodes/condense_query.py::condense_query(state) -> {"search_query": ...}`:
- If no prior context (`not state.get("messages") and not state.get("summary")`) → `search_query = question` (no LLM call).
- Else call `get_llm(temperature=0, max_tokens=64)` with a new `prompts/condense.py::build_condense_prompt(summary, history, question)` → *"Rewrite the user's question as a standalone search query using the conversation. Output only the query."* Wrap the call in `@resilient_call` (#14).
- Gated by `query_rewrite_enabled` (else pass-through).

**Wiring.**
- `graph/builder.py`: `START → load_memory → condense_query → retrieve_context → generate_answer → …`.
- `services/chat_service.stream_conversation`: add `state.update(condense_query(state))` after `load_memory`, before `retrieve_context`.
- `graph/nodes/retrieve_context.py`: `query = state.get("search_query") or state["question"]`; use `query` for `similarity_search*`/MMR. **Generation still uses `state["question"]`** (and citations' snippets are unaffected).

**Files.** New `graph/nodes/condense_query.py`, `prompts/condense.py`; touch `graph/builder.py`, `services/chat_service.py`, `graph/nodes/retrieve_context.py`, `graph/state.py`, `config.py`.

**Tests** (`tests/test_graph_nodes.py` / new `test_condense.py`): first turn → `search_query == question`, no LLM call; with history → LLM-rewritten query is what `retrieve_context` searches on (assert the vectorstore mock was called with the rewritten string, not the raw question); flag off → pass-through. Add a multi-turn case proving a pronoun follow-up retrieves the right doc on a seeded corpus (ties to #19).

**Acceptance.** A two-turn exchange where turn 2 is elliptical ("and for damaged items?") retrieves the correct chunk and does **not** falsely refuse in strict mode; first-turn latency unchanged (no extra call).

**Risks/mitigations.** Extra short LLM call per multi-turn message (latency/cost) → first-turn skip, 64-token cap, `query_rewrite_enabled`, optional cache keyed on `(hash(summary), question)`. Over-rewriting → keep prompt minimal and temperature 0. **Effort: S.**

---

### #19 — Hermetic retrieval-regression test + opt-in eval CI

**Objective.** Prevent silent retrieval-quality regressions; make the RAGAS harness runnable on demand without breaking hermetic CI.

**Design — hermetic regression test.** `tests/test_retrieval_regression.py`: build a temp Chroma using the **real FastEmbed** model already used in CI (`BAAI/bge-small-en-v1.5`, deterministic, offline once cached). Seed ~6–8 labeled chunks (distinct topics: returns/shipping/refunds/privacy/exchange/warranty). For ~8 `(query → expected doc_id)` pairs, assert the expected chunk is in `top_k` (recall@k) and `best_score` clears a floor. Mark `@pytest.mark.retrieval` so it can be selected/deselected; keep it in the default run if it stays fast (<a few s).

**Design — opt-in eval CI.** New workflow `.github/workflows/eval.yml` triggered by `workflow_dispatch` + weekly `schedule` (never on PRs). Steps: install `requirements.txt` + `requirements-eval.txt`, seed a corpus, run `eval/run_ragas.py --output report.json` using a repo secret `OPENAI_API_KEY` (or a configured judge), upload the report artifact, and optionally fail if a metric drops below a floor. Keeps the PR pipeline hermetic and cost-free.

**Files.** New `tests/test_retrieval_regression.py`, `.github/workflows/eval.yml`; touch `pyproject.toml` (register the `retrieval` marker), `eval/README.md` (document the CI job).

**Tests/Acceptance.** The regression test passes on `main` and **fails** if `top_k`/threshold/embedding settings are detuned (verify by temporarily lowering `top_k` locally). The eval workflow runs green via manual dispatch.

**Risks/mitigations.** FastEmbed model fetch on first CI run (already incurred today) → cache the model dir. Mild nondeterminism → assert membership in top-k + score floors, not exact ordering. **Effort: S–M.**

---

## Phase 2

### #2 — Groundedness / faithfulness verification

**Objective.** Expose a real signal for "is the answer supported by the retrieved chunks," and let strict mode act on it.

**Design.** New node `graph/nodes/verify_answer.py::verify_answer(state)` running after `generate_answer`, only when `docs` are present and `groundedness_enabled`:
- **`heuristic` mode (default, no extra call):** sentence-level overlap of `last_answer` against `docs` (normalized token Jaccard / embedding-free); `grounded_score` = fraction of answer sentences supported; bucket → `supported|partial|unsupported` via `groundedness_min_score`.
- **`llm` mode:** one `get_llm` JSON-judge call (wrapped in #14) → `{grounded: bool, unsupported_claims: []}`.
- **Strict enforcement:** if `chat_mode == "strict"` and verdict is `unsupported` and `strict_refuse_on_ungrounded` → replace `last_answer` with the canonical "Not in the knowledge base" refusal and clear `sources` (turns a subtle hallucination into the web spec's refusal card). In `open`/`learning`, keep the answer but set `meta.grounded` so the UI downgrades the confidence badge.

**Wiring.** `graph/builder.py`: `generate_answer → verify_answer → self_ingest`. `stream_conversation`: run `verify_answer` post-assembly; since tokens already streamed, surface `grounded` in the `done` meta (document that strict-refusal override applies to the *stored* answer + meta, not retroactively to streamed tokens — strict's pre-retrieval gate already blocks the common no-doc case).

**Files.** New `graph/nodes/verify_answer.py`, `prompts/verify.py` (llm tier); touch `graph/builder.py`, `services/chat_service.py` (both paths + `meta`), `graph/state.py`, `schemas/responses.py` (`ChatMeta.grounded`, `grounded_score`), `config.py`.

**Tests** (`tests/test_verify.py`): heuristic flags an answer with no overlap as `unsupported` and a faithful one as `supported`; strict + unsupported → answer replaced by refusal and `sources == []`; open + unsupported → answer retained, `meta.grounded == "unsupported"`; llm mode parsed from mocked JSON; flag off → no-op. API test: `meta.grounded` serialized in `ChatResponse`.

**Acceptance.** Confidence badge now reflects answer-support, not just retrieval similarity; a planted hallucination in strict mode is converted to a refusal.

**Risks/mitigations.** Heuristic false +/- → tune `groundedness_min_score`, default heuristic (cheap) with llm tier opt-in; latency/cost of llm tier behind config. **Effort: S–M.**

---

### #3 — Persistent feedback + closed quality loop

**Objective.** Capture 👍/👎 (+reason) on answers, store them, and feed thumbs-down into the review queue / RAGAS golden set.

**Design.** Mirror the existing `review` feature's shape.
- `schemas/feedback.py`: `FeedbackRequest {correlation_id?: str, rating: Literal["up","down"], reason?: str, question?: str, answer?: str}`, `FeedbackResponse`, `FeedbackListResponse`.
- `feedback/keys.py`: `FEEDBACK_IDS_KEY`, `feedback_key(id)`.
- `services/feedback_service.py`: `record(...)` (id = uuid or hash, store hash + index set, optional TTL), `list_feedback(rating, limit, cursor)`, `export_downvoted_to_golden(path)` (appends `{question, ground_truth?}` to `eval/golden.jsonl`).
- `controllers/v1/feedback.py`: `POST /api/v1/feedback` (**open** to end users; protected by the existing per-IP rate limiter), `GET /api/v1/feedback?rating=down` (**`require_api_key`**, like review/ingest). Capture `correlation_id` from `correlation_id_var`. Mount in `main.py` + add `feedback` OpenAPI tag.

**Files.** New `schemas/feedback.py`, `feedback/__init__.py`, `feedback/keys.py`, `services/feedback_service.py`, `controllers/v1/feedback.py`; optional `eval/import_feedback.py`; touch `main.py`.

**Tests** (`tests/test_feedback.py`): submit up/down stored + retrievable; list filters by rating and paginates; list requires API key when configured; export appends downvoted questions to a temp golden file. Reuse `fakeredis`.

**Acceptance.** A downvote with a reason is persisted and shows up in the moderator list; exporter grows the eval set. Unblocks the web spec's inline 👍/👎.

**Risks/mitigations.** Abuse on open submit → existing rate limiter + optional TTL/size cap; PII in reasons → run `guardrails.sanitize_output` on stored reason. **Effort: S–M.**

---

## Phase 3

### #4 — Durable, retryable ingestion

**Objective.** Survive restarts mid-ingest; retry transient failures; never duplicate.

**Design.** Introduce `ingest_mode`:
- **`inline`** (default) — current FastAPI `BackgroundTasks` behavior (keeps existing tests + small deployments unchanged).
- **`queue`** — controllers enqueue a job onto a Redis list (`ingest:queue`) with a JSON payload `{kind: "url"|"upload", file_name, ext, s3_url?|file_path?, attempts}`; a worker process consumes it.
- `ingest/queue.py`: `enqueue(job)`, `process_one(redis)` (BLPOP → run `process_policy`/`process_uploaded` → on transient failure re-enqueue with `attempts+1` up to `ingest_max_attempts`, else mark `failed`), and a per-`doc_id` lock (`SET NX`) for idempotency on top of the existing content-hash dedup.
- `ingest/worker.py`: `python -m ingest.worker` loop calling `process_one`.
- **Uploads in queue mode:** the controller writes the temp file to a shared `INGEST_INCOMING_DIR` (volume) instead of a process-local temp, so the worker can read it. `docker-compose.yml` gains a `worker` service (same image, `command: python -m ingest.worker`) and a shared volume.

**Files.** New `ingest/queue.py`, `ingest/worker.py`; touch `controllers/v1/ingest.py` (enqueue when `queue`), `config.py`, `docker-compose.yml`, `README.md`/`PTD.md` (ops).

**Tests** (`tests/test_ingest_queue.py`): `enqueue` pushes a job; `process_one` with a mocked `process_policy` consumes and marks `done`; a transient failure re-enqueues with incremented attempts and stops at `ingest_max_attempts` → `failed`; the `doc_id` lock prevents double-processing. Hermetic via `fakeredis` (test `process_one`, not a daemon).

**Acceptance.** Killing/restarting the API mid-ingest leaves the job on the queue and the worker completes it; a flaky download retries; re-running a completed job is a no-op (`skipped`/idempotent).

**Risks/mitigations.** New operational component + shared volume → keep `inline` default so nothing changes unless opted in; document the compose topology. Poison messages → attempt cap → `failed` with error recorded. **Effort: M.**

---

### #5 — Configurable persona, refusal copy & domain scoping

**Objective.** De-hardcode "our company"; make persona/domain/refusal configurable so the project is deployable as-is by anyone.

**Design.** Keep `prompts/answer.py` pure (no `config` import): `graph/nodes/generate_answer.build_chat_prompt` reads `get_settings()` and passes `assistant_name`, `knowledge_domain`, `escalation_message` into `build_answer_prompt(...)`, which threads them into the strict/open/learning builders. **Defaults reproduce today's exact strings** (incl. the strict refusal "…Please contact support.") so existing prompt assertions and behavior are unchanged. Optional Phase-3b: a length-capped, guardrail-checked per-request `system_hint` on `ChatRequest` for multi-persona deployments.

**Files.** Touch `config.py`, `prompts/answer.py`, `graph/nodes/generate_answer.py` (and `services/chat_service` build path); optional `schemas/chat.py` for `system_hint`.

**Tests** (`tests/test_graph_nodes.py`): default prompt text is byte-identical to today (existing tests pass unchanged); overriding `assistant_name`/`escalation_message` flows into the generated prompt; refusal line reflects `escalation_message`.

**Acceptance.** Setting three env vars rebrands the assistant and its refusal/escalation copy with zero code edits; out-of-the-box behavior is identical to current.

**Risks/mitigations.** Drift from tested defaults → assert defaults equal current strings. `system_hint` injection risk → cap length + run input guard. **Effort: S.**

---

## Phase 4

### Hybrid retrieval + reranking (gated by #19)

**Objective.** Recover lexical recall (acronyms/SKUs/exact phrases) and improve precision — **only if** #19 proves a lift.

**Design.** `retrieval_strategy` switch in `retrieve_context`:
- **`mmr`** (default) — unchanged.
- **`hybrid`** — dense (Chroma) + lexical (`rank-bm25` over chunk texts pulled via the collection) fused with **Reciprocal Rank Fusion (RRF)**.
- **`hybrid_rerank`** — hybrid candidates passed through a reranker. Reranker options, config-selectable: FastEmbed reranker (local, preferred for the zero-cloud story), an LLM reranker (reuse `get_llm`), or an external rerank API. Choose during spike; default off.

**Files.** New `ingest/retrieval.py` (or extend `graph/nodes/retrieve_context.py`) for BM25 index build + RRF; touch `config.py`, `requirements.txt` (`rank-bm25`, optional reranker), `db/vector.py` if chunk-text access helpers are needed.

**Tests.** RRF fusion is deterministic → unit-test fusion ordering; on the #19 seeded corpus, assert `hybrid` retrieves a keyword-only query (e.g. an exact code) that dense misses; reranker mocked. Compare recall@k vs. `mmr` in the regression test.

**Acceptance.** The #19 regression/eval shows measurable recall/precision lift on keyword-heavy queries with acceptable latency; otherwise we **don't ship it** (the value of #19 is the honest go/no-go).

**Risks/mitigations.** Complexity, new deps, BM25 index freshness on re-ingest (rebuild lazily / on ingest), latency from rerank → all behind `retrieval_strategy` (default `mmr`), adopted only with evidence. **Effort: M (higher uncertainty).**

---

### #29 — Reviewer UI for the `learning_review` queue

**Objective.** Give moderators a UI for the two-phase ingest queue (`/api/v1/review/*`) shipped earlier.

**Design (web/).** Add `listPending`/`approve`/`reject` to `web/src/lib/api.ts`; a `ReviewPanel.tsx` listing entries (`question`, `answer`, `best_score`, `created_at`) with Approve/Reject actions and optimistic removal; a header **Review** toggle (or `#/review` hash route) to open it. Add an **API-key field** (stored in `localStorage`, sent as `X-API-Key`) since review writes are gated by `require_api_key` when `REQUIRE_AUTH_FOR_INGEST=true`. Reuse existing button/surface styles (respect the design budget).

**Files.** New `web/src/components/ReviewPanel.tsx`; touch `web/src/lib/api.ts`, `web/src/App.tsx`, `web/src/types.ts`, `web/src/styles.css`, `web/README.md`.

**Tests/Acceptance.** `tsc -b && vite build` clean; `bun audit` clean; manual QA: pending entries list, Approve embeds (entry disappears, becomes retrievable in learning mode), Reject discards, API-key flows. (Project's web layer has no unit-test harness today; verification is build + manual, consistent with the UX spec's "manual QA" note.)

**Risks/mitigations.** Surfacing a privileged action in the client → key stored locally + only meaningful when `require_auth_for_ingest`; document that this panel is for operators. **Effort: M.**

---

## 1. Definition of done (every item)

- Behind a config flag with behavior-preserving default (where applicable).
- Hermetic tests added; full suite green at ≥95% coverage; `ruff check` + `format --check` clean.
- Streaming and non-streaming paths both updated.
- Docs updated (README/CHANGELOG `[2.4.0]`/PTD/.env.example) and OpenAPI tags/summaries for any new endpoint.
- For web items: `tsc -b && vite build` + `bun audit` clean.

## 2. Rollout

Ship each phase as its own PR (or one PR per item for #4/hybrid, which carry the most risk). Land Phase 1 first so #19 can gate everything after it. Bundle the small config-only surface (`#5`, `#14`) early to de-risk later phases.
</content>
