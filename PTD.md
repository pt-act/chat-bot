# Project Technical Document (PTD) — `chat-bot`

Technical reference for engineers and operators. For consumer usage see
[`user_guidelines.md`](user_guidelines.md); for setup see [`README.md`](README.md).

**Version:** API 2.3.0 · **Runtime:** Python 3.10+ · **Last updated:** 2026-05-31

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
| Graph | `graph/builder.py`, `graph/state.py`, `graph/nodes/*` | RAG pipeline nodes & wiring. |
| Ingest | `ingest/policies.py`, `ingest/loaders.py`, `ingest/keys.py` | URL download **or** local upload → shared `_run_ingest` (load→chunk→embed→upsert); multi-format loader registry (PDF/TXT/MD/DOCX/HTML); Redis key constants. |
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
4. Graph runs: `load_memory → retrieve_context → generate_answer → self_ingest →
   summarize → store_memory`.
5. Controller maps the result to `ChatResponse` (answer + structured `sources` + `meta`).

### Streaming chat (`POST /api/v1/chat/stream`)
`stream_conversation` runs `load_memory` + `retrieve_context` synchronously, **streams**
the LLM answer token-by-token (`get_llm(...).stream(prompt)` via the shared
`build_chat_prompt`), then runs `self_ingest → summarize → store_memory` **after** the
stream so memory persists even though the client saw tokens first. Emits SSE
`token`/`sources`/`done` (and `error` on failure, with no internal text).

### Async ingest (`POST /api/v1/ingest`, `POST /api/v1/ingest/upload`)
Writes an initial `queued` status to Redis, schedules a background task via FastAPI
`BackgroundTasks`, returns `202` + `Location`. **URL path:** `process_policy` downloads
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
sources, chat_mode, best_score, last_answer, self_ingested, lang, top_k, score_threshold`.

| Node | Reads | Writes | Notes |
|------|-------|--------|-------|
| `load_memory` | `user_id` | `messages`, `summary` | Reads `chat:memory:{user_id}` from Redis. |
| `retrieve_context` | `question`, `chat_mode`, `top_k`, `score_threshold` | `docs`, `sources`, `best_score` | Relevance gate (strict blocks below threshold) → **MMR** for diverse selection above threshold; learning also queries the synthesized store. Returns structured citations with scores joined from the scored candidate pool. |
| `generate_answer` | `summary`, `messages`, `docs`, `question`, `lang`, `chat_mode` | `messages`, `last_answer`, `lang` | Resolves language via `utils.lang_detect` — explicit `en`/`ar`/`pt` bypass detection, `auto` runs the hybrid detector (script → heuristic → lingua); calls the LLM. |
| `self_ingest` | `chat_mode`, `best_score`, `last_answer` | `self_ingested`, `pending_review`, `review_entry_id` | Learning modes only. `learning` embeds into the **separate** synthesized collection; `learning_review` **queues** the answer in Redis for review (no embedding). |
| `summarize` | `messages` | `summary`, `messages` | Summarizes when ≥4 messages; truncates to last 6. |
| `store_memory` | `messages`, `summary`, `user_id` | — | Persists to Redis with TTL. |

Edges are linear: `START → load_memory → retrieve_context → generate_answer →
self_ingest → summarize → store_memory → END`.

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
| `GUARDRAILS_ENABLED` / `GUARDRAILS_BLOCK_INJECTION` / `GUARDRAILS_MASK_PII` / `GUARDRAILS_MAX_ANSWER_CHARS` | true / true / false / 4000 | Input injection blocking; output PII masking + length cap. |
| `MAX_FILE_SIZE_MB` / `DOWNLOAD_TIMEOUT_SECONDS` | 50 / 30 | Ingest limits. |
| `API_KEY` / `REQUIRE_AUTH_FOR_INGEST` | "" / false | Ingest auth. |
| `CORS_ORIGINS` / `ALLOWED_HOSTS` / `TRUSTED_PROXIES` | [] / ["*"] / [] | CORS, SSRF allowlist, proxy-aware rate limiting. |
| `DEBUG` / `LOG_LEVEL` / `LOG_FORMAT` | false / INFO / text | Logging (`json` for aggregators). |

---

## 9. API surface

**v1 (typed envelopes, problem+json errors)**
- `POST /api/v1/chat` → `ChatResponse`
- `POST /api/v1/chat/stream` → `text/event-stream`
- `POST /api/v1/ingest` → `202 IngestResult` (+ `Location`) — ingest from a remote URL
- `POST /api/v1/ingest/upload` → `202 IngestResult` (+ `Location`) — ingest an uploaded local PDF (`multipart/form-data`)
- `GET /api/v1/ingest/status/{doc_id}` → `IngestResult`
- `GET /api/v1/ingest/docs?limit&cursor` → `DocsListResponse`
- `DELETE /api/v1/ingest/{doc_id}` → `DeleteResponse`
- `GET /api/v1/review/pending?limit&cursor` → `PendingListResponse`
- `POST /api/v1/review/{entry_id}/approve` → `ReviewDecision` (embeds into synthesized store)
- `POST /api/v1/review/{entry_id}/reject` → `ReviewDecision` (discards)

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

- **Framework:** pytest + pytest-cov. **Status:** 223 tests, ~97% line coverage, hermetic
  (fakeredis + mocked DNS/boundaries; no live Redis or network required). The RAGAS eval
  harness (`eval/`) is intentionally excluded — it needs an LLM judge and is non-deterministic.
- **Layers:** unit (nodes, adapters, security, schemas, language detection —
  `test_lang_detect.py`, guardrails — `test_guardrails.py`, learning review —
  `test_review.py`), API/contract (`test_api_v1.py`,
  problem+json, deprecation, OpenAPI), streaming (`test_streaming.py`), async ingest +
  pagination (`test_async_ingest.py`), and an **end-to-end graph integration test**
  (`test_graph_integration.py`) that drives the real `get_llm` path (regression guard for
  the original signature-mismatch crash).
- **Web:** `tsc -b` typecheck + `vite build`; `bun audit` clean.

---

## 13. CI/CD

GitHub Actions (`.github/workflows/ci.yml`), pinned action SHAs:
1. **security** — bandit + pip-audit.
2. **lint** — ruff check + format check.
3. **test** — provisions a `redis:7-alpine` service + explicit env; pytest with coverage
   gate.
4. **docker** — build + smoke test.

---

## 14. Deployment

- **Docker Compose:** `docker-compose.yml` (api + redis), `.local`/`.test` variants.
- **Process:** `uvicorn main:app --host 0.0.0.0 --port 8000 --workers N`.
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
- **BackgroundTasks for async ingest:** simple, in-process; a Celery/RQ worker is the
  durability/scale upgrade path.
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
- **In-process async ingest** — uses FastAPI `BackgroundTasks` (single process, not
  durable across restarts); move to a worker/broker (Celery/RQ) for durability and scale.
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
