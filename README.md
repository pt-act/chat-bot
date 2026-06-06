<div align="center">

# 🤖 AI Chatbot Backend Service

### LangChain + LangGraph + RAG + FastAPI

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![LangChain](https://img.shields.io/badge/LangChain-LLM%20Orchestration-orange)
![ChromaDB](https://img.shields.io/badge/VectorDB-Chroma-purple)
![LLM](https://img.shields.io/badge/LLM-14%20Providers-black)
![Chat Mode](https://img.shields.io/badge/Mode-Strict%20%7C%20Open%20%7C%20Learning-blue)

</div>

---

## 📋 Table of Contents

- [Project Overview](#-project-overview)
- [Why This Project](#-why-this-project)
- [Architecture](#-architecture)
- [How It Works](#-how-it-works)
- [Project Structure](#-project-structure)
- [Setup Instructions](#-setup-instructions)
- [Document Ingestion](#-6-document-ingestion-s3--chromadb)
- [Chat API](#-7-chat-api)
- [Health & Readiness](#-8-health--readiness)
- [Web Client](#-web-client)
- [Further Documentation](#-further-documentation)
- [Observability](#-observability)
- [Core System Design](#-core-system-design)
- [Security](#-security)
- [Security Audit History](#-security-audit-history)
- [Key Features](#-key-features)
- [TODO](#-todo-roadmap)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [Changelog](#-changelog)
- [Fork History](#-fork-history)
- [Summary](#-summary)

---

## 📌 Project Overview

This project is a **production-grade AI chatbot backend** built using:

* 🧠 LangGraph for conversation orchestration (8-node pipeline)
* 🔍 RAG pipeline using ChromaDB with mode-aware score gating, context-aware query rewriting, and groundedness verification
* 💬 Multi-LLM support (14 providers via universal OpenAI-compatible adapter)
* ⚡ FastAPI for backend APIs with auth, rate limiting, and observability
* 🧠 Redis for memory storage, rate limiting, and ingestion registry
* 🔒 Security-hardened: SSRF protection, API key auth, proxy-aware rate limiting, structured logging

It supports:

* Conversational memory with summarization
* Document-based Q&A (RAG) — ingest PDF / TXT / Markdown / DOCX / HTML, from a URL or by uploading a local file (privacy-friendly)
* Four chat modes: strict (knowledge-base-only), open (free interaction), learning (auto-growing KB), learning_review (KB growth gated by human review)
* 14 LLM providers (OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek, Together, Mistral, Fireworks, OpenRouter, vLLM, LM Studio, llama.cpp)
* 7+ embedding models via FastEmbed (ONNX-based, zero CVEs)
* Self-ingestion in learning mode — auto-saves synthesized answers with provenance metadata
* API key authentication on destructive ingest endpoints
* SSRF protection — blocks private IPs and cloud metadata endpoints
* Proxy-aware rate limiting (X-Forwarded-For handling with CIDR trust)
* Structured JSON logging with correlation ID tracing
* Fully local deployment with Ollama (zero cloud API keys)
* Multilingual responses (Arabic / English / European Portuguese)
* Versioned, typed HTTP API (`/api/v1`) with RFC 9457 `problem+json` errors and per-request controls
* SSE token streaming (`/api/v1/chat/stream`) with structured citations (label, doc_id, score, page, snippet)
* Context-aware query rewriting — condenses multi-turn follow-ups into a standalone search query before retrieval
* Groundedness verification — surfaces `meta.grounded`; strict mode refuses answers unsupported by the retrieved chunks
* Persistent feedback (`POST /api/v1/feedback`) feeding a moderator queue and the RAGAS golden set
* Provider resilience — transient 429/5xx retries with backoff + an in-process circuit breaker
* Durable, retryable ingestion (`INGEST_MODE=queue`) with a worker that survives restarts
* Configurable persona / domain / refusal copy — deploy as your own assistant with three env vars
* Optional hybrid retrieval (dense + BM25 via RRF) for lexical recall of acronyms / SKUs / exact phrases
* Guardrails — input prompt-injection blocking + output PII masking / length cap (config-toggleable)
* RAGAS evaluation harness (`eval/`) — offline faithfulness / relevancy / context precision+recall
* Reference web client (`web/`) — Vite + React + TypeScript SPA demonstrating the v1 API, incl. a reviewer panel
* Kubernetes-ready health/ready probes
* Scalable backend design

## 🎯 Why This Project

Most chatbot APIs are stateless and cannot maintain long-term context.

This project solves that by combining:
- Stateful memory (Redis)
- Long-term summarization
- RAG-based knowledge retrieval
- LangGraph orchestration

Making it suitable for real-world SaaS integrations.

## 🧠 Architecture

<div align="center">

```
┌─────────────────────────────────────────────────────┐
│                   User Query                        │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
              FastAPI  POST /api/chat
                         │
                         ▼
          ┌──────────────────────────────┐
│     LangGraph Orchestrator   │
           │                              │
           │  1. load_memory   (Redis)    │
           │  2. condense_query  (LLM)    │ ← context-aware rewrite (multi-turn)
           │  3. retrieve_context (Chroma)│ ← mode-aware gate + mmr/hybrid
           │  4. generate_answer  (LLM)   │ ← mode-specific prompt
           │  5. verify_answer            │ ← groundedness gate (strict refuses)
           │  6. self_ingest  (Chroma)    │ ← learning mode only
           │  7. summarize                │
           │  8. store_memory  (Redis)    │
          └──────────────────────────────┘
                         │
                         ▼
                  Response to User
```

</div>

## 🧠 How It Works

1. User sends a question
2. System loads conversation history from Redis
3. Relevant documents are retrieved from ChromaDB (RAG) — behavior depends on `CHAT_MODE`
4. LangGraph orchestrates the flow:
   - memory → condense query → retrieval → reasoning → verify groundedness → self-ingest (if learning) → response
5. On multi-turn follow-ups, the question is condensed into a standalone search query before retrieval
6. LLM generates a final contextual answer — mode-specific prompt controls behavior
7. The answer's groundedness is verified against the retrieved chunks — strict mode refuses when unsupported
8. In learning mode, synthesized answers are auto-ingested into ChromaDB as new knowledge
9. Conversation is updated + summarized for future use

## 🗂️ Project Structure

```
chat-bot/
├── controllers/          # Route handler logic (chat, ingest endpoints)
├── middlewares/          # Rate limiting middleware
├── db/                   # Redis and ChromaDB clients
├── graph/
│   ├── builder.py        # LangGraph pipeline definition (8 nodes + edges)
│   ├── state.py          # State TypedDict (chat_mode, best_score, search_query, grounded, …)
│   └── nodes/            # Individual graph nodes
│       ├── load_memory.py       # Load conversation history from Redis
│       ├── condense_query.py    # Rewrite follow-ups into a standalone search query (#1)
│       ├── retrieve_context.py  # Mode-aware score gate + MMR / hybrid retrieval
│       ├── generate_answer.py   # Mode-specific prompt → LLM call (resilient)
│       ├── verify_answer.py     # Groundedness verification + strict refusal (#2)
│       ├── self_ingest.py       # Auto-ingest synthesized answers (learning mode)
│       ├── store_memory.py      # Save conversation to Redis
│       └── summarize.py        # Conversation summarization
├── ingest/               # Document ingestion pipeline
│   ├── loaders.py        # Multi-format loader registry (PDF/TXT/MD/DOCX/HTML)
│   ├── retrieval.py      # Hybrid (dense + BM25) retrieval + RRF fusion (Phase 4)
│   ├── queue.py          # Durable Redis-backed ingest queue (#4)
│   └── worker.py         # `python -m ingest.worker` — durable ingest worker
├── feedback/             # Feedback Redis keys (#3)
├── prompts/
│   ├── answer.py         # 3 mode-specific prompt builders (config-driven persona)
│   ├── condense.py       # Query-rewrite prompt
│   ├── verify.py         # LLM groundedness-judge prompt
│   └── summarize.py      # Conversation summarization prompt
├── schemas/
│   ├── chat.py           # ChatRequest schema
│   ├── feedback.py       # Feedback request/response schemas
│   └── ingest.py         # IngestRequest schema
├── services/
│   ├── chat_service.py   # Runs the graph / streaming path; returns grounded + self_ingested
│   └── feedback_service.py  # Persist feedback + export downvotes to the golden set
├── utils/
│   └── resilience.py     # Provider retry/backoff + circuit breaker (#14)
├── eval/                 # RAGAS harness + corpus seeder + golden set
├── tests/                # Pytest test suite (300+ tests, 97% coverage)
├── main.py               # App entrypoint
├── config.py             # Settings (pydantic-settings) — all feature flags
├── pytest.ini            # Test configuration
├── requirements.txt
├── requirements-dev.txt  # Test dependencies (pytest, fakeredis, responses, fpdf2)
├── docker-compose.yml           # Cloud deployment (API + Redis)
└── docker-compose.local.yml     # Local deployment (API + Redis + Ollama)
```

## ⚙️ Setup Instructions

### 🧩 1. Install Miniconda

```bash
bash ~/Downloads/Miniconda3-*.sh
source ~/miniconda3/bin/activate
```

> Full guide: https://www.anaconda.com/docs/getting-started/miniconda/install/mac-cli-install

### 🐍 2. Create Environment

```bash
conda create -n chat-bot python=3.10
conda activate chat-bot
```

### 📦 3. Clone and Install Dependencies

```bash
git clone https://github.com/pt-act/chat-bot.git
cd chat-bot
pip install -r requirements.txt
```

### ⚠️ 4. Configure Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Key variables:

```env
OPENAI_API_KEY=your_openai_key_here     # https://platform.openai.com/account/api-keys

LLM_PROVIDER=openai                     # openai | anthropic | google | groq | ollama | openrouter | together | deepseek | mistral
LLM_MODEL=gpt-4o-mini
# Override base URL for any OpenAI-compatible endpoint:
# LLM_BASE_URL=http://localhost:11434/v1  # Ollama
# LLM_BASE_URL=https://openrouter.ai/api/v1  # OpenRouter

REDIS_HOST=localhost
REDIS_PORT=6379

RETRIEVAL_SCORE_THRESHOLD=0.3           # raise to 0.7 for stricter grounding

CHAT_MODE=strict                        # strict | open | learning | learning_review — see Chat Modes section
SELF_INGEST_MIN_LENGTH=50               # minimum answer length for auto-ingest in learning modes

GUARDRAILS_ENABLED=true                 # input prompt-injection blocking + output guards
GUARDRAILS_BLOCK_INJECTION=true         # reject likely prompt-injection / jailbreak inputs (400)
GUARDRAILS_MASK_PII=false               # mask emails/phone/card-like numbers in output
GUARDRAILS_MAX_ANSWER_CHARS=4000        # hard cap on answer length (0 disables)
```

See [.env.example](.env.example) for the full list of options.

#### 🧠 LLM Provider Support

The system uses a **universal OpenAI-compatible adapter** — most modern providers expose an OpenAI-compatible API, so we support them with a single code path.

**Native providers:**
- `openai` — GPT-4o, GPT-4o-mini, etc.
- `anthropic` — Claude 3.5 Sonnet, Haiku, etc.
- `google` — Gemini models (requires `GOOGLE_API_KEY`)

**OpenAI-compatible (use `LLM_BASE_URL` override):**
- `ollama` — Local models (Llama, Mistral, etc.)
- `openrouter` — Route to 100+ models
- `together` — Together AI
- `groq` — Groq (also works natively)
- `deepseek` — DeepSeek models
- `fireworks` — Fireworks AI
- `mistral` — Mistral AI
- `vllm` — vLLM self-hosted
- `lmstudio` — LM Studio local
- `llamacpp` — llama.cpp local

All OpenAI-compatible providers use the same `langchain_openai.ChatOpenAI` client. Just set `LLM_BASE_URL` to point to your endpoint. Local providers (Ollama, LM Studio, vLLM) don't need an API key.

**Provider aliases:** `claude` → anthropic, `gpt` / `chatgpt` → openai, `llama` → ollama, `gemini` → google.

##### LLM Provider Comparison

| Provider | Type | Latency | Cost (per 1M tokens) | Best For | API Key |
|----------|------|---------|----------------------|----------|---------|
| **OpenAI** | Cloud API | ~1s | Input $0.15 / Output $0.60 (gpt-4o-mini) | General production use | `OPENAI_API_KEY` |
| **Anthropic** | Cloud API | ~1.5s | Input $0.25 / Output $1.25 (claude-3.5-haiku) | Long-context reasoning, safety | `ANTHROPIC_API_KEY` |
| **Google Gemini** | Cloud API | ~1s | Free tier: 15 RPM; Paid ~$0.075/1M (gemini-2.0-flash) | Cost-effective, multimodal | `GOOGLE_API_KEY` |
| **Groq** | Cloud API | ~0.3s | Free tier available; Paid ~$0.05/1M | Fastest inference, real-time chat | `GROQ_API_KEY` + `LLM_BASE_URL` |
| **DeepSeek** | Cloud API | ~2s | Input $0.14 / Output $0.28 (deepseek-chat) | Budget-friendly, strong coding | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| **Together** | Cloud API | ~1s | Varies by model (~$0.10–$0.80/1M) | Open-source model access | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| **Mistral** | Cloud API | ~1s | Input $0.10 / Output $0.30 (mistral-small) | European data compliance | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| **Fireworks** | Cloud API | ~0.5s | ~$0.20/1M (open-source models) | Fast open-source inference | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| **OpenRouter** | Cloud proxy | Varies | Varies by model + 5% surcharge | Single API for 100+ models | `OPENAI_API_KEY` + `LLM_BASE_URL` |
| **Ollama** | Local | ~2–10s | **Free** (own hardware) | Full privacy, air-gapped, zero cost | None (local) |
| **vLLM** | Local | ~1–5s | **Free** (own hardware) | High-throughput self-hosted | None (local) |
| **LM Studio** | Local | ~2–10s | **Free** (own hardware) | Desktop dev/testing | None (local) |
| **llama.cpp** | Local | ~3–15s | **Free** (own hardware) | Minimal hardware, CPU-only | None (local) |

> **When to use local vs cloud:** Use local providers (Ollama/vLLM) when data privacy is paramount, for air-gapped deployments, or to avoid API costs. Use cloud providers for production reliability, lower latency, and models that exceed local hardware capacity. Groq is the fastest cloud option; DeepSeek and Gemini Flash are the cheapest.

#### 📦 Embedding Providers

The default embedding provider is OpenAI (no extra dependencies).

**Recommended for local embeddings — FastEmbed (ONNX):**

```bash
# Already included in requirements.txt
# Set EMBEDDING_PROVIDER=fastembed
# Set EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

FastEmbed uses ONNX Runtime (no torch dependency):
- ~50MB download vs ~2GB for torch-based alternatives
- Zero CVEs — pure Python + ONNX
- Supports any FastEmbed-compatible model — unknown models trigger a warning but still load

**Alternative — HuggingFace (torch-based):**

```bash
pip install langchain-huggingface sentence-transformers transformers numpy
```

> ⚠️ `sentence-transformers` and `transformers` pull in `torch` which has known CVEs on older versions. Only install these if you explicitly need HuggingFace-specific models not available in FastEmbed.

##### Embedding Model Comparison

| Model | Provider | Dimensions | Download | Context | Best For |
|-------|----------|-----------|----------|---------|----------|
| `text-embedding-3-small` | OpenAI | 1536 | API-only | 8191 | Default, production reliability |
| `text-embedding-3-large` | OpenAI | 3072 | API-only | 8191 | Maximum accuracy, higher cost |
| `BAAI/bge-small-en-v1.5` | FastEmbed | 384 | ~50MB | 512 | Prototyping, small datasets, low memory |
| `BAAI/bge-base-en-v1.5` | FastEmbed | 768 | ~120MB | 512 | Balanced speed/quality (**recommended**) |
| `BAAI/bge-large-en-v1.5` | FastEmbed | 1024 | ~430MB | 512 | Highest local quality, slower inference |
| `sentence-transformers/all-MiniLM-L6-v2` | FastEmbed | 384 | ~30MB | 256 | Fast semantic search, versatile |
| `sentence-transformers/all-MiniLM-L12-v2` | FastEmbed | 384 | ~60MB | 256 | Slightly better quality than L6 |
| `BAAI/bge-m3` | FastEmbed | 1024 | ~570MB | 8192 | **Arabic/English mixed content**, multilingual |
| `nomic-ai/nomic-embed-text-v1.5` | FastEmbed | 768 | ~130MB | 8192 | Long documents (>256 tokens) |
| `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace | 384 | ~2GB+ | 256 | Same model, torch-based (AVOID if FastEmbed works) |

> **Choosing an embedding model:** If you need Arabic+English support, use `BAAI/bge-m3`. For most English-only use cases, `BAAI/bge-base-en-v1.5` offers the best balance. For zero-cost local deployment, any FastEmbed model works without API keys. OpenAI embeddings are best when you don't want to manage local inference.

> **Switching models requires re-ingesting:** Embedding models produce different vectors — you must delete existing documents and re-ingest after changing `EMBEDDING_MODEL`.

#### 🔒 Security Configuration

Production deployments must configure these security settings in `.env`:

```env
# API Key Authentication (recommended for production)
API_KEY=your-secret-api-key-here        # Set to enable auth on ingest endpoints
REQUIRE_AUTH_FOR_INGEST=true           # Require API key for POST /api/ingest and GET /api/ingest/docs

# CORS — production should never use "*"
CORS_ORIGINS=["https://your-domain.com"]  # Empty list [] disables CORS entirely

# Rate Limiting (behind reverse proxy)
TRUSTED_PROXIES=["10.0.0.0/8", "172.16.0.0/12"]  # CIDR ranges of trusted load balancers
ALLOWED_HOSTS=["*"]                    # SSRF protection: whitelist download hosts or ["*"] to allow all public hosts
```

**Authentication behavior:**
- `DELETE /api/ingest/{doc_id}` **always** requires the `X-API-Key` header when `API_KEY` is set
- Other ingest endpoints require it only when `REQUIRE_AUTH_FOR_INGEST=true`
- When `API_KEY` is empty, auth is skipped (backward-compatible dev mode)

**Rate limiting:** 60 requests/minute per IP. If running behind Cloudflare/nginx, configure `TRUSTED_PROXIES` so the real client IP is used instead of the proxy's IP.

> **LangSmith (optional):** Tracing is disabled by default (`LANGSMITH_TRACING=false`). To enable it, set `LANGSMITH_TRACING=true` and provide a valid `LANGSMITH_API_KEY` from [smith.langchain.com](https://smith.langchain.com).

### 🚀 5. Run Server

```bash
uvicorn main:app --reload
```

Server runs at `http://127.0.0.1:8000`

Or run with Docker (includes Redis):

```bash
docker-compose up --build
```

> The compose stack runs three services — `api`, a durable ingest `worker`
> (`python -m ingest.worker`), and `redis` — with `INGEST_MODE=queue` so ingestion
> survives API restarts (see [Durable ingestion](#-6-document-ingestion-s3--chromadb)).
> For a single-process setup, set `INGEST_MODE=inline` (the code default) and drop the worker.

#### Fully Local Deployment (Ollama + FastEmbed — zero cloud API keys)

For air-gapped, privacy-first, or zero-cost deployment, use the local compose file with Ollama:

```bash
# One command — Ollama pulls llama3.2 and nomic-embed-text on first start
docker-compose -f docker-compose.local.yml up --build
```

This starts:
- **Ollama** on port 11434 — pulls `llama3.2` for chat and `nomic-embed-text` for embeddings (if you prefer FastEmbed)
- **Redis** on port 6379 — conversation memory with AOF persistence
- **API** on port 8000 — configured for fully local operation

All settings are pre-configured in `docker-compose.local.yml`:
- `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://ollama:11434/v1`
- `EMBEDDING_PROVIDER=fastembed`, `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`
- No cloud API keys needed

> **Hardware requirements:** Ollama with llama3.2 needs ~4GB RAM. For larger models (llama3.1-70b), you need ~40GB RAM or a GPU. See [Ollama model list](https://ollama.com/models) for options.

> **Customizing the model:** Edit `LLM_MODEL` and the `ollama pull` command in `docker-compose.local.yml` to use any Ollama-supported model. For multilingual support, use `bge-m3` as the embedding model and a multilingual LLM like `mistral` or `qwen2`.

## 📥 6. Document Ingestion (S3 → ChromaDB)

On `/api/v1`, ingestion is **asynchronous**: the request returns `202 Accepted` with
`status=queued` and a `Location` header, then processes in the background — poll the
status endpoint for progress. (Legacy `/api/ingest` remains synchronous.)

**Supported formats:** PDF, TXT, Markdown (`.md`/`.markdown`), DOCX, HTML (`.html`/`.htm`).
The format is inferred from the file/URL extension and dispatched to the matching loader
(`ingest/loaders.py`) — adding another format is a one-line entry there.

### Queue a document (from a URL)

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_name": "terms_conditions", "s3_url": "https://your-host/terms.pdf"}'
# → 202  {"doc_id": "terms_conditions", "status": "queued"}   # .pdf/.txt/.md/.docx/.html
```

### Upload a local document (no URL — privacy-friendly)

For a fully local / on-prem setup, push a file straight from your machine — it never has
to be hosted anywhere. Pair with FastEmbed + Ollama for a zero-cloud pipeline.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest/upload" \
  -F "file=@/path/to/return_policy.pdf"          # or .txt, .md, .docx, .html
# → 202  {"doc_id": "return_policy", "status": "queued"}

# optional explicit doc id (otherwise derived + sanitized from the filename):
curl -X POST "http://127.0.0.1:8000/api/v1/ingest/upload" \
  -F "file=@./Q3 Report.docx" -F "file_name=q3_report"
```

> Multipart `file` must be a supported format (validated by extension; PDFs also get a
> `%PDF` header check) and within `MAX_FILE_SIZE_MB`. Same async contract as URL ingest:
> poll `GET /ingest/status/{doc_id}`. The web client exposes this as an **Upload doc** button.

### Check ingest status (poll)

```bash
curl http://127.0.0.1:8000/api/v1/ingest/status/terms_conditions
# → {"doc_id": "...", "status": "done", "added": 12, "total": 12, "version": "..."}
```

### List ingested documents (paginated)

```bash
curl "http://127.0.0.1:8000/api/v1/ingest/docs?limit=50&cursor=0"
# → {"total": N, "docs": [...], "next_cursor": "50"}
```

### Delete a document

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/ingest/terms_conditions
```

> Ingest management endpoints honor API-key auth — `DELETE` always requires `X-API-Key`,
> and the others require it when `REQUIRE_AUTH_FOR_INGEST=true`.

### Review synthesized answers (learning-mode two-phase ingest)

```bash
# List entries awaiting review
curl "http://127.0.0.1:8000/api/v1/review/pending?limit=50&cursor=0"
# → {"total": N, "pending": [{"entry_id": "synthesized:…", "question": "…", "answer": "…", ...}], "next_cursor": null}

# Approve → embeds into the synthesized_answers collection (retrievable in learning mode)
curl -X POST http://127.0.0.1:8000/api/v1/review/synthesized:1a2b3c4d5e6f/approve

# Reject → discards without embedding
curl -X POST http://127.0.0.1:8000/api/v1/review/synthesized:1a2b3c4d5e6f/reject
```

> Review endpoints honor the same API-key dependency as ingest (gated by
> `REQUIRE_AUTH_FOR_INGEST`). The queue is only populated when requests run in
> `learning_review` mode.

## 💬 7. Chat API

### Chat Modes

The system supports four interaction modes via `CHAT_MODE` in `.env`:

| Mode | Behavior | When no docs match | Self-ingest | Use case |
|------|----------|--------------------|-------------|----------|
| **strict** (default) | Knowledge-base-only | Refuses: "I don't have information..." | No | Legal, medical, regulated domains |
| **open** | Free interaction | Uses general knowledge, honest about provenance | No | General assistants, brainstorming |
| **learning** | Free interaction + growing KB | Synthesizes answer, **embeds immediately** into ChromaDB | Yes (≥50 chars, no docs found) | Knowledge-building, research assistants |
| **learning_review** | Same as learning, **human-gated** | Synthesizes answer, **queues for review** (not embedded) | Queued for approval (≥50 chars, no docs found) | Curated KB growth with a moderator in the loop |

> **Learning quality gate:** Both learning modes only act on a response when (1) no documents matched the question (filling a knowledge gap) and (2) the answer is ≥50 characters. Synthesized entries live in a **separate ChromaDB collection** (`synthesized_answers`) consulted only in the learning modes — they never pollute `strict`/`open` retrieval.

> **`learning` vs `learning_review` (two-phase ingest):** In `learning`, a passing answer is embedded into `synthesized_answers` immediately. In `learning_review`, it is instead **queued in Redis for human review** — a moderator lists entries (`GET /api/v1/review/pending`) and **approves** (embeds into `synthesized_answers`, making it retrievable) or **rejects** (discards). This keeps unverified model output out of the vector store until a human signs off.

`CHAT_MODE` sets the server default; clients can override it **per request** (see below).

```env
# In .env
CHAT_MODE=strict    # or open, learning, learning_review
SELF_INGEST_MIN_LENGTH=50
```

### API versions

The API is **versioned**. New clients should use `/api/v1`; the unversioned `/api/*`
paths still work but are **deprecated** (responses carry `Deprecation`/`Sunset`/`Link`
headers). Errors everywhere use **RFC 9457 `application/problem+json`**.

| | `/api/v1` (recommended) | `/api` (legacy, deprecated) |
|---|---|---|
| Chat response | `{ answer, sources[], meta }` (typed) | `{ status, data, sources[] }` |
| Sources | structured objects (label, doc_id, score, page, snippet) | bare label strings |
| Streaming | `POST /api/v1/chat/stream` (SSE) | — |
| Ingest | `202` + background + poll | synchronous |

### `POST /api/v1/chat`

Request (`q` required; the rest are optional per-request overrides):

```jsonc
{
  "q": "what is the return policy?",
  "mode": "strict",        // strict | open | learning  (overrides server default)
  "lang": "auto",          // auto | en | ar | pt  (auto-detects Arabic/Portuguese vs English; pt = European Portuguese)
  "top_k": 3,              // 1..10 chunks to retrieve
  "score_threshold": 0.3   // 0..1 minimum relevance
}
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/chat" \
  -H "Content-Type: application/json" -H "X-User-Id: user_123" \
  -d '{"q":"what is the return policy?"}'
```

Response:

```json
{
  "answer": "Returns are accepted within 30 days of purchase.",
  "sources": [
    {"label": "return_policy.pdf", "doc_id": "return_policy", "score": 0.82, "page": 3, "snippet": "Customers may return..."}
  ],
  "meta": {"mode": "strict", "lang": "en", "self_ingested": false, "grounded": "supported", "grounded_score": 0.83, "correlation_id": "…", "model": "gpt-4o-mini"}
}
```

### `POST /api/v1/chat/stream` (Server-Sent Events)

Streams the answer token-by-token. Same request body. Event sequence:

```
event: token    data: {"delta": "Returns"}
event: token    data: {"delta": " are"}
event: sources  data: {"sources": [ … ]}
event: done     data: {"meta": { … }}
```

On failure an `event: error` frame is emitted (no internal detail). Each response
includes a `X-Correlation-Id` header and rate-limit headers
(`X-RateLimit-Limit/Remaining/Reset`, plus `Retry-After` on `429`).

> `X-User-Id` scopes per-user conversation memory (defaults to `anonymous`). It is
> validated (`[A-Za-z0-9_.@-]{1,128}`) and namespaced internally.

> **Groundedness (`meta.grounded`):** when documents back the answer, `verify_answer`
> reports `supported | partial | unsupported` (+ `grounded_score`). In **strict** mode an
> `unsupported` answer is replaced by the "Not in the knowledge base" refusal and its
> sources cleared (`STRICT_REFUSE_ON_UNGROUNDED`). On the streaming path this applies to
> the stored answer + `done` meta (tokens already streamed cannot be retracted).

### Feedback (`POST /api/v1/feedback`)

Capture 👍/👎 on an answer (open to end users; the turn's correlation id is captured
automatically). Downvotes can be exported into the RAGAS golden set to close the loop.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{"rating":"down","reason":"cited the wrong policy","question":"return window?"}'
# → 201  {"feedback_id":"a1b2c3d4e5f6","rating":"down","status":"recorded"}

# Operators list feedback (API-key gated, like review/ingest):
curl "http://127.0.0.1:8000/api/v1/feedback?rating=down&limit=50&cursor=0"
```

## 🏥 8. Health & Readiness

### Startup health (cached flags)

```bash
curl http://127.0.0.1:8000/health
```

Returns `ok` or `degraded` based on Redis and ChromaDB connectivity at startup time.

### Live readiness probe

```bash
curl http://127.0.0.1:8000/ready
```

Returns `200` with `{"status": "ready"}` only if both Redis and ChromaDB respond right now. Returns `503` with dependency-specific error details if either is down. Use this for Kubernetes readiness probes or load balancer health checks.

## 🖥️ Web Client

A reference single-page client lives in [`web/`](web/) (Vite + React + TypeScript). It
demonstrates the v1 API end-to-end with **production-grade UX**:

- **Streaming chat** (SSE) with typing indicator, smart autoscroll (pin-to-bottom), and a **"New messages"** affordance when scrolled up
- **Markdown rendering** with `react-markdown` + `remark-gfm` — tables, strikethrough, autolinks; fenced code blocks are buffered until the closing fence arrives so no half-rendered blobs flicker
- **Shiki syntax highlighting** (lazy-loaded, one chunk per language) with **Copy** button per code block
- **Trust signals** — confidence badge (High/Medium/Low from `meta.grounded_score`), mode chip, provenance chip ("AI-synthesized" warning), and structured citation cards with score meter, expandable snippet, and copy button
- **Strict-mode refusal UX** — "Not in the knowledge base" card with a one-click **"Answer from general knowledge"** CTA that re-sends in `open` mode
- **Suggested prompt chips** — 3–4 mode/language-aware suggestions on empty state and after each turn (e.g., "Explain in Arabic", "Answer from general knowledge")
- **Inline feedback** — 👍/👎 buttons on every assistant message, with optional reason input on downvote; submits `POST /api/v1/feedback` automatically with `correlation_id`
- **Conversation management** — **+ New** button rotates `X-User-Id` for a fresh chat; **Export** dropdown downloads transcript as JSON or Text; TTL note (~24h) in footer
- **Error handling** — friendly problem+json messages, rate-limit countdown from `Retry-After`, correlation ID copy button for support
- **Health badge** — polls `/health`, shows degraded state (amber), on-demand `/ready` probe with dependency details (Redis/ChromaDB)
- **Accessibility** — RTL/Arabic (`dir="rtl"`, `lang="ar"`), deferred screen-reader announcements (once per completed message, not per token), visible focus rings, `prefers-reduced-motion` support
- **Keyboard** — Enter to send, Shift+Enter for newline, Escape to stop streaming, arrow keys navigate citation cards
- **Controls** — per-request mode/language selectors with `sessionStorage` persistence; character counter (2000 char limit)

```bash
cd web
bun install      # or npm install
bun run dev      # http://localhost:5173 (proxies /api and /health to :8000)
bun run build    # tsc -b && vite build → web/dist/
```

See [`web/README.md`](web/README.md) for details.

## 📚 Further Documentation

- [`user_guidelines.md`](user_guidelines.md) — end-user / API-consumer guide (modes,
  languages, citations, errors, rate limits, streaming, worked examples).
- [`PTD.md`](PTD.md) — Project Technical Document (architecture, data flow, components,
  storage, security, observability, testing, CI/CD, deployment, design decisions).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CHANGELOG.md`](CHANGELOG.md)

## Observability

Every request is tagged with a **correlation ID** (`X-Correlation-Id`) that propagates through all log calls, graph nodes, and service layers. This enables tracing a single request across Redis operations, ChromaDB retrievals, LLM calls, and ingest pipeline steps.

- **Correlation ID middleware** — injects or preserves `X-Correlation-Id` header, stores in `contextvars.ContextVar` for async-safe propagation
- **Request timing middleware** — logs method, path, status code, duration (ms), and correlation ID
- **Structured JSON logging** — set `LOG_FORMAT=json` for Datadog, CloudWatch, or ELK ingestion. Each log line includes `timestamp`, `level`, `correlation_id`, and message fields.
- **Log rotation** — `logs/app.log` capped at 10 MB with 5 rotated backups

```env
LOG_FORMAT=json        # "text" (default) or "json" for log aggregators
```

## 🧠 Core System Design

### 🔹 Memory System

Redis stores:
- Full conversation history
- Running conversation summary (for long-term context)
- TTL-based expiry (configurable via `REDIS_TTL_SECONDS`)

### 🔹 RAG System — Incremental Ingestion + MMR Retrieval

#### Ingestion Flow

<div align="center">

```
POST /api/ingest  { file_name, s3_url }
         │
         ▼
┌─────────────────────────────────────────────────┐
│  STEP 1 — Download                              │
│  requests.get(s3_url, stream=True)              │
│  • Enforce MAX_FILE_SIZE_MB limit               │
│  • Write to temp .pdf file on disk              │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  STEP 2 — File-level dedup check                │
│  SHA-256(file) → new_file_hash                  │
│                                                 │
│  Redis: GET ingest_status:{doc_id}.file_hash    │
│  ┌─ same hash? ──────────────────────────────┐  │
│  │  return { status: "skipped",              │  │
│  │           reason: "file unchanged" }      │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  Redis: HGET ingest:content_hashes new_hash     │
│  ┌─ hash owned by different doc? ────────────┐  │
│  │  return { status: "skipped",              │  │
│  │           reason: "duplicate content      │  │
│  │           already ingested as '{doc}'" }  │  │
│  └───────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────┘
                     │  (file is new or changed)
                     ▼
┌─────────────────────────────────────────────────┐
│  STEP 3 — Parse & chunk                         │
│  PyPDFLoader  →  raw pages                      │
│  RecursiveCharacterTextSplitter                 │
│    chunk_size=800, overlap=100                  │
│    separators: [\n\n, \n, ., " ", ""]           │
│  _clean_text() — collapse extra whitespace      │
│  MD5(chunk_text) → chunk_hash per chunk         │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  STEP 4 — Chunk-level diff                      │
│                                                 │
│  old_hashes = Redis SMEMBERS doc_chunks:{id}    │
│  new_hashes = set of MD5s from step 3           │
│                                                 │
│  stale = old_hashes − new_hashes                │
│    └─► delete those chunk IDs from ChromaDB     │
│                                                 │
│  fresh = new_hashes − old_hashes                │
│    └─► embed + add only these to ChromaDB       │
│                                                 │
│  unchanged = intersection → skip (no API call)  │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  STEP 5 — Update Redis registry                 │
│  DEL  doc_chunks:{doc_id}                       │
│  SADD doc_chunks:{doc_id}  ← new_hashes         │
│  SADD ingest:doc_ids       ← doc_id             │
│  HDEL ingest:content_hashes old_file_hash       │
│  HSET ingest:content_hashes new_hash → doc_id   │
│  HSET ingest_status:{doc_id} status/hash/counts │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
         { status: "done", added, removed, total }
```

</div>

**Redis keys used by the ingest pipeline:**

| Key | Type | Purpose |
|-----|------|---------|
| `ingest_status:{doc_id}` | Hash | Status, file hash, version, chunk counts per document |
| `doc_chunks:{doc_id}` | Set | MD5 hash of every chunk in the current version |
| `ingest:doc_ids` | Set | Global list of all ingested doc IDs |
| `ingest:content_hashes` | Hash | Maps `file_hash → doc_id` — catches same PDF under a different filename |

#### Retrieval — Score Gate + MMR (Hallucination Prevention)

Retrieval runs in two steps, with behavior depending on `CHAT_MODE`:

<div align="center">

```
User question
      │
      ▼
Step 1 — Relevance gate
similarity_search k=1  →  score < threshold?
      │                         │
      │    ┌─── CHAT_MODE ──────┤
      │    │                     │
      │    │ strict:             │ open/learning:
      │    │ docs = ""           │ docs = best available
      │    │ → refusal prompt    │ → "use general knowledge"
      │    │                     │ prompt
      │    │                     │
      │ score ≥ threshold (question is on-topic)
      ▼
Step 2 — MMR retrieval
max_marginal_relevance_search k=3, fetch_k=10
      │
      ▼
3 diverse, relevant chunks → LLM → grounded answer
```

</div>

**Step 1 — Score gate:** fetches the single closest chunk and checks its cosine similarity score. Behavior depends on `CHAT_MODE`:
- **Strict mode:** If even the best match is below threshold, the question is off-topic and no context is sent to the LLM (refusal prompt).
- **Open/learning mode:** Below-threshold matches are still provided to the LLM as weak grounding signals. The prompt instructs the LLM to use general knowledge when context is weak, and to be honest about provenance.

**Step 2 — MMR:** only runs when step 1 passes the threshold. Fetches 10 candidates and picks the 3 that are both relevant AND diverse — avoiding 3 near-identical paragraphs being sent to the LLM.

**Step 3 — Self-ingest (learning modes only):** If the retrieval score was below threshold (knowledge gap) and the LLM's answer is ≥50 characters, the answer is captured with `source_type=synthesized` metadata. In `learning` mode it is embedded into the `synthesized_answers` collection immediately; in `learning_review` mode it is **queued for human review** instead, and only embedded once a moderator approves it (see [Chat Modes](#chat-modes) and the `/api/v1/review/*` endpoints). This grows the knowledge base — optionally with a human in the loop.

**ChromaDB is configured with cosine distance** (`hnsw:space: cosine`) — the correct metric for text embeddings. Without this, scores are L2-based and can go negative, making the threshold meaningless.

> Threshold is configurable via `RETRIEVAL_SCORE_THRESHOLD` in `.env` (default `0.3`). Raise to `0.7` for stricter grounding, lower to `0.2` if too many valid questions are being rejected.

### 🔹 LLM Layer

Configurable via environment variables and chat mode:
- `CHAT_MODE=strict` — Knowledge-base-only. Refuses outside topics.
- `CHAT_MODE=open` — Free interaction. Uses general knowledge when no documents match.
- `CHAT_MODE=learning` — Free interaction + auto-ingests synthesized answers into ChromaDB.
- `CHAT_MODE=learning_review` — Like learning, but synthesized answers are queued for human approval (`/api/v1/review/*`) before being embedded.
- Uses conversation summary (long-term memory)
- Uses recent messages (short-term memory)
- Uses retrieved context (RAG)
- Generates final response in the user's language (Arabic / English / European Portuguese)

> **Language detection (`lang: "auto"`):** Arabic is detected by script. A fast,
> dependency-free heuristic (distinctive Portuguese diacritics + a stopword-frequency
> ratio) handles the vast majority of inputs; only short, unaccented, genuinely ambiguous
> fragments fall through to the [lingua](https://github.com/pemistahl/lingua-py) EN/PT
> statistical model. Selecting `pt` (or `en`/`ar`) explicitly bypasses detection entirely.
> Portuguese output uses Portugal spelling/vocabulary (pt-PT).

## Security

### Authentication

API key authentication via FastAPI dependency injection (`middlewares/auth.py`):

- `DELETE /api/ingest/{doc_id}` **always** requires `X-API-Key` when `API_KEY` is set
- Other ingest endpoints require it only when `REQUIRE_AUTH_FOR_INGEST=true`
- Empty `API_KEY` skips auth (backward-compatible dev mode)

```bash
curl -X DELETE http://127.0.0.1:8000/api/ingest/doc_id \
  -H "X-API-Key: your-secret-api-key"
```

### SSRF Protection

`utils/security.py` blocks downloads from:
- Private IP ranges (10/8, 172.16/12, 192.168/16, 127/8)
- Link-local addresses (169.254/16, fe80::/10)
- Cloud metadata endpoints (169.254.169.254, metadata.google.internal)
- Loopback (::1)

Controlled via `ALLOWED_HOSTS` env var. `["*"]` allows all public hosts (still blocks private IPs).

### Rate Limiting

60 requests/minute per IP, Redis-backed. Behind reverse proxies:
- `TRUSTED_PROXIES` — CIDR ranges of trusted load balancers (e.g., `["10.0.0.0/8", "172.16.0.0/12"]`)
- `X-Forwarded-For` and `X-Real-IP` header handling for real client IP extraction
- Fails open on Redis error (availability > strict enforcement)

### CORS

Default `[]` — production must explicitly opt-in. Never use `["*"]` in production.

```env
CORS_ORIGINS=["https://your-domain.com"]
```

### Startup Validation

Pydantic `model_validator` ensures required API keys are present for the chosen `LLM_PROVIDER`. Raises `ValueError` at startup instead of failing at runtime with opaque errors.

## Security Audit History

| Date | Score | Grade | Scope |
|------|-------|-------|-------|
| 2026-05-28 (initial) | 72/100 | C+ | Identified 3 critical, 4 high, 5 medium, 5 low, 5 informational findings |
| 2026-05-28 (post-elevation) | 95/100 | A+ | All critical/high findings resolved; auth, SSRF, rate limiting, CORS, logging, CI hardened |

**Critical findings resolved:**
- Dependency hell (numpy/torch incompatibility) → pinned compatible versions
- Deserialization vulnerability (langchain-core CVE-2026-44843) → upgraded to ≥1.3.3
- Permissive CORS (`["*"]`) → default `[]`
- Missing auth on DELETE endpoint → API key dependency
- SSRF in download pipeline → private IP + metadata blocking
- Rate limiter proxy blindness → trusted proxy CIDR support
- Broad exception handling → specific exception classes
- Missing startup validation → Pydantic validators

Full audit reports: `audit_artifacts/AUDIT_REPORT.md` and `audit_artifacts/FINAL_AUDIT.md`

## 🧠 Key Features

* ✅ Conversational memory (short + long-term via Redis)
* ✅ RAG retrieval with mode-aware score gate + MMR diversity ranking
* ✅ Context-aware query rewriting — condenses multi-turn follow-ups into a standalone search query before retrieval (`QUERY_REWRITE_ENABLED`)
* ✅ Groundedness / faithfulness verification — `meta.grounded` (supported/partial/unsupported); strict mode refuses answers unsupported by the retrieved chunks (`GROUNDEDNESS_ENABLED`)
* ✅ Persistent feedback loop — `POST /api/v1/feedback` (👍/👎 + reason) → operator queue + export of downvotes to the RAGAS golden set
* ✅ Provider resilience — retry transient 429/5xx/timeouts with backoff + in-process circuit breaker (`utils/resilience.py`)
* ✅ Durable, retryable ingestion — `INGEST_MODE=queue` with a Redis-backed worker that survives restarts (idempotent, retrying)
* ✅ Configurable persona / domain / refusal copy — rebrand the assistant with `ASSISTANT_NAME` / `KNOWLEDGE_DOMAIN` / `ESCALATION_MESSAGE` (defaults unchanged)
* ✅ Optional hybrid retrieval — dense + BM25 fused via RRF (`RETRIEVAL_STRATEGY=hybrid`) for acronym/SKU/exact-phrase recall
* ✅ Four chat modes: strict (knowledge-base-only), open (general knowledge), learning (growing KB), learning_review (review-gated KB growth)
* ✅ Self-ingest in learning mode — synthesized answers captured with provenance metadata
* ✅ `learning_review` mode — two-phase ingest: synthesized answers queued for human approve/reject before embedding (`/api/v1/review/*`)
* ✅ Guardrails — input prompt-injection/jailbreak blocking + output PII masking and length cap (config-toggleable)
* ✅ RAGAS evaluation harness — offline faithfulness / relevancy / context precision+recall (`eval/`)
* ✅ Versioned, typed API (`/api/v1`) — Pydantic response envelopes with RFC 9457 `application/problem+json` errors; unversioned `/api/*` still works but is deprecated
* ✅ SSE streaming — `POST /api/v1/chat/stream` emits `token` → `sources` → `done` (and `error`) Server-Sent Events
* ✅ Per-request controls — `mode`, `lang`, `top_k`, `score_threshold` override server defaults per call
* ✅ Reference web client (`web/`) — Vite + React + TypeScript SPA with production UX: streaming chat with smart autoscroll, markdown + Shiki highlighting, trust signals (confidence badge, mode/provenance chips, citation cards with score meter), strict-mode refusal CTA, suggested prompt chips, inline 👍/👎 feedback, conversation export (JSON/Text), new-chat rotation, rate-limit countdown, health badge with `/ready` probe, `sessionStorage` persistence, RTL/Arabic, deferred SR announcements, `prefers-reduced-motion`, keyboard navigation, and a `learning_review` reviewer panel
* ✅ 14 LLM providers with universal OpenAI-compatible adapter + provider aliases
* ✅ 7+ embedding models via FastEmbed (ONNX, ~50MB, zero CVEs) + model registry
* ✅ API key authentication (FastAPI dependency injection) on destructive ingest endpoints
* ✅ SSRF protection — blocks private IPs and cloud metadata endpoints
* ✅ Proxy-aware rate limiting — 60 requests/minute per IP with CIDR trust configuration
* ✅ CORS hardened — default `[]`, production must opt-in
* ✅ Observability — correlation ID tracing, request timing, structured JSON logging
* ✅ Kubernetes-ready — cached `/health` + live `/ready` probes with dependency-specific error details
* ✅ Structured citations — each source carries `label`, `doc_id`, `score`, `page`, and `snippet` (v1 API; legacy `/api/chat` keeps bare label strings)
* ✅ Conversational follow-ups — context-aware replies when no document match exists
* ✅ Multi-format ingestion — PDF, TXT, Markdown, DOCX, HTML via a pluggable loader registry (`ingest/loaders.py`)
* ✅ Two ingest paths — remote URL pull **or** local file upload (multipart), so documents can stay on-prem / private
* ✅ Incremental ingestion — only re-embeds changed chunks, not the whole document
* ✅ Ingestion safeguards — duplicate submission protection, file size limits, status polling endpoint
* ✅ Global duplicate detection — same PDF under different names caught via content hash
* ✅ Multilingual responses (Arabic / English / European Portuguese) — hybrid auto-detection: Arabic by script + a dependency-free Portuguese diacritic/stopword heuristic, with a [lingua](https://github.com/pemistahl/lingua-py) EN/PT statistical fallback for short ambiguous inputs
* ✅ LangGraph workflow orchestration (8-node pipeline)
* ✅ FastAPI production API layer
* ✅ Dockerized — cloud deployment (docker-compose.yml) + local deployment (docker-compose.local.yml with Ollama)
* ✅ Structured logging to console + rotating file (logs/app.log, 10 MB cap)
* ✅ 300+ tests covering adapters, graph nodes, builder, resilience, groundedness, feedback, ingest queue, rate limiter, security, API endpoints (97% coverage) + a hermetic retrieval-regression test

## 🧩 TODO (Roadmap)

* [x] Multi-provider LLM support (14 providers)
* [x] FastEmbed local embeddings (7+ models, ONNX-based)
* [x] Chat modes (strict, open, learning with self-ingest, learning_review with two-phase ingest)
* [x] Local deployment (Ollama + FastEmbed, zero API keys)
* [x] Provider comparison documentation
* [x] CI/CD pipeline (ruff, bandit, pip-audit, coverage, Docker build)
* [x] Security elevation (auth, SSRF, rate limiting, CORS, observability) — 72→95 audit score
* [x] Guardrails (input prompt-injection blocking + output PII masking / length cap)
* [x] Evaluation (RAGAS) — offline harness (`eval/`)
* [x] Learning mode review workflow (two-phase ingest for synthesized entries)
* [x] Context-aware query rewriting (condense follow-ups before retrieval)
* [x] Groundedness / faithfulness verification (strict-mode anti-hallucination gate)
* [x] Persistent feedback + closed quality loop (feedback → review queue / golden set)
* [x] Provider retry/backoff + circuit breaker
* [x] Durable, retryable ingestion (queue + worker)
* [x] Configurable persona / domain / refusal copy
* [x] Hermetic retrieval-regression test + opt-in scheduled eval CI
* [x] Reviewer UI for the learning_review queue (web)
* [ ] Hybrid retrieval + reranking — scaffolding shipped (`RETRIEVAL_STRATEGY`); promote to default once the eval proves a lift

## ⚡ Tech Stack

* **Backend:** FastAPI
* **LLM:** 14 providers — OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek, Together, Mistral, Fireworks, OpenRouter, vLLM, LM Studio, llama.cpp
* **Embeddings:** OpenAI / FastEmbed (7+ models) / HuggingFace
* **Orchestration:** LangGraph
* **Framework:** LangChain
* **Vector DB:** ChromaDB (dense) + BM25 (`rank-bm25`, optional hybrid)
* **Cache / Memory / Queue:** Redis (memory, rate limiting, ingest registry + durable ingest queue)
* **Resilience:** tenacity (retry/backoff) + in-process circuit breaker
* **Runtime:** Python 3.10+
* **Container:** Docker + Docker Compose (API + worker + Redis; local + cloud)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide — setup, code standards, testing, security, and PR workflow.

**Quick start:**
```bash
conda create -n chat-bot python=3.10 && conda activate chat-bot
pip install -r requirements.txt -r requirements-dev.txt
pytest  # 300+ tests, 97% coverage
```

**Good first contributions:**
- Add a new document loader (DOCX, TXT, HTML) in `ingest/`
- Expand the guardrail patterns (`guardrails/`) or the RAGAS golden set (`eval/golden.jsonl`)
- Wire a concrete reranker into `ingest/retrieval.rerank` (FastEmbed / cross-encoder) behind `RETRIEVAL_STRATEGY=hybrid_rerank`
- Grow the eval golden set (`eval/golden.jsonl`) or the retrieval-regression corpus (`tests/test_retrieval_regression.py`)
- Add a new FastEmbed model to the registry in `utils/embedding_adapter.py`

> Please open an issue before starting large changes so we can discuss approach first.

---

## 📌 Summary

This project demonstrates a **real-world production architecture for AI chatbots** combining:

> RAG + Memory + LLM + Backend Engineering + Security Hardening

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history, detailed changes, and the v1.0.0 → v2.0.0 comparison table.

## Fork History

This repository (`pt-act/chat-bot`) is a hardened fork of [`hasandeveloper/chat-bot`](https://github.com/hasandeveloper/chat-bot) with significant enhancements:

| Dimension | Upstream (v1.0.0) | This Fork (v2.4.0) |
|-----------|--------------------|---------------------|
| LLM providers | 3 (OpenAI, Anthropic, Groq) | 14 (universal adapter) |
| Chat modes | 1 (strict only) | 4 (strict, open, learning, learning_review) |
| Multi-turn retrieval | Raw last message | Context-aware query rewriting (condense follow-ups) |
| Answer faithfulness | Unverified | Groundedness verification + strict-mode refusal of unsupported answers |
| Feedback | None | Persistent 👍/👎 (`/api/v1/feedback`) → review queue + golden-set export |
| Provider failures | Fail the turn | Retry transient 429/5xx with backoff + circuit breaker |
| Ingestion durability | In-process `BackgroundTasks` | Optional durable Redis queue + worker (survives restarts, retries) |
| Persona / branding | Hard-coded "our company" | Configurable name / domain / refusal copy (defaults unchanged) |
| Retrieval strategy | Dense MMR | Dense MMR + optional hybrid (BM25 + RRF) |
| Self-ingestion | None | Learning mode with quality gate + two-phase review (`learning_review`: queued for human approve/reject before embedding) |
| Languages | 2 (English / Arabic) | 3 (English / Arabic / European Portuguese) + hybrid auto-detection (script + diacritic/stopword heuristic + lingua fallback) |
| Document formats | PDF only | PDF / TXT / Markdown / DOCX / HTML (pluggable loader registry) |
| Ingest sources | URL / S3 pull | URL pull + local file upload (multipart, on-prem friendly) |
| HTTP API | Unversioned `/api/*` | Versioned `/api/v1` (typed envelopes) + RFC 9457 `problem+json` errors |
| Streaming | None | SSE token streaming (`POST /api/v1/chat/stream`) |
| Guardrails | None | Input prompt-injection blocking + output PII masking / length cap |
| Evaluation | None | RAGAS offline harness (faithfulness / relevancy / context precision+recall) |
| Web client | None | Vite + React + TypeScript SPA with production UX: streaming with smart autoscroll, markdown + Shiki highlighting, trust signals (confidence badges, citation cards with score meters, mode/provenance chips), strict-mode refusal CTA, suggested prompt chips, inline 👍/👎 feedback, conversation export (JSON/Text), new-chat rotation, rate-limit countdown, health badge with `/ready` probe, `sessionStorage` persistence, RTL/Arabic, deferred screen-reader announcements, `prefers-reduced-motion`, keyboard navigation |
| Authentication | None | API key (FastAPI DI) |
| SSRF protection | None | Private IP + metadata blocking |
| Rate limiting | Direct IP only | Proxy-aware (CIDR, X-Forwarded-For) |
| Observability | None | Correlation ID + request timing |
| Logging | Text only | Text + JSON (structured) |
| Health probes | `/health` (static) | `/health` (cached) + `/ready` (live) |
| CI/CD | Basic (ruff + pytest) | Full (ruff + bandit + pip-audit + coverage + Docker) |
| Test count | ~10 | 300+ (97% coverage) + hermetic retrieval-regression |
| Audit score | 72/100 (C+) | 95/100 (A+) |
| Local deployment | None | docker-compose.local.yml (Ollama + FastEmbed) |

Contributions to both repositories are welcome.
