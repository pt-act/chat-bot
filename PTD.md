# Project Technical Document (PTD) — `chat-bot`

Technical reference for engineers and operators. For consumer usage see
[`user_guidelines.md`](user_guidelines.md); for setup see [`README.md`](README.md).

**Version:** API 2.4.0 · **Runtime:** Python 3.10+ · **Last updated:** 2026-05-31

---

## 1. Purpose & scope

`chat-bot` is a Retrieval-Augmented Generation (RAG) chatbot service. It ingests documents
(PDF, TXT, Markdown, DOCX, HTML) into a vector store, answers questions grounded in those documents
(with selectable strictness), keeps per-user conversation memory, and exposes a versioned
HTTP API plus a reference web client.

**Lineage.** This builds on the fork's **v2.0.0** release (multi-mode chat, self-ingestion,
14-provider support, security hardening — see `CHANGELOG.md`). The **v2.1.0** work
documented here adds the versioned `/api/v1` contract, SSE streaming, structured
citations, async ingest, and the reference web client, and incorporates an independent
audit's fixes (the `get_llm` generation-params crash, SSRF redirect+DNS hardening, 5xx
information-leak, memory-key namespacing, synthesized-collection isolation, and CI/test
repairs). Retrieval continues to use the **score gate + MMR** design from v1.0.0 — MMR was
never dropped; citation scores are obtained alongside it (see §6, §15).

**v2.2.0** adds **European Portuguese (pt-PT)** as a third response language (alongside
English and Arabic) via a hybrid auto-detector (`utils/lang_detect.py`) — a fast,
dependency-free heuristic with a lingua statistical fallback for short ambiguous inputs
(see §6, §15). Additive and backward compatible: `lang` still defaults to `auto`.

**v2.3.0** adds multi-format ingestion (PDF/TXT/MD/DOCX/HTML) + local upload, guardrails,
the RAGAS harness, and the `learning_review` two-phase ingest mode.

**v2.4.0** is a quality/trust/reliability release (top-5 proposals + honorable mentions —
see `docs/audit/implementation-plan.md`). It adds two pipeline nodes — **`condense_query`**
(context-aware query rewriting, #1) and **`verify_answer`** (groundedness verification with
a strict-mode refusal gate, #2) — a **persistent feedback** endpoint feeding the review
queue / golden set (#3), **provider resilience** (retry/backoff + circuit breaker, #14),
**durable queue-based ingestion** with a worker (#4), **configurable persona/refusal copy**
(#5), optional **hybrid (dense + BM25) retrieval** behind `RETRIEVAL_STRATEGY` (Phase 4),
a hermetic **retrieval-regression test** + opt-in eval CI (#19), and a **reviewer UI** (#29).
Every change is behind a `config.Settings` flag whose default preserves prior behavior; the
pipeline is now **8 nodes** and the API contract is backward compatible.

---

## 2. High-level architecture

```
                       ┌─────────────────────────── FastAPI app (main.py) ───────────────────────────┐
   Client / Web SPA →  │  Middleware chain (outer→inner):                                              │
   (web/)              │   CorrelationId → RequestTiming → Deprecation → RateLimit → CORS             │
                       │  Routers:  /api/v1 (typed)   +   /api (legacy, deprecated)                    │
                       │  Errors:  RFC 9457 problem+json (middlewares/errors.py)                       │
                       └───────────┬───────────────────────────────────────┬─────────────────────────┘
                                   │ controllers/v1/{chat,ingest}           │ controllers/{chat,ingest}_controller
                                   ▼                                        ▼
                         services/chat_service        services/ingest_service → ingest/policies
                                   │                                        │
                       ┌───────────▼────────────┐                ┌──────────▼───────────┐
                       │ LangGraph pipeline      │                │ PDF download (SSRF-   │
                       │ (graph/builder + nodes) │                │ guarded) → chunk →    │
                       └───────────┬────────────┘                │ embed → upsert        │
                                   │                              └──────────┬───────────┘
                    ┌──────────────┼───────────────┐                        │
                    ▼              ▼               ▼                         ▼
              Redis (memory,  ChromaDB        LLM/Embeddings           ChromaDB (policies
              rate limits)   (policies +      (utils/llm_adapter,      collection) + Redis
                             synthesized)     embedding_adapter)       (status/hashes)
```

---

## 3. Tech stack

- **Web framework:** FastAPI / Starlette, Uvicorn.
- **Orchestration:** LangGraph (`StateGraph`) + LangChain.
- **LLM providers:** OpenAI-compatible (OpenAI, Ollama, OpenRouter, Together, Groq,
  DeepSeek, Fireworks, Mistral, vLLM, LM Studio, llama.cpp), Anthropic, Google Gemini —
  via `utils/llm_adapter`.
- **Embeddings:** OpenAI, FastEmbed, HuggingFace — via `utils/embedding_adapter`.
- **Language detection:** in-house heuristic + [lingua](https://github.com/pemistahl/lingua-py)
  (`lingua-language-detector`) EN/PT fallback — via `utils/lang_detect`.
- **Vector store:** ChromaDB (embedded/persistent) via `langchain-chroma`.
- **Document parsing:** pypdf (PDF), docx2txt (DOCX), beautifulsoup4 (HTML), stdlib (TXT/MD) — via `ingest/loaders.py`.
- **Cache/state:** Redis (conversation memory, rate-limit counters, ingest metadata).
- **Config:** pydantic-settings (`config.py`).
- **Web client:** Vite + React + TypeScript (`web/`).
- **Tooling:** pytest + coverage, ruff, bandit, pip-audit; GitHub Actions CI.

---

## 4. Components

| Area | Module(s) | Responsibility |
|------|-----------|----------------|
| App wiring | `main.py` | App, middleware order, router mounting (v1 + legacy), error handlers, health/ready. |
| Config | `config.py` | Typed settings + validators (provider keys, chat mode, CORS, embeddings). |
| Controllers (v1) | `controllers/v1/{chat,ingest}.py` | Typed envelopes, SSE streaming, async ingest, pagination. |
| Controllers (legacy) | `controllers/{chat,ingest}_controller.py` | Backward-compatible unversioned endpoints. |
| Services | `services/{chat,ingest}_service.py` | Orchestrate the graph / ingest pipeline; `stream_conversation`. |
| Graph | `graph/builder.py`, `graph/state.py`, `graph/nodes/*` | RAG pipeline nodes & wiring (8 nodes incl. `condense_query`, `verify_answer`). |
| Query rewrite | `graph/nodes/condense_query.py`, `prompts/condense.py` | Condense multi-turn follow-ups into a standalone search query before retrieval (#1). |
| Groundedness | `graph/nodes/verify_answer.py`, `prompts/verify.py` | Verify answer support vs. retrieved chunks; strict-mode refusal of unsupported answers (#2). |
| Resilience | `utils/resilience.py` | `resilient_invoke`/`@resilient_call`: tenacity retry on transient errors + in-process circuit breaker (#14). |
| Feedback | `services/feedback_service.py`, `feedback/keys.py`, `controllers/v1/feedback.py`, `schemas/feedback.py` | Persist 👍/👎 (+reason), list (API-key gated), export downvotes to the golden set (#3). |
| Ingest | `ingest/policies.py`, `ingest/loaders.py`, `ingest/keys.py` | URL download **or** local upload → shared `_run_ingest` (load→chunk→embed→upsert); multi-format loader registry (PDF/TXT/MD/DOCX/HTML); Redis key constants. |
| Durable ingest | `ingest/queue.py`, `ingest/worker.py` | `INGEST_MODE=queue`: Redis-list job queue + worker, retries + per-`doc_id` idempotency lock (#4). |
| Hybrid retrieval | `ingest/retrieval.py` | Dense + BM25 fused via RRF + rerank hook; gated by `RETRIEVAL_STRATEGY` (Phase 4). |
| DB | `db/redis_client.py`, `db/vector.py` | Redis client + `memory_key`; Chroma accessors + `VectorStoreRepository`. |
| Adapters | `utils/llm_adapter.py`, `utils/embedding_adapter.py` | Provider selection. |
| Language detection | `utils/lang_detect.py` | Resolve response language (EN/AR/PT): script + heuristic, lingua fallback. |
| Guardrails | `guardrails/{input_guard,output_guard,exceptions}.py` | Input prompt-injection blocking; output PII masking + length cap. Dependency-free, toggleable. |
| Review (learning) | `services/review_service.py`, `review/keys.py`, `controllers/v1/review.py` | Two-phase ingest: queue → approve(embed)/reject for synthesized answers. |
| Evaluation | `eval/run_ragas.py`, `eval/golden.jsonl` | Offline RAGAS harness (not in CI). |
| Security | `utils/security.py`, `middlewares/auth.py` | SSRF guard (DNS-aware); API-key dependency. |
| Middleware | `middlewares/{observability,rate_limiter,errors,logging_setup}.py` | Correlation id, timing, rate limiting + headers, problem+json, logging. |
| Schemas | `schemas/{chat,ingest,responses}.py` | Request validation + typed responses + problem model. |

---

## 5. Request lifecycle

### Synchronous chat (`POST /api/v1/chat`)
1. Middleware assigns/propagates `X-Correlation-Id`; rate limiter increments the per-IP
   window and sets `X-RateLimit-*`.
2. Controller validates `X-User-Id`, calls `chat_service.conversation(...)` with overrides.
3. `conversation` builds the initial `State` and invokes the compiled graph.
4. Graph runs: `load_memory → condense_query → retrieve_context → generate_answer →
   verify_answer → self_ingest → summarize → store_memory`.
5. Controller maps the result to `ChatResponse` (answer + structured `sources` + `meta`,
   incl. `grounded`/`grounded_score`).

### Streaming chat (`POST /api/v1/chat/stream`)
`stream_conversation` runs `load_memory` + `condense_query` + `retrieve_context`
synchronously, **streams** the LLM answer token-by-token (the initial connection is
retried via the resilience layer; once tokens flow it is not replayed), then runs
`verify_answer → self_ingest → summarize → store_memory` **after** the stream so memory
persists even though the client saw tokens first. Emits SSE `token`/`sources`/`done`
(and `error` on failure, with no internal text). A strict-mode groundedness refusal
applies to the stored answer + `done` meta, not to tokens already streamed.

### Async ingest (`POST /api/v1/ingest`, `POST /api/v1/ingest/upload`)
Writes an initial `queued` status to Redis and returns `202` + `Location`. With
`INGEST_MODE=inline` (default) it schedules a FastAPI `BackgroundTasks` job; with
`INGEST_MODE=queue` it pushes a job onto a Redis list that the `ingest.worker` process
consumes (durable across API restarts, retries transient failures up to
`INGEST_MAX_ATTEMPTS`, idempotent via a per-`doc_id` lock; uploads stage to the shared
`INGEST_INCOMING_DIR`). **URL path:** `process_policy` downloads
(SSRF-guarded, no redirects) to a temp file. **Upload path:** the controller validates the
extension (PDF also gets a `%PDF` magic check), streams the `multipart` file to a temp file
(`MAX_FILE_SIZE_MB` cap), then `process_uploaded` runs. Both pass the detected extension to
the shared `_run_ingest`, which loads the file via the format registry
(`ingest.loaders.load_documents` — PDF/TXT/MD/DOCX/HTML), then hashes, chunks
(`RecursiveCharacterTextSplitter`), embeds, diffs against prior chunk hashes, upserts
changed chunks, records `done`/`failed`, and removes the temp file.

---

## 6. LangGraph pipeline

`State` (TypedDict, `total=False`): `user_id, question, messages, docs, summary,
sources, chat_mode, best_score, last_answer, self_ingested, search_query, grounded,
grounded_score, lang, top_k, score_threshold`.

| Node | Reads | Writes | Notes |
|------|-------|--------|-------|
| `load_memory` | `user_id` | `messages`, `summary` | Reads `chat:memory:{user_id}` from Redis. |
| `condense_query` | `question`, `messages`, `summary` | `search_query` | #1. Pass-through on the first turn or when `QUERY_REWRITE_ENABLED=false` (no LLM call). Otherwise an LLM (temp 0, ≤64 tokens, resilient) rewrites the follow-up into a standalone query. |
| `retrieve_context` | `search_query`/`question`, `chat_mode`, `top_k`, `score_threshold` | `docs`, `sources`, `best_score` | Searches on `search_query` (falls back to `question`). Relevance gate (strict blocks below threshold) → `RETRIEVAL_STRATEGY` selection above threshold: **MMR** (default) or **hybrid** (dense + BM25 via RRF); learning also queries the synthesized store. Citations keep scores joined from the scored candidate pool. |
| `generate_answer` | `summary`, `messages`, `docs`, `question`, `lang`, `chat_mode` | `messages`, `last_answer`, `lang` | Resolves language via `utils.lang_detect`; builds the prompt with config-driven persona (`ASSISTANT_NAME`/`KNOWLEDGE_DOMAIN`/`ESCALATION_MESSAGE`); calls the LLM via the resilience layer (#14). |
| `verify_answer` | `last_answer`, `docs`, `chat_mode` | `grounded`, `grounded_score`, (`last_answer`, `sources`, `messages`) | #2. When docs present + `GROUNDEDNESS_ENABLED`: `heuristic` overlap (default) or `llm` judge → `supported`/`partial`/`unsupported`. Strict + `unsupported` + `STRICT_REFUSE_ON_UNGROUNDED` → replace answer with the refusal and clear sources. |
| `self_ingest` | `chat_mode`, `best_score`, `last_answer` | `self_ingested`, `pending_review`, `review_entry_id` | Learning modes only. `learning` embeds into the **separate** synthesized collection; `learning_review` **queues** the answer in Redis for review (no embedding). |
| `summarize` | `messages` | `summary`, `messages` | Summarizes when ≥4 messages; truncates to last 6. |
| `store_memory` | `messages`, `summary`, `user_id` | — | Persists to Redis with TTL. |

Edges are linear: `START → load_memory → condense_query → retrieve_context →
generate_answer → verify_answer → self_ingest → summarize → store_memory → END`. The
streaming path (`services/chat_service.stream_conversation`) runs the same nodes manually,
keeping both paths in sync.

**Language resolution (`utils/lang_detect.detect_language`).** Supported labels:
`English`, `Arabic`, `European Portuguese`. Explicit `lang` (`en`/`ar`/`pt`) maps directly
via `_LANG_LABELS`; `auto` runs a three-tier hybrid:
1. **Arabic** — Unicode script match (instant, definitive).
2. **Portuguese heuristic** (no dependency) — distinctive diacritics
   (`ã õ á é í ó ú â ê ô à ç`) are decisive; otherwise a Portuguese stopword-frequency
   ratio (>0.5 of tokens, NLTK `portuguese` list) decides for sentences of ≥4 words. A
   single shared token (e.g. English "no", also a PT stopword) cannot flip the verdict.
3. **lingua fallback** — only for short, unaccented, ambiguous fragments. The EN/PT
   detector is built once (`lru_cache`); on any error it defaults to English so a request
   never fails on detection. The resolved label is injected into the prompt and surfaced
   in `meta.lang`.

**Guardrails (`guardrails/`).** Two deterministic, dependency-free layers, toggleable via
settings. *Input* (`check_input`, run in `chat_service` before the graph) rejects
prompt-injection / jailbreak phrasings, raising `GuardrailViolation` (a `ValueError`) →
HTTP 400 / problem+json (sync) or a 400 `error` SSE frame before any token is streamed.
*Output* (`sanitize_output`, in `generate_answer` and on the assembled streaming answer)
optionally masks PII and enforces a length cap. PII masking on the stream applies to the
stored/persisted answer, not tokens already emitted.

**Learning review (`learning_review` mode, two-phase ingest).** The `learning_review` chat
mode behaves like `learning` but `self_ingest` writes the synthesized answer to a Redis
pending queue (`services/review_service.py`) instead of embedding it — unverified content
never reaches the vector store until approved. A moderator drives `/api/v1/review/*`;
**approve** embeds the entry into `synthesized_answers` (then retrievable in the learning
modes), **reject** discards it. Plain `learning` embeds immediately. Mode membership is
centralized in `config.LEARNING_MODES`.

---

## 7. Storage model

**Redis keys**
- `chat:memory:{user_id}` → JSON `{summary, messages[]}` (TTL `REDIS_TTL_SECONDS`).
- `rate_limit:{ip}:{window}` → counter (TTL = window + 1s).
- `ingest_status:{doc_id}` (hash), `doc_chunks:{doc_id}` (set of chunk hashes),
  `ingest:doc_ids` (set), `ingest:content_hashes` (hash) — centralized in `ingest/keys.py`.
- `review:pending:{entry_id}` (hash: question, answer, best_score, created_at, status),
  `review:pending_ids` (set) — learning-review queue, centralized in `review/keys.py`.
- `feedback:{id}` (hash: rating, reason, correlation_id, question, answer, created_at),
  `feedback:ids` (set) — persistent answer feedback, centralized in `feedback/keys.py`.
- `ingest:queue` (list of JSON jobs) + `ingest:lock:{doc_id}` (NX lock) — durable ingest
  queue (`INGEST_MODE=queue`), in `ingest/queue.py`.

**ChromaDB collections** (same persist dir, different names)
- `policies` (configurable) — authoritative ingested chunks. Metadata: `doc_id`,
  `source_file`, `file_hash`, `chunk_hash`, `chunk_index`, `page_number`, `version`.
- `synthesized_answers` — learning-mode synthesized content; consulted only in learning
  mode (isolation prevents knowledge-base poisoning).

---

## 8. Configuration (key env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL` | openai / gpt-4o-mini / "" | Model selection; base URL for OpenAI-compatible endpoints. |
| `OPENAI/ANTHROPIC/GOOGLE/GROQ_API_KEY` | "" | Provider credentials (validated when selected). |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | openai / text-embedding-3-small | Embedding backend. |
| `REDIS_HOST/PORT/PASSWORD` / `REDIS_TTL_SECONDS` | localhost/6379/""/86400 | Redis + memory TTL. |
| `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION` / `SYNTHESIZED_COLLECTION` | ./chroma_db / policies / synthesized_answers | Vector store. |
| `CHAT_MODE` / `RETRIEVAL_SCORE_THRESHOLD` / `SELF_INGEST_MIN_LENGTH` | strict / 0.3 / 50 | RAG behavior. `CHAT_MODE` ∈ `strict`/`open`/`learning`/`learning_review` (the last queues synthesized answers for review). |
| `RETRIEVAL_STRATEGY` | mmr | `mmr` (default) / `hybrid` (dense + BM25 via RRF) / `hybrid_rerank` (Phase 4). |
| `QUERY_REWRITE_ENABLED` | true | Context-aware query rewriting before retrieval (#1). |
| `GROUNDEDNESS_ENABLED` / `GROUNDEDNESS_MODE` / `GROUNDEDNESS_MIN_SCORE` / `STRICT_REFUSE_ON_UNGROUNDED` | true / heuristic / 0.5 / true | Groundedness verification + strict-mode refusal of unsupported answers (#2). |
| `PROVIDER_MAX_RETRIES` / `PROVIDER_RETRY_BASE_DELAY` / `CIRCUIT_BREAKER_ENABLED` / `CB_FAILURE_THRESHOLD` / `CB_RESET_SECONDS` | 3 / 0.5 / true / 5 / 30 | Provider retry/backoff + circuit breaker (#14). |
| `ASSISTANT_NAME` / `KNOWLEDGE_DOMAIN` / `ESCALATION_MESSAGE` | "our company" / "" / "Please contact support." | Configurable persona / domain / refusal copy; defaults reproduce prior prompt strings (#5). |
| `GUARDRAILS_ENABLED` / `GUARDRAILS_BLOCK_INJECTION` / `GUARDRAILS_MASK_PII` / `GUARDRAILS_MAX_ANSWER_CHARS` | true / true / false / 4000 | Input injection blocking; output PII masking + length cap. |
| `MAX_FILE_SIZE_MB` / `DOWNLOAD_TIMEOUT_SECONDS` | 50 / 30 | Ingest limits. |
| `INGEST_MODE` / `INGEST_MAX_ATTEMPTS` / `INGEST_INCOMING_DIR` | inline / 3 / ./ingest_incoming | Durable ingestion: `queue` enqueues to Redis for the worker; retries + staged-upload dir (#4). |
| `API_KEY` / `REQUIRE_AUTH_FOR_INGEST` | "" / false | Ingest auth (also gates `GET /feedback` and review listing). |
| `CORS_ORIGINS` / `ALLOWED_HOSTS` / `TRUSTED_PROXIES` | [] / ["*"] / [] | CORS, SSRF allowlist, proxy-aware rate limiting. |
| `DEBUG` / `LOG_LEVEL` / `LOG_FORMAT` | false / INFO / text | Logging (`json` for aggregators). |

---

## 9. API surface

**v1 (typed envelopes, problem+json errors)**
- `POST /api/v1/chat` → `ChatResponse`
- `POST /api/v1/chat/stream` → `text/event-stream`
- `POST /api/v1/ingest` → `202 IngestResult` (+ `Location`) — ingest from a remote URL
- `POST /api/v1/ingest/upload` → `202 IngestResult` (+ `Location`) — ingest an uploaded local document (PDF/TXT/MD/DOCX/HTML, `multipart/form-data`)
- `GET /api/v1/ingest/status/{doc_id}` → `IngestResult`
- `GET /api/v1/ingest/docs?limit&cursor` → `DocsListResponse`
- `DELETE /api/v1/ingest/{doc_id}` → `DeleteResponse`
- `GET /api/v1/review/pending?limit&cursor` → `PendingListResponse`
- `POST /api/v1/review/{entry_id}/approve` → `ReviewDecision` (embeds into synthesized store)
- `POST /api/v1/review/{entry_id}/reject` → `ReviewDecision` (discards)
- `POST /api/v1/feedback` → `201 FeedbackResponse` — open submission of 👍/👎 (#3)
- `GET /api/v1/feedback?rating&limit&cursor` → `FeedbackListResponse` (API-key gated)

**System:** `GET /health` (cached), `GET /ready` (live, 200/503), `GET /`.
**Legacy:** `/api/*` mirrors the above with the old envelope; responses carry
`Deprecation`/`Sunset`/`Link`. OpenAPI at `/docs`, `/redoc`, `/openapi.json`.

---

## 10. Security model

- **Error model:** problem+json everywhere; 5xx never echo internal text (detail logged
  with correlation id).
- **SSRF:** `validate_download_url` blocks private/loopback/link-local/reserved IPs,
  resolves DNS to defeat rebinding, and the downloader sets `allow_redirects=False`.
  `ALLOWED_HOSTS` is an explicit allowlist; `*` allows public hosts only.
- **Ingest auth:** `X-API-Key` dependency — `DELETE` always; others when
  `REQUIRE_AUTH_FOR_INGEST=true`.
- **Ingest path guard:** `_validate_ingest_path` (in `ingest/policies.py`) resolves symlinks
  and confines every file the pipeline opens (hashing + loaders) to the system temp dir or
  `INGEST_INCOMING_DIR`. Defense-in-depth against path-traversal / file-inclusion — relevant
  for queue mode, where `file_path` is carried in a Redis job.
- **Memory safety:** `X-User-Id` validated (`[A-Za-z0-9_.@-]{1,128}`) and namespaced
  (`chat:memory:`) so it cannot collide with operational keys.
- **Rate limiting:** per-IP sliding window in Redis, proxy-aware (`TRUSTED_PROXIES`),
  with `X-RateLimit-*` + `Retry-After`; fails open if Redis is down (availability choice).
- **CORS:** driven by `CORS_ORIGINS`; warns on `*`. Set explicit origins in production.

---

## 11. Observability

- **Correlation id:** `X-Correlation-Id` accepted or generated; propagated via a
  `contextvar` and injected into every log line; returned in responses and problem bodies.
- **Request timing:** method/path/status/duration logged per request.
- **Logging:** text or structured JSON (`LOG_FORMAT=json`) with rotating file handler.

---

## 12. Testing

- **Framework:** pytest + pytest-cov. **Status:** 300+ tests, ~97% line coverage, hermetic
  (fakeredis + mocked DNS/boundaries; no live Redis or network required). The RAGAS eval
  harness (`eval/`) is intentionally excluded — it needs an LLM judge and is non-deterministic.
- **Layers:** unit (nodes, adapters, security, schemas, language detection —
  `test_lang_detect.py`, guardrails — `test_guardrails.py`, learning review —
  `test_review.py`, resilience — `test_resilience.py`, query rewrite — `test_condense.py`,
  groundedness — `test_verify.py`, persona — `test_persona.py`, feedback —
  `test_feedback.py`, durable ingest — `test_ingest_queue.py`, hybrid retrieval —
  `test_hybrid_retrieval.py`), API/contract (`test_api_v1.py`, problem+json, deprecation,
  OpenAPI), streaming (`test_streaming.py`), async ingest + pagination
  (`test_async_ingest.py`), and an **end-to-end graph integration test**
  (`test_graph_integration.py`).
- **Retrieval regression (#19):** `test_retrieval_regression.py` (marked
  `@pytest.mark.retrieval`) seeds a tiny labeled corpus with the **real FastEmbed** model
  and asserts recall@k + a score floor; skips cleanly when the model can't be fetched.
- **Web:** `tsc -b` typecheck + `vite build`; `bun audit` clean.

---

## 13. CI/CD

GitHub Actions (`.github/workflows/ci.yml`), pinned action SHAs:
1. **security** — bandit + pip-audit.
2. **lint** — ruff check + format check.
3. **test** — provisions a `redis:7-alpine` service + explicit env; pytest with coverage
   gate.
4. **docker** — build + smoke test.

A separate **non-PR** workflow (`.github/workflows/eval.yml`, `workflow_dispatch` + weekly
`schedule`) seeds a corpus (`eval/seed_corpus.py`), runs the RAGAS harness, uploads the
report, and applies metric floors — keeping the PR pipeline hermetic and cost-free (#19).

---

## 14. Deployment

- **Docker Compose:** `docker-compose.yml` (api + **ingest worker** + redis, with
  `INGEST_MODE=queue` and a shared `ingest_incoming` volume), `.local`/`.test` variants.
- **Process:** `uvicorn main:app --host 0.0.0.0 --port 8000 --workers N`; durable ingestion
  adds a `python -m ingest.worker` process (one or more) consuming the Redis queue.
- **Web client:** build `web/` and serve `dist/` statically; configure `CORS_ORIGINS` or
  reverse-proxy `/api`.
- **SSE behind proxies:** endpoint sets `Cache-Control: no-cache` and
  `X-Accel-Buffering: no`; ensure the proxy does not buffer event streams.
- **Scaling:** memory/rate-limit state is in Redis (shared across workers). Health at
  `/health`, readiness at `/ready`.

---

## 15. Design decisions & trade-offs

- **Versioned API + legacy alias:** introduce `/api/v1` typed envelopes while keeping
  `/api` working (deprecated) — avoids breaking existing consumers.
- **problem+json app-wide:** one error contract is strictly better than three; applied to
  all routes.
- **MMR retained, scores joined (not either/or):** above-threshold retrieval uses MMR for
  diverse, non-redundant chunks (the documented v1.0.0 behavior — valuable given
  `chunk_overlap=100`, small `k`, and versioned ingestion). Per-citation relevance scores
  come from scoring the candidate pool once and joining by `chunk_hash`. An earlier change
  had replaced MMR with scored top-k to get scores; that was an unforced quality regression
  and has been reverted.
- **Hybrid language detection (heuristic first, lingua only when needed):** the fast,
  dependency-free heuristic resolves the overwhelming majority of inputs at negligible cost;
  the heavier statistical model is consulted only for short, unaccented, ambiguous fragments
  where the heuristic abstains. This balances latency against accuracy and keeps an explicit
  `lang` selector 100% reliable. Restricting lingua to EN/PT keeps it fast and prevents it
  guessing an unsupported language.
- **Synthesized isolation:** separate collection prevents model-generated content from
  surfacing as authoritative.
- **Two-phase learning ingest (review before embed):** model-synthesized answers are
  queued for human approval rather than embedded immediately, so unverified content cannot
  enter the vector store (and thus retrieval) without a human in the loop. The queue is
  Redis-only — embedding happens at approval — which keeps the synthesized collection clean
  and avoids embedding work for entries that get rejected.
- **Guardrails are lightweight, deterministic, and toggleable:** dependency-free heuristics
  (no model calls) keep the suite hermetic and latency negligible; tuned for precision over
  recall. They are a defense layer, not a complete solution. PII masking defaults off because
  a support assistant often legitimately returns contact emails.
- **RAGAS eval is offline, not CI-gated:** it judges answers with an LLM (key, network,
  non-deterministic), which is incompatible with the hermetic CI. It ships as a standalone
  harness with a golden set for manual/scheduled regression checks.
- **Ingestion durability is opt-in (`INGEST_MODE`):** `inline` `BackgroundTasks` stays the
  zero-ops default for small/single-process deployments; `queue` adds a Redis-list job + a
  worker process for crash-safety, retries, and idempotency on the value-critical KB path —
  reusing the existing Redis status + content-hash dedup rather than a new broker (#4).
- **Query rewriting before retrieval (#1):** generation was already context-aware while
  retrieval searched the raw last message; condensing the follow-up first fixes multi-turn
  recall (and false strict refusals) for one cheap, first-turn-skipped, flag-gated LLM call.
- **Groundedness gate, heuristic-first (#2):** a dependency-free overlap heuristic is the
  default (no extra call); an LLM judge is opt-in. Strict mode converts an `unsupported`
  answer into the existing refusal so a high-similarity-but-hallucinated answer can't ship
  under a confident badge.
- **Resilience wraps only synchronous calls + the stream pre-roll (#14):** mid-stream
  failures can't be safely replayed, so only the initial connection is retried; the circuit
  breaker counts transient failures only, so logic errors don't trip it.
- **Persona defaults are byte-identical (#5):** prompts stay config-free and pure; persona
  values are injected by `generate_answer`, with defaults reproducing the original strings
  so existing prompt assertions and behavior are unchanged.
- **Hybrid/rerank are scaffolding, default off (Phase 4):** `RETRIEVAL_STRATEGY` keeps `mmr`
  the default; hybrid (BM25 + RRF) and the rerank hook are adopted only once the regression
  test / eval prove a lift — the value of #19 is the honest go/no-go.
- **Rate limiter fails open:** prioritizes availability; pair with alerting on Redis loss.

---

## 16. Known limitations / roadmap

- **Retrieval quality is not validated against a live corpus.** The test suite is hermetic
  — ChromaDB and embeddings are mocked. Unit/contract tests verify *that* MMR is invoked
  and *that* citation scores are joined, but they do **not** measure real retrieval
  relevance or MMR diversity on actual documents. A live evaluation (e.g. RAGAS, or manual
  spot-checks against your corpus) is recommended before relying on answer quality, and
  after any change to chunking, `top_k`, `fetch_k`, or the embedding model.
- **`chromadb 1.5.9` / CVE-2026-45829** (pre-auth RCE) — no upstream fix yet; mitigated by
  embedded (non-server) use. Track and upgrade when patched; never expose the Chroma
  server API on the network.
- **No `/chat` authentication** by default (identity is scoped/validated, not
  authenticated). Gate behind auth if conversation memory is sensitive.
- **SSRF guard has a TOCTOU window.** `validate_download_url` resolves DNS at check time;
  the subsequent request resolves again and could differ. Combined with
  `allow_redirects=False` this is a strong mitigation, not airtight — pinning the validated
  IP for the connection would close it.
- **Rate limiter fails open.** If Redis is unavailable, requests are allowed (availability
  over enforcement). Pair with alerting on Redis loss; the open window is otherwise silent.
- **MMR tuning is defaulted.** `fetch_k = max(10, top_k*4)` and LangChain's `lambda_mult`
  default (0.5) are not yet configurable; extreme `top_k` or unusual corpora may want
  tuning. Score↔chunk join relies on `chunk_hash` (falls back to content) — a citation
  shows `score: null` if a selected chunk isn't in the scored candidate pool.
- **Async ingest is in-process by default** — `INGEST_MODE=inline` uses FastAPI
  `BackgroundTasks` (not durable across restarts). `INGEST_MODE=queue` adds the durable
  Redis-queue worker; enable it (and run the worker) for production-grade ingestion.
- **Groundedness heuristic is lexical.** Content-word overlap can mis-judge heavy paraphrase
  (false `unsupported`) or shared-vocabulary hallucinations (false `supported`); tune
  `GROUNDEDNESS_MIN_SCORE` per corpus or use the `llm` tier. The strict refusal on the
  streaming path corrects the stored answer/meta, not tokens already streamed.
- **Hybrid retrieval / reranking are unproven on your corpus** and off by default; the
  `rerank` hook is an identity passthrough until a concrete reranker is wired in. Validate a
  lift via the regression test / RAGAS before enabling `RETRIEVAL_STRATEGY=hybrid*`.
- **Feedback submission is open** (rate-limited only). Add a TTL/size cap if abuse is a
  concern; stored reasons are guardrail-sanitized but not authenticated to a user.
- **Auto language detection is statistical for unaccented input.** Very short, unaccented
  single tokens are inherently ambiguous between EN and PT; `auto` is high-accuracy, not
  guaranteed. Use an explicit `lang` for determinism. Adding a language requires extending
  `_LANG_LABELS`, the lingua language set, and the prompt guidance (currently EN/AR/PT only).
- **Guardrails are heuristic.** Tuned for precision; novel prompt-injection phrasings may
  slip through, and streaming PII masking applies only to the persisted answer, not tokens
  already sent. Treat them as one layer of defense.
- **RAGAS scores are non-deterministic and corpus/model-dependent.** Use as a regression
  signal across changes, not an absolute grade; the harness is not run in CI.
- **`retrieve_context` complexity** is CC 15 (radon) — a candidate for extracting the
  weak-match branch into a helper.
- See [`README.md`](README.md) → Roadmap and [`CHANGELOG.md`](CHANGELOG.md) `[2.2.0]`/`[2.1.0]`
  → Known limitations for the broader list.
