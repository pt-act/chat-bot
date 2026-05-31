# Changelog

All notable changes to the AI Chatbot Backend Service are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.4.0] — 2026-05-31

Quality, trust, and reliability release implementing the top-5 proposals plus four
honorable mentions from `docs/audit/improvement-proposals.md` (see
`docs/audit/implementation-plan.md`). Every behavior change lands behind a `config.Settings`
flag whose **default preserves today's behavior**; new capabilities are additive and the
API contract is backward compatible. The LangGraph pipeline grows from 6 to 8 nodes
(adds `condense_query` and `verify_answer`); both the graph and the streaming path are kept
in sync.

### Added

#### Context-aware query rewriting (#1)

- **New `condense_query` node** (`graph/nodes/condense_query.py`, `prompts/condense.py`)
  rewrites a follow-up into a self-contained search query using the rolling summary +
  recent turns, so multi-turn retrieval is no longer context-blind (a turn like
  "and what about damaged ones?" now retrieves the right chunk instead of falsely
  refusing in strict mode). Retrieval searches on `state["search_query"]`; **generation
  still uses the original question**, so display and citations are unaffected.
- Skipped on the first turn (no LLM call), capped at 64 output tokens, and gated by
  `QUERY_REWRITE_ENABLED` (default on). Wired into `graph/builder.py` and
  `services/chat_service.stream_conversation`.

#### Groundedness / faithfulness verification (#2)

- **New `verify_answer` node** (`graph/nodes/verify_answer.py`, `prompts/verify.py`) runs
  after generation when documents are present, computing a `grounded` verdict
  (`supported` | `partial` | `unsupported`) and `grounded_score`. Two config-selectable
  tiers: `heuristic` (default, no extra LLM call — content-word overlap per answer
  sentence) and `llm` (a single JSON-judge call).
- **Strict-mode enforcement** — an `unsupported` answer in strict mode is converted to the
  canonical "Not in the knowledge base" refusal and its sources cleared
  (`STRICT_REFUSE_ON_UNGROUNDED`), turning a subtle hallucination into an honest refusal.
  In `open`/`learning` the answer is kept and only the signal is surfaced.
- New `ChatMeta.grounded` / `grounded_score` (`schemas/responses.py`); surfaced in both the
  `POST /api/v1/chat` response and the streaming `done` meta.

#### Persistent feedback + closed quality loop (#3)

- **`POST /api/v1/feedback`** (open to end users) records 👍/👎 with an optional reason and
  Q/A snapshot; **`GET /api/v1/feedback`** (API-key gated) lists/paginates/filters it.
  New `schemas/feedback.py`, `feedback/keys.py`, `services/feedback_service.py`,
  `controllers/v1/feedback.py`, OpenAPI tag `feedback`. Stored reasons run through the
  output guardrail; the turn's `correlation_id` is captured automatically.
- **`export_downvoted_to_golden()`** appends thumbs-down questions to `eval/golden.jsonl`,
  closing the loop from production feedback into the RAGAS regression set.

#### Provider retry/backoff + circuit breaker (#14)

- **New `utils/resilience.py`** — `resilient_invoke` / `@resilient_call` wrap synchronous
  LLM calls (`generate_answer`, `summarize`, `condense_query`, `verify_answer`) with
  tenacity exponential-backoff retries on **transient** errors (timeouts, connection
  errors, HTTP 429/5xx) plus an in-process `CircuitBreaker` (opens after
  `CB_FAILURE_THRESHOLD` consecutive failures, half-opens after `CB_RESET_SECONDS`).
  Non-transient errors are never retried. Streaming retries only the **initial connection**
  (pre-roll), before any token is yielded.
- New dependency **`tenacity`**.

#### Durable, retryable ingestion (#4)

- **`INGEST_MODE=queue`** — controllers enqueue an ingest job onto a Redis list
  (`ingest/queue.py`) consumed by a worker (`python -m ingest.worker`), so ingestion
  survives API restarts, retries transient failures up to `INGEST_MAX_ATTEMPTS`, and stays
  idempotent via a per-`doc_id` lock on top of the existing content-hash dedup. Uploads are
  staged to a shared `INGEST_INCOMING_DIR`. `docker-compose.yml` gains a `worker` service +
  shared volume. The `inline` default (FastAPI `BackgroundTasks`) is unchanged.

#### Configurable persona, refusal copy & domain scoping (#5)

- `ASSISTANT_NAME`, `KNOWLEDGE_DOMAIN`, `ESCALATION_MESSAGE` thread through the strict/open/
  learning prompt builders (`prompts/answer.py` stays config-free; `generate_answer` reads
  settings). **Defaults reproduce the original prompt strings byte-for-byte**, so an
  unconfigured deployment behaves identically — but three env vars now rebrand the assistant
  and its refusal/escalation copy with zero code edits.

#### Hybrid retrieval + reranking (Phase 4, gated)

- **`RETRIEVAL_STRATEGY`** = `mmr` (default, unchanged) | `hybrid` | `hybrid_rerank`.
  `ingest/retrieval.py` adds BM25 lexical retrieval fused with dense results via Reciprocal
  Rank Fusion (recovers acronyms/SKUs/exact phrases dense embeddings miss) and a `rerank`
  integration point (identity passthrough by default — no new heavy dependency forced).
  New dependency **`rank-bm25`**. Adopt only with evidence from the regression test/eval.

#### Hermetic retrieval-regression test + opt-in eval CI (#19)

- **`tests/test_retrieval_regression.py`** (marked `@pytest.mark.retrieval`) seeds a tiny
  labeled corpus with the real FastEmbed model and asserts recall@k + a score floor, so
  retrieval quality cannot silently regress (skips cleanly when offline).
- **`.github/workflows/eval.yml`** — a non-PR workflow (`workflow_dispatch` + weekly
  `schedule`) seeds a corpus (`eval/seed_corpus.py`), runs `eval/run_ragas.py`, uploads the
  report, and applies conservative metric floors. The PR pipeline stays hermetic.

#### Reviewer UI (#29)

- The reference web client (`web/`) gains a **Review** panel for the `learning_review`
  queue: list pending synthesized answers and Approve/Reject them, with an operator
  API-key field (stored in `localStorage`, sent as `X-API-Key`). Builds clean
  (`tsc -b && vite build`), `bun audit` clean.

### Changed

- **App version** → `2.4.0`.
- **LangGraph pipeline** is now 8 nodes: `load_memory → condense_query → retrieve_context →
  generate_answer → verify_answer → self_ingest → summarize → store_memory`.
- **`graph/state.py`** — added `search_query`, `grounded`, `grounded_score`.
- **`retrieve_context`** searches on `search_query` (falling back to `question`) and
  dispatches the retrieval strategy; default MMR behavior is unchanged.

### Dependencies

- Added **`tenacity`** (resilience, #14) and **`rank-bm25`** (hybrid retrieval, Phase 4).

### Security

- **`pypdf` 6.11.0 → 6.12.0** — fixes two PDF-parsing DoS issues (AIKIDO-2026-10938
  xref-stream over-iteration, AIKIDO-2026-10937 layout-mode whitespace blow-up).
- **Pinned `h11>=0.16.0`** (transitive via uvicorn/httpx) — closes the chunked-body
  request-smuggling leniency in CVE-2025-43859.
- **Container hardening** — the Docker image now runs as a non-root `appuser` (least
  privilege); runtime dirs (`logs`, `chroma_db`, `ingest_incoming`) are pre-created and
  owned by it so queue-mode uploads stay writable.
- **Residual:** `chromadb 1.5.9` **CVE-2026-45829** (pre-auth RCE in *server* mode) still
  has no upstream-fixed release; mitigated by embedded (non-server) use and excluded in CI
  pip-audit. The ingest downloader's SSRF surface remains guarded by `validate_download_url`
  (DNS-aware private/metadata-IP blocking), `allow_redirects=False`, and `ALLOWED_HOSTS`.

### Known limitations (at 2.4.0)

- **Groundedness heuristic is lexical** (content-word overlap) — tune `GROUNDEDNESS_MIN_SCORE`
  per corpus, or switch to the `llm` tier for harder paraphrase. Strict refusal applies to
  the *stored* answer/meta on the streaming path, not to tokens already streamed.
- **Hybrid/rerank are off by default and unproven on your corpus** — validate a lift with
  the regression test / RAGAS before enabling; the reranker is an identity passthrough until
  a concrete reranker is wired in.
- **Queue-mode ingestion adds an operational component** (worker + shared volume); `inline`
  remains the zero-ops default.
- **Feedback submission is open** (rate-limited only) — add a TTL/size cap if abuse is a concern.

---

## [2.3.0] — 2026-05-31

Closes three roadmap items — **Guardrails**, **RAGAS evaluation**, and a **learning-mode
review workflow (two-phase ingest)** — and adds **multi-format ingestion** (PDF, TXT,
Markdown, DOCX, HTML) with a **local upload** path so documents can be ingested without a
public URL. Backward compatible: existing endpoints/contracts are unchanged; new behavior
is additive.

### Added

#### Multi-format document ingestion + local upload

- **Multi-format support** — ingestion is no longer PDF-only. A new loader registry
  (`ingest/loaders.py`, `load_documents`) handles **PDF, TXT, Markdown (`.md`/`.markdown`),
  DOCX, and HTML (`.html`/`.htm`)**, dispatched by extension; adding a format is a one-line
  entry. Both URL and upload paths infer the format from the file/URL extension. URL ingest
  now validates against all supported extensions (not just `.pdf`).
- **`POST /api/v1/ingest/upload`** (`multipart/form-data`) — ingest a document uploaded
  directly from the client, no URL required, so documents never have to leave the user's
  environment (completes the fully-local story alongside FastEmbed + Ollama). Validates by
  extension (PDFs also get a `%PDF` magic-header check), enforces `MAX_FILE_SIZE_MB` while
  streaming to a temp file, derives a sanitized `doc_id` from the filename (or an explicit
  `file_name`), and reuses the existing async pipeline (202 + `Location`, poll
  `GET /ingest/status/{doc_id}`).
- **Shared ingest core** — `ingest/policies.py` refactored into `_run_ingest` reused by both
  `process_policy` (URL) and the new `process_uploaded` (local file), threading the format
  through to the loader; `ingest_local_file` service + `sanitize_doc_id`/`clean_file_name`
  helpers in `schemas/ingest.py`.
- **Web client `Upload doc` button** (`web/`) — file picker (PDF/TXT/MD/DOCX/HTML) that
  posts to the upload endpoint and reports queued status.
- Dependencies: **`python-multipart`** (FastAPI form/file parsing), **`docx2txt`** (.docx),
  **`beautifulsoup4`** (.html, via the stdlib parser).

#### Guardrails (`guardrails/`)

- **Lightweight, dependency-free, deterministic** input/output guards (no model calls, so
  the suite stays hermetic). Config-toggleable via `config.Settings`.
- **Input guard** (`check_input`) — rejects prompt-injection / jailbreak attempts
  ("ignore previous instructions", "reveal your system prompt", "developer mode",
  `<system>` tags, etc.). Raises `GuardrailViolation` (a `ValueError`) → HTTP 400 /
  problem+json on `POST /chat`, and a 400 `error` SSE frame on `POST /chat/stream`.
  Runs before any token is streamed.
- **Output guard** (`sanitize_output`) — optional PII masking (emails, phone/card-like
  number runs) and a hard answer-length cap; returns flags describing what was applied.
  Applied in `generate_answer` and on the assembled streaming answer.
- Settings: `GUARDRAILS_ENABLED` (true), `GUARDRAILS_BLOCK_INJECTION` (true),
  `GUARDRAILS_MASK_PII` (false — a support bot often legitimately returns contact
  emails), `GUARDRAILS_MAX_ANSWER_CHARS` (4000; 0 disables).

#### Learning-mode review workflow — new `learning_review` chat mode (two-phase ingest)

- **New fourth chat mode `learning_review`** alongside `strict` / `open` / `learning`
  (`CHAT_MODES` / `LEARNING_MODES` in `config.py`; added to the `ChatRequest.mode` enum and
  the web mode selector). It behaves like `learning` — synthesizing gap-filling answers and
  consulting the synthesized store — but is **two-phase**: synthesized answers are **queued
  in Redis** (`services/review_service.py`, keys in `review/keys.py`) instead of embedded.
  Unverified model output never enters the vector store until a human approves it. Plain
  `learning` keeps embedding immediately.
- **New `/api/v1/review` endpoints** (`controllers/v1/review.py`, gated by the existing
  `require_api_key` dependency): `GET /review/pending` (paginated), `POST /review/{id}/approve`
  (embeds into `synthesized_answers`, then retrievable in the learning modes),
  `POST /review/{id}/reject` (discards). Typed via `schemas/review.py`.
- New state fields `pending_review` / `review_entry_id`; new OpenAPI tag `review`.

#### Evaluation (RAGAS) — `eval/`

- **Offline harness** (`eval/run_ragas.py`) computing faithfulness, answer relevancy,
  context precision, and context recall. Two modes: `live` (runs the real retrieval +
  generation path) and `score` (scores precomputed records). Golden dataset
  (`eval/golden.jsonl`), docs (`eval/README.md`), optional deps (`requirements-eval.txt`).
- **Deliberately not wired into CI** — RAGAS judges with an LLM (needs a key, network, and
  is non-deterministic), which would break the hermetic suite.

### Changed

- **App version** → `2.3.0`.
- **`meta.lang`** now reports `pt` for European Portuguese responses (previously collapsed
  to `en`); mapping centralized in `utils.lang_detect.to_code`.

### Dependencies

- `requirements-eval.txt` (optional): `ragas>=0.1,<0.2`, `datasets>=2.16`. Not installed
  in CI or the runtime image.

### Known limitations (at 2.3.0)

- **Guardrails are heuristic**, tuned for precision over recall — novel injection phrasings
  may pass; they are a layer, not a complete defense. PII masking on streaming applies to
  the stored/persisted answer, not tokens already streamed to the client.
- **RAGAS scores are corpus/model-dependent and non-deterministic** — use them as a
  regression signal, not an absolute grade.

---

## [2.2.0] — 2026-05-31

Adds **European Portuguese (pt-PT)** as a third response language alongside English and
Arabic. Backward compatible: `lang` defaults to `auto` and existing EN/AR behavior is
unchanged; `pt` is purely additive across the API, pipeline, and web client.

### Added

- **European Portuguese responses** — `lang` now accepts `pt` (`ChatRequest`,
  `schemas/chat.py`). When selected, prompts instruct the model to answer in the spelling
  and vocabulary of Portugal (pt-PT), never Brazilian Portuguese (`prompts/answer.py`,
  all three modes).
- **Hybrid language auto-detection** (`utils/lang_detect.py`, new module exposing
  `detect_language`):
  - Arabic by Unicode script (unchanged, definitive).
  - A fast, dependency-free **Portuguese heuristic** — distinctive diacritics
    (`ã õ á é í ó ú â ê ô à ç`) are decisive; otherwise a Portuguese **stopword-frequency
    ratio** (NLTK `portuguese` list) decides for sentences of ≥4 words. Single shared
    tokens (e.g. the English word "no", also a PT stopword) cannot flip the verdict.
  - Only short, unaccented, genuinely ambiguous fragments fall through to the
    [lingua](https://github.com/pemistahl/lingua-py) EN/PT statistical model, built once
    and `lru_cache`d. Falls back to English if the model is unavailable (never crashes a
    request).
- **Web client `PT` language selector** (`web/src/components/Controls.tsx`,
  `web/src/types.ts`) — `lang` type is now `auto | en | ar | pt`. Portuguese renders LTR
  (no RTL change needed).
- **Tests** — new `tests/test_lang_detect.py` (10 cases: Arabic, diacritics, stopword
  ratio, shared-stopword abstention, lingua fallback for PT and EN, library-unavailable
  default) plus Portuguese cases in `tests/test_graph_nodes.py`.

### Changed

- **App version** → `2.2.0`.
- **`generate_answer`** now delegates language resolution to `utils.lang_detect`
  (the inline EN/AR-only heuristic was removed); explicit `en`/`ar`/`pt` still bypass
  detection.

### Dependencies

- Added **`lingua-language-detector==2.1.1`** — statistical EN/PT fallback for short,
  unaccented inputs.

### Known limitations (at 2.2.0)

- **Auto-detection of unaccented Portuguese vs English is statistical, not perfect.** Very
  short single tokens are inherently ambiguous (lingua leans on n-gram models). Explicit
  `lang: "pt"` (or `en`/`ar`) is 100% reliable; auto is high-accuracy but not guaranteed.
- Detection currently distinguishes **EN / AR / PT** only; adding more languages means
  extending `_LANG_LABELS`, the lingua language set, and the prompt guidance.

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