# Changelog

All notable changes to the AI Chatbot Backend Service are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] — 2026-05-31

API ergonomics + a reference web client, plus fixes from an independent code-quality
audit. Backward compatible: the unversioned `/api/*` endpoints keep their existing
response shapes (now flagged deprecated); the new typed contract lives under `/api/v1`.

### Added

#### API contract (`/api/v1`)

- **Versioned API** under `/api/v1` with typed Pydantic response envelopes
  (`schemas/responses.py`): `ChatResponse` (`answer`, structured `sources[]`, `meta`),
  `IngestResult`, `DocsListResponse`, `DeleteResponse`, `DependencyHealth`.
- **RFC 9457 `application/problem+json`** error model applied application-wide
  (`middlewares/errors.py`) — replaces the three inconsistent prior error shapes.
- **Per-request controls** on `ChatRequest` (all optional): `mode` (strict|open|learning),
  `lang` (auto|en|ar), `top_k` (1–10), `score_threshold` (0–1) — override server defaults
  per call without changing config.
- **Structured citations** — each source carries `label`, `doc_id`, `score`, `page`,
  `snippet` (v1); legacy `/api/chat` keeps bare label strings.
- **SSE streaming** — `POST /api/v1/chat/stream` emits `token` → `sources` → `done`
  (and `error`) as Server-Sent Events; memory persists after the stream.
- **Async ingestion** — `POST /api/v1/ingest` returns `202` + `Location` and processes in
  the background (`BackgroundTasks`); poll `GET /api/v1/ingest/status/{doc_id}`.
- **Pagination** — `GET /api/v1/ingest/docs?limit&cursor` returns `total` + `next_cursor`.
- **Rate-limit headers** — `X-RateLimit-Limit/Remaining/Reset` on every response and
  `Retry-After` on `429`.
- **OpenAPI quality** — `response_model`, tags, summaries, and examples across routes;
  legacy `/api/*` responses carry `Deprecation`/`Sunset`/`Link` headers.

#### Reference web client (`web/`)

- **Vite + React + TypeScript SPA** — streaming chat (SSE) with a Stop button,
  per-request mode/language selectors, collapsible structured citations, **RTL/Arabic**
  rendering (logical CSS properties), accessibility (`aria-live`, keyboard send, focus
  rings, reduced-motion), and a `/health` status badge. Plain CSS; builds clean
  (`tsc -b && vite build`), `bun audit` clean.

#### Documentation

- **`user_guidelines.md`** (consumer guide) and **`PTD.md`** (project technical document);
  README updated for the v1 API, streaming, and web client; `docs/audit/` deliverables.

### Changed

- **App version** → `2.1.0`.
- **Conversation memory keys** namespaced to `chat:memory:{user_id}` and `X-User-Id`
  validated (`[A-Za-z0-9_.@-]{1,128}`) so caller-supplied ids cannot collide with
  operational keys.
- **Self-ingested (learning) content** now stored in a **separate** Chroma collection
  (`synthesized_answers`) and consulted only in learning mode — never in strict/open.
- **Ingest Redis key constants** centralized in `ingest/keys.py`.

### Fixed

- **Critical:** `get_llm()` raised `TypeError` on the real chat/summarize path — it was
  called with `temperature`/`max_tokens` it didn't accept. Now threads generation params;
  guarded by an end-to-end graph integration test (`tests/test_graph_integration.py`).
- **SSRF redirect bypass** — the ingest downloader now sets `allow_redirects=False`, and
  `validate_download_url()` resolves DNS and blocks hosts resolving to private/reserved
  IPs (DNS-rebinding defense).
- **5xx information disclosure** — `RuntimeError`/unhandled handlers no longer echo
  internal exception text; detail is logged server-side with the correlation id.
- **Citation source mismatch** — retrieval reads `source_file` (with `source` fallback);
  real documents no longer surface as `"unknown"`.
- **`doc_id` derivation** — `removesuffix(".pdf")` instead of `rstrip(".pdf")`.
- **Dependencies** — added `langchain-google-genai` (provider was importable but
  undeclared); pinned `langchain-anthropic`/`langchain-groq`; upgraded web `vite` 5→8 to
  clear dev-server advisories.
- **CI `test` job** — provisions a `redis:7-alpine` service + explicit env so it no longer
  depends on a committed `.env`; fixed a rate-limiter test whose patch scope expired
  before requests ran and a readiness test missing a Redis mock.
- **MMR regression (this release):** an interim change had replaced
  `max_marginal_relevance_search` with scored top-k to obtain citation scores. MMR is a
  deliberate retrieval-quality feature (avoids near-duplicate chunks) and has been
  **restored**; citation scores are now obtained alongside MMR by joining the scored
  candidate pool on `chunk_hash`. [regression introduced and fixed within 2.1.0 dev]

### Security

- Independent audit (ruff, bandit, pip-audit, radon, secret scan, pytest+coverage). Fixes
  above; one residual: `chromadb 1.5.9` **CVE-2026-45829** (pre-auth RCE) has no upstream
  fix yet — mitigated by embedded (non-server) usage. Track and upgrade when patched; do
  not expose the Chroma server API on the network. Full reports in `docs/audit/`.

### Removed

- **`.env` / `.coverage`** untracked from git and added to `.gitignore`.
- **`db.vector.chroma()`** — unused alias of `get_vectorstore()`.

### Known limitations (at 2.1.0)

- **Retrieval quality is not validated against a live corpus** — tests are hermetic
  (ChromaDB/embeddings mocked). MMR invocation and citation-score joining are covered, but
  real relevance/diversity is not; run a live eval (RAGAS / manual spot-checks) before
  trusting answer quality and after changing chunking, `top_k`, `fetch_k`, or embeddings.
- **`chromadb 1.5.9` CVE-2026-45829** has no upstream fix (mitigated by embedded use).
- **No authentication on `/chat`** — `X-User-Id` is validated/namespaced, not authenticated.
- **SSRF guard has a TOCTOU window** (DNS re-resolves at request time); mitigated by
  `allow_redirects=False`, not airtight.
- **Rate limiter fails open** on Redis outage (availability over enforcement).
- **Async ingest is in-process** (`BackgroundTasks`) — not durable across restarts.
- **MMR `fetch_k`/`lambda_mult` are not configurable yet**; a citation may show
  `score: null` if its chunk falls outside the scored candidate pool.
- **`retrieve_context` complexity** is CC 15 — a refactor candidate.

---

## [2.0.0] — 2026-05-30

Major release: multi-mode chat, self-ingestion, expanded provider support, and security elevation from audit score 72/100 (C+) to 95/100 (A+).

### Added

#### Chat Modes & Self-Ingestion

- **Three chat modes** (`strict`, `open`, `learning`) via `CHAT_MODE` environment variable
  - `strict` (default): Knowledge-base-only responses. Refuses to answer outside ingested documents.
  - `open`: Free interaction. Uses general knowledge when no documents match, honest about provenance.
  - `learning`: Free interaction + auto-growing knowledge base. Synthesized answers are auto-ingested into ChromaDB.
- **Self-ingest node** (`graph/nodes/self_ingest.py`) — auto-ingests model responses in learning mode when no docs matched AND answer ≥50 chars. Tags with `source_type=synthesized`, `source_question`, and `best_score` metadata for provenance tracking.
- **Mode-specific prompt builders** (`prompts/answer.py`) — three distinct prompt functions: `_build_strict_prompt`, `_build_open_prompt`, `_build_learning_prompt`. Each has different instruction structures for refusal, general knowledge, and synthesis behavior.
- **Mode-aware score gate** (`graph/nodes/retrieve_context.py`) — strict blocks below threshold (no context → refusal prompt), open/learning provide best-available matches as weak grounding signals.
- **State fields** (`graph/state.py`) — added `chat_mode`, `best_score`, `last_answer`, `self_ingested` to State TypedDict.
- **Graph wiring** (`graph/builder.py`) — added `self_ingest` node between `generate_answer` and `summarize`. No-op in strict/open modes, avoids conditional graph compilation.
- **Config validators** (`config.py`) — `check_chat_mode()` validates `CHAT_MODE` must be `strict|open|learning`. `SELF_INGEST_MIN_LENGTH` defaults to 50.
- **Service layer** (`services/chat_service.py`) — injects `chat_mode` from settings into initial state, returns `self_ingested` flag in response.

#### LLM & Embedding Provider Expansion

- **14 LLM providers** with universal OpenAI-compatible adapter (`utils/llm_adapter.py`)
  - Native: `openai`, `anthropic`, `google` (Gemini)
  - OpenAI-compatible (via `LLM_BASE_URL`): `ollama`, `openrouter`, `together`, `groq`, `deepseek`, `fireworks`, `mistral`, `vllm`, `lmstudio`, `llamacpp`
- **Provider aliases** — friendly name normalization: `claude`→`anthropic`, `gpt`→`openai`, `chatgpt`→`openai`, `llama`→`ollama`, `gemini`→`google`
- **`OPENAI_COMPATIBLE` set** — single code path for 10+ providers, eliminating per-provider import explosion
- **`LLM_BASE_URL` config** — override for any OpenAI-compatible endpoint (Ollama, OpenRouter, Together, etc.)
- **`GOOGLE_API_KEY` config** — required for Google Gemini provider
- **FastEmbed embedding provider** (`utils/embedding_adapter.py`) — ONNX-based, ~50MB, zero CVEs, no torch dependency
- **`FASTEMBED_MODELS` registry** — 7 models with dimension and description metadata:
  - `BAAI/bge-small-en-v1.5` (384d), `BAAI/bge-base-en-v1.5` (768d, recommended), `BAAI/bge-large-en-v1.5` (1024d)
  - `sentence-transformers/all-MiniLM-L6-v2` (384d), `sentence-transformers/all-MiniLM-L12-v2` (384d)
  - `BAAI/bge-m3` (1024d, multilingual — Arabic/English)
  - `nomic-ai/nomic-embed-text-v1.5` (768d, 8192 token context)
- **`list_supported_models()`** utility — exposes the registry for programmatic access
- **Config validator** `check_embedding_keys()` — warns on unknown FastEmbed models (allows pass-through), validates required API keys per provider
- **LLM provider comparison table** (README) — 14 providers: latency, cost, best-for, API key requirements
- **Embedding model comparison table** (README) — 10 models: dimensions, download size, context, best-for

#### Local Deployment

- **`docker-compose.local.yml`** — Ollama + Redis + API stack for fully local deployment, zero cloud API keys
  - Ollama auto-pulls `llama3.2` for chat and `nomic-embed-text` for embeddings on first start
  - Redis with AOF persistence
  - API configured for `LLM_PROVIDER=ollama` and `EMBEDDING_PROVIDER=fastembed`
- **`docker-compose.test.yml`** — test-specific compose for running pytest in Docker

#### Security & Observability

- **API key authentication** (`middlewares/auth.py`) — FastAPI dependency injection approach
  - `DELETE /ingest/{doc_id}` always requires `X-API-Key` header when `API_KEY` is set
  - Other ingest endpoints require it only when `REQUIRE_AUTH_FOR_INGEST=true`
  - Empty `API_KEY` skips auth (backward-compatible dev mode)
- **SSRF protection** (`utils/security.py`) — blocks private IPs, link-local addresses, loopback, cloud metadata endpoints (169.254.169.254). Allowlist mode via `ALLOWED_HOSTS` config.
- **Proxy-aware rate limiting** (`middlewares/rate_limiter.py`) — `TRUSTED_PROXIES` CIDR support, `X-Forwarded-For` and `X-Real-IP` header handling, fail-open on Redis error
- **CORS hardened** — default changed from `["*"]` to `[]`. Production must explicitly opt-in. `check_cors()` validator warns on wildcard.
- **Observability middleware** (`middlewares/observability.py`)
  - `CorrelationIdMiddleware` — injects/preserves `X-Correlation-Id` via `contextvars.ContextVar`
  - `CorrelationIdFilter` — propagates correlation ID to all log lines
  - `RequestTimingMiddleware` — logs method, path, status, duration, correlation ID
- **Structured JSON logging** (`middlewares/logging_setup.py`) — `LOG_FORMAT=json` for Datadog/CloudWatch/ELK ingestion, `python-json-logger` integration
- **Live `/ready` endpoint** — Kubernetes readiness probe checking actual Redis and ChromaDB connectivity (returns 200 or 503 with dependency-specific error details)
- **Cached `/health` endpoint** — startup health flags (cached) for load balancer routing
- **Specific exception handlers** — `ValueError`→400, `RuntimeError`→500, generic `Exception`→500 with logging. No more bare `except Exception:` in controllers.
- **Startup validation** (`config.py`) — `check_api_keys()` ensures required API keys are present for the chosen `LLM_PROVIDER`. Raises `ValueError` at startup instead of failing at runtime with opaque errors.

#### CI/CD Pipeline

- **`.github/workflows/ci.yml`** — full pipeline:
  - Ruff lint + format check
  - Bandit security scan (excludes tests directory)
  - pip-audit dependency vulnerability scan
  - pytest with coverage reporting
  - Docker build validation

#### Testing

- **91→120+ tests** across 7 test files:
  - `tests/test_adapters.py` — 48 tests: 15 LLM provider, 6 alias, 7 edge case, 11 embedding, 9 registry
  - `tests/test_graph_nodes.py` — 21 tests: 3 load_memory, 5 retrieve_context (mode-aware), 5 generate_answer (mode-specific prompts), 1 store_memory, 3 summarize, 5 self_ingest
  - `tests/test_api.py` — 17 tests: health, readiness, chat, ingest, auth, validation error handling
  - `tests/test_ingest_controller.py` — 14 tests: ingest endpoints with auth
  - `tests/test_rate_limiter.py` — 9 tests: proxy-aware IP extraction
  - `tests/test_security.py` — 7 tests: SSRF guard
  - `tests/test_graph_builder.py` — 4 tests: graph structure validation
  - `tests/test_main.py` — 7 tests: lifespan, health/ready endpoints
- **97% test coverage** (up from 89% in initial audit)
- **`tests/conftest.py`** — refactored: removed verbose comments, updated `ingest_env` fixture to use `get_redis` instead of direct `redis` patch

#### Configuration

- **`config.py`** — added `llm_base_url`, `google_api_key`, `chat_mode`, `self_ingest_min_length`, `log_format`, `api_key`, `require_auth_for_ingest`, `trusted_proxies`, `allowed_hosts` settings with Pydantic validators
- **`pyproject.toml`** — ruff config (target `py310`, line-length 120, lint rules E/F/W/I/UP), pytest config (testpaths, filterwarnings)
- **`.env.example`** — expanded with FastEmbed model registry comments, local deployment section, security configuration section, LLM provider documentation

### Changed

- **CORS default** — `cors_origins` changed from `["*"]` to `[]`. Existing deployments must explicitly configure allowed origins. [AD #1]
- **MD5 hashing** — `hashlib.md5()` in `ingest/policies.py` now uses `usedforsecurity=False`. Used for chunk deduplication only, not security. [AD #2]
- **LLM adapter** — `get_llm()` now uses `@lru_cache`, returns `ChatOpenAI` with `base_url` and `api_key` kwargs for OpenAI-compatible providers. No per-provider client imports.
- **Chat service** — `conversation()` uses `lru_cache`-wrapped graph, injects `chat_mode`, returns `self_ingested` flag.
- **Retrieve context** — mode-aware score gate: strict blocks below threshold, open/learning provide best-available. Returns `best_score` in state.
- **Generate answer** — passes `chat_mode` to prompt builder, stores `last_answer` in state for self_ingest node.
- **Rate limiter** — proxy-aware IP extraction with `TRUSTED_PROXIES` CIDR support, fail-open on Redis error.
- **Logging** — `setup_logging()` accepts `log_format` parameter ("text" or "json"), uses `python-json-logger` for structured output.

### Fixed

- **Bandit B324** — `hashlib.md5(..., usedforsecurity=False)` in `ingest/policies.py` [from audit HI-1]
- **CORS wildcard** — default changed from `["*"]` to `[]` [from audit HI-2]
- **Rate limiter proxy blindness** — `request.client.host` replaced with proxy-aware `_get_client_ip()` [from audit HI-3]
- **Missing auth on DELETE endpoint** — API key required for destructive ingest operations [from audit ME-1]
- **Missing startup validation** — `check_api_keys()` validator ensures required keys are present [from audit ME-2]
- **SSRF vulnerability** — `validate_download_url()` blocks private IPs and cloud metadata [from audit ME-5]
- **Broad exception handling** — controllers catch specific exceptions instead of bare `Exception` [from audit ME-4]
- **Ruff formatting** — `ruff format` applied across 12 files [from audit LO-1]
- **Ruff lint** — unused imports (F401) and variables (F841) cleaned in tests [from audit LO-2]
- **`.venv/` in git** — virtual environment directory removed from git tracking [AD #3]

### Security

- Full audit conducted (ruff, bandit, pip-audit, lizard, pytest with coverage) — score elevated from 72/100 (C+) to 95/100 (A+)
- 28 architectural decisions documented (AD #1–#28) covering security hardening, provider expansion, chat mode design, and testing strategy
- See `audit_artifacts/AUDIT_REPORT.md` for detailed findings and `audit_artifacts/FINAL_AUDIT.md` for verification results

### Removed

- **`pytest.ini`** — replaced by `pyproject.toml` [tool.pytest.ini_options]
- **`.venv/`** — purged from git tracking [AD #3]
- **HF dependencies from production** — `sentence-transformers` pulls `torch` transitively (CVE source); production uses OpenAI embeddings only; HuggingFace remains optional [AD #12]
- **Verbose comments in conftest.py** — removed pedagogical docstrings, kept functional code

---

## [1.0.0] — 2026-05-25

Initial release from upstream `hasandeveloper/chat-bot`.

### Features

- Conversational memory (short + long-term via Redis)
- RAG retrieval with cosine score gate (threshold 0.3) + MMR diversity ranking
- Hallucination prevention — off-topic questions blocked before LLM call
- Incremental document ingestion — only re-embeds changed chunks
- Ingestion safeguards — duplicate submission protection, file size limits, status polling
- Global duplicate detection — same PDF under different names caught via content hash
- Citations — every answer includes source documents
- Multilingual responses (Arabic / English auto-detected)
- LangGraph workflow orchestration (5 nodes)
- FastAPI production API layer
- Rate limiting — 60 requests/minute per IP (Redis-backed)
- Dockerized with Docker Compose (Redis with AOF persistence)
- Structured logging to console + rotating file (logs/app.log, 10 MB cap)
- Multi-LLM support (OpenAI, Anthropic, Groq)
- Strict knowledge-base-only responses — refuses outside ingested documents

### Limitations (at v1.0.0)

- 3 LLM providers only (OpenAI, Anthropic, Groq)
- Single chat mode (strict only)
- No authentication on ingest endpoints
- No SSRF protection on download URLs
- Permissive CORS default (`["*"]`)
- Rate limiter not proxy-aware
- No live readiness probe
- No structured JSON logging
- No CI/CD security gates
- 1 test file (ingest pipeline only)
- torch dependency with known CVEs

---

## Comparison: v1.0.0 → v2.0.0

| Dimension | v1.0.0 | v2.0.0 |
|-----------|--------|--------|
| LLM providers | 3 | 14 |
| Embedding providers | 2 (OpenAI, HuggingFace) | 3 (OpenAI, FastEmbed, HuggingFace) |
| Chat modes | 1 (strict) | 3 (strict, open, learning) |
| Self-ingestion | No | Yes (learning mode, quality gate) |
| Authentication | None | API key (FastAPI dependency) |
| SSRF protection | None | Private IP + metadata blocking |
| Rate limiting | Direct IP only | Proxy-aware (CIDR, X-Forwarded-For) |
| CORS default | `["*"]` | `[]` |
| Health probes | `/health` (static) | `/health` (cached) + `/ready` (live) |
| Logging | Text only | Text + JSON (structured) |
| Observability | None | Correlation ID + request timing |
| CI/CD | Basic (ruff + pytest) | Full (ruff + bandit + pip-audit + coverage + Docker build) |
| Test count | ~10 | 120+ |
| Test coverage | ~89% | 97% |
| Local deployment | None | docker-compose.local.yml (Ollama + FastEmbed) |
| Audit score | 72/100 (C+) | 95/100 (A+) |