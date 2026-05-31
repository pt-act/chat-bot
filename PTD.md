# Project Technical Document (PTD) — `chat-bot`

Technical reference for engineers and operators. For consumer usage see
[`user_guidelines.md`](user_guidelines.md); for setup see [`README.md`](README.md).

**Version:** API 2.1.0 · **Runtime:** Python 3.10+ · **Last updated:** 2026-05-30

---

## 1. Purpose & scope

`chat-bot` is a Retrieval-Augmented Generation (RAG) chatbot service. It ingests PDF
policy documents into a vector store, answers questions grounded in those documents
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
- **Vector store:** ChromaDB (embedded/persistent) via `langchain-chroma`.
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
| Ingest | `ingest/policies.py`, `ingest/keys.py` | Download→chunk→embed→upsert; Redis key constants. |
| DB | `db/redis_client.py`, `db/vector.py` | Redis client + `memory_key`; Chroma accessors + `VectorStoreRepository`. |
| Adapters | `utils/llm_adapter.py`, `utils/embedding_adapter.py` | Provider selection. |
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

### Async ingest (`POST /api/v1/ingest`)
Writes an initial `queued` status to Redis, schedules `ingest_file` via FastAPI
`BackgroundTasks`, returns `202` + `Location`. `process_policy` downloads (SSRF-guarded,
no redirects), hashes, chunks (`RecursiveCharacterTextSplitter`), embeds, diffs against
prior chunk hashes, upserts changed chunks, and records `done`/`failed` status.

---

## 6. LangGraph pipeline

`State` (TypedDict, `total=False`): `user_id, question, messages, docs, summary,
sources, chat_mode, best_score, last_answer, self_ingested, lang, top_k, score_threshold`.

| Node | Reads | Writes | Notes |
|------|-------|--------|-------|
| `load_memory` | `user_id` | `messages`, `summary` | Reads `chat:memory:{user_id}` from Redis. |
| `retrieve_context` | `question`, `chat_mode`, `top_k`, `score_threshold` | `docs`, `sources`, `best_score` | Relevance gate (strict blocks below threshold) → **MMR** for diverse selection above threshold; learning also queries the synthesized store. Returns structured citations with scores joined from the scored candidate pool. |
| `generate_answer` | `summary`, `messages`, `docs`, `question`, `lang`, `chat_mode` | `messages`, `last_answer`, `lang` | Resolves language (auto/en/ar); calls the LLM. |
| `self_ingest` | `chat_mode`, `best_score`, `last_answer` | `self_ingested` | Learning-only; writes synthesized answers to the **separate** collection. |
| `summarize` | `messages` | `summary`, `messages` | Summarizes when ≥4 messages; truncates to last 6. |
| `store_memory` | `messages`, `summary`, `user_id` | — | Persists to Redis with TTL. |

Edges are linear: `START → load_memory → retrieve_context → generate_answer →
self_ingest → summarize → store_memory → END`.

---

## 7. Storage model

**Redis keys**
- `chat:memory:{user_id}` → JSON `{summary, messages[]}` (TTL `REDIS_TTL_SECONDS`).
- `rate_limit:{ip}:{window}` → counter (TTL = window + 1s).
- `ingest_status:{doc_id}` (hash), `doc_chunks:{doc_id}` (set of chunk hashes),
  `ingest:doc_ids` (set), `ingest:content_hashes` (hash) — centralized in `ingest/keys.py`.

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
| `CHAT_MODE` / `RETRIEVAL_SCORE_THRESHOLD` / `SELF_INGEST_MIN_LENGTH` | strict / 0.3 / 50 | RAG behavior. |
| `MAX_FILE_SIZE_MB` / `DOWNLOAD_TIMEOUT_SECONDS` | 50 / 30 | Ingest limits. |
| `API_KEY` / `REQUIRE_AUTH_FOR_INGEST` | "" / false | Ingest auth. |
| `CORS_ORIGINS` / `ALLOWED_HOSTS` / `TRUSTED_PROXIES` | [] / ["*"] / [] | CORS, SSRF allowlist, proxy-aware rate limiting. |
| `DEBUG` / `LOG_LEVEL` / `LOG_FORMAT` | false / INFO / text | Logging (`json` for aggregators). |

---

## 9. API surface

**v1 (typed envelopes, problem+json errors)**
- `POST /api/v1/chat` → `ChatResponse`
- `POST /api/v1/chat/stream` → `text/event-stream`
- `POST /api/v1/ingest` → `202 IngestResult` (+ `Location`)
- `GET /api/v1/ingest/status/{doc_id}` → `IngestResult`
- `GET /api/v1/ingest/docs?limit&cursor` → `DocsListResponse`
- `DELETE /api/v1/ingest/{doc_id}` → `DeleteResponse`

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

- **Framework:** pytest + pytest-cov. **Status:** 178 tests, ~97% line coverage, hermetic
  (fakeredis + mocked DNS/boundaries; no live Redis or network required).
- **Layers:** unit (nodes, adapters, security, schemas), API/contract (`test_api_v1.py`,
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
- **Synthesized isolation:** separate collection prevents model-generated content from
  surfacing as authoritative.
- **BackgroundTasks for async ingest:** simple, in-process; a Celery/RQ worker is the
  durability/scale upgrade path.
- **Rate limiter fails open:** prioritizes availability; pair with alerting on Redis loss.

---

## 16. Known limitations / roadmap

- **`chromadb 1.5.9` / CVE-2026-45829** (pre-auth RCE) — no upstream fix yet; mitigated by
  embedded (non-server) use. Track and upgrade when patched; never expose the Chroma
  server API on the network.
- **No `/chat` authentication** by default (identity is scoped, not authenticated).
- **In-process async ingest** — move to a worker/broker for durability and horizontal
  scale.
- **`retrieve_context` complexity** is creeping (CC ~14) — candidate for a small refactor.
- See [`README.md`](README.md) → Roadmap for the broader TODO list.
