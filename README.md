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
- [Health Check](#-8-health-check)
- [Core System Design](#-core-system-design)
- [Key Features](#-key-features)
- [TODO](#-todo-roadmap)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [Summary](#-summary)

---

## 📌 Project Overview

This project is a **production-style AI chatbot backend** built using:

* 🧠 LangGraph for conversation orchestration
* 🔍 RAG pipeline using ChromaDB
* 💬 Multi-LLM support (OpenAI, Anthropic, Groq)
* ⚡ FastAPI for backend APIs
* 🧠 Redis for memory storage

It supports:

* Conversational memory
* Document-based Q&A (RAG)
* Three chat modes: strict (knowledge-base-only), open (free interaction), learning (auto-growing KB)
* 14 LLM providers (OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek, Together, Mistral, Fireworks, OpenRouter, vLLM, LM Studio, llama.cpp)
* 7+ embedding models via FastEmbed (ONNX-based, zero CVEs)
* Fully local deployment with Ollama (zero cloud API keys)
* Multilingual responses (Arabic / English)
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
           │  2. retrieve_context (Chroma)│ ← mode-aware score gate
           │  3. generate_answer  (LLM)   │ ← mode-specific prompt
           │  4. self_ingest  (Chroma)    │ ← learning mode only
           │  5. summarize                │
           │  6. store_memory  (Redis)    │
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
   - memory → retrieval → reasoning → self-ingest (if learning) → response
5. LLM generates a final contextual answer — mode-specific prompt controls behavior
6. In learning mode, synthesized answers are auto-ingested into ChromaDB as new knowledge
7. Conversation is updated + summarized for future use

## 🗂️ Project Structure

```
chat-bot/
├── controllers/          # Route handler logic (chat, ingest endpoints)
├── middlewares/          # Rate limiting middleware
├── db/                   # Redis and ChromaDB clients
├── graph/
│   ├── builder.py        # LangGraph pipeline definition (6 nodes + edges)
│   ├── state.py          # State TypedDict (chat_mode, best_score, last_answer, self_ingested)
│   └── nodes/            # Individual graph nodes
│       ├── load_memory.py       # Load conversation history from Redis
│       ├── retrieve_context.py  # Mode-aware score gate + MMR retrieval
│       ├── generate_answer.py   # Mode-specific prompt → LLM call
│       ├── self_ingest.py       # Auto-ingest synthesized answers (learning mode)
│       ├── store_memory.py      # Save conversation to Redis
│       └── summarize.py        # Conversation summarization
├── ingest/               # Incremental document ingestion pipeline
├── prompts/
│   ├── answer.py         # 3 mode-specific prompt builders (strict, open, learning)
│   └── summarize.py      # Conversation summarization prompt
├── schemas/
│   ├── chat.py           # ChatRequest schema
│   └── ingest.py         # IngestRequest schema
├── services/
│   └── chat_service.py   # Injects chat_mode from settings, returns self_ingested flag
├── tests/                # Pytest test suite (91 tests across 5 test files)
├── main.py               # App entrypoint
├── config.py             # Settings (pydantic-settings) — CHAT_MODE, SELF_INGEST_MIN_LENGTH
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
git clone https://github.com/hasandeveloper/chat-bot.git
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

CHAT_MODE=strict                        # strict | open | learning — see Chat Modes section
SELF_INGEST_MIN_LENGTH=50               # minimum answer length for auto-ingest in learning mode
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

### Ingest a document

```bash
curl -X POST "http://127.0.0.1:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "file_name": "terms_conditions",
    "s3_url": "https://your-s3-url.pdf"
  }'
```

### Check ingest status

```bash
curl http://127.0.0.1:8000/api/ingest/status/terms_conditions
```

### List all ingested documents

```bash
curl http://127.0.0.1:8000/api/ingest/docs
```

### Delete a document

```bash
curl -X DELETE http://127.0.0.1:8000/api/ingest/terms_conditions
```

## 💬 7. Chat API

### Chat Modes

The system supports three interaction modes via `CHAT_MODE` in `.env`:

| Mode | Behavior | When no docs match | Self-ingest | Use case |
|------|----------|--------------------|-------------|----------|
| **strict** (default) | Knowledge-base-only | Refuses: "I don't have information..." | No | Legal, medical, regulated domains |
| **open** | Free interaction | Uses general knowledge, honest about provenance | No | General assistants, brainstorming |
| **learning** | Free interaction + growing KB | Synthesizes answer, auto-saves to ChromaDB | Yes (≥50 chars, no docs found) | Knowledge-building, research assistants |

> **Learning mode quality gate:** Only auto-ingests responses when (1) no documents matched the question (filling a knowledge gap) and (2) the answer is ≥50 characters. All synthesized entries are tagged with `source_type=synthesized` so you can distinguish model-generated content from ingested documents.

```env
# In .env
CHAT_MODE=strict    # or open, or learning
SELF_INGEST_MIN_LENGTH=50
```

### Endpoint

```
POST /api/chat
```

### Request

```json
{
  "q": "what are the return policies?"
}
```

### Example

```bash
curl -X POST "http://127.0.0.1:8000/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: user_123" \
  -d '{"q":"what is return policy?"}'
```

> `X-User-ID` identifies the user session — memory is stored and loaded per user. Defaults to `anonymous` if omitted.

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

**Step 3 — Self-ingest (learning mode only):** If the retrieval score was below threshold (knowledge gap) and the LLM's answer is ≥50 characters, the answer is auto-ingested into ChromaDB with `source_type=synthesized` metadata. This creates a growing knowledge base that fills gaps over time.

**ChromaDB is configured with cosine distance** (`hnsw:space: cosine`) — the correct metric for text embeddings. Without this, scores are L2-based and can go negative, making the threshold meaningless.

> Threshold is configurable via `RETRIEVAL_SCORE_THRESHOLD` in `.env` (default `0.3`). Raise to `0.7` for stricter grounding, lower to `0.2` if too many valid questions are being rejected.

### 🔹 LLM Layer

Configurable via environment variables and chat mode:
- `CHAT_MODE=strict` — Knowledge-base-only. Refuses outside topics.
- `CHAT_MODE=open` — Free interaction. Uses general knowledge when no documents match.
- `CHAT_MODE=learning` — Free interaction + auto-ingests synthesized answers into ChromaDB.
- Uses conversation summary (long-term memory)
- Uses recent messages (short-term memory)
- Uses retrieved context (RAG)
- Generates final response in the user's language (Arabic / English)

## 🧠 Key Features

* ✅ Conversational memory (short + long-term via Redis)
* ✅ RAG retrieval with mode-aware score gate + MMR diversity ranking
* ✅ Three chat modes: strict (knowledge-base-only), open (general knowledge), learning (growing KB)
* ✅ Self-ingest in learning mode — auto-saves synthesized answers to ChromaDB
* ✅ 14 LLM providers with universal OpenAI-compatible adapter + provider aliases
* ✅ 7+ embedding models via FastEmbed (ONNX, ~50MB, zero CVEs) + model registry
* ✅ Citations — every answer includes which source documents were used
* ✅ Conversational follow-ups — context-aware replies when no document match exists
* ✅ Incremental ingestion — only re-embeds changed chunks, not the whole document
* ✅ Ingestion safeguards — duplicate submission protection, file size limits, status polling endpoint
* ✅ Global duplicate detection — same PDF under different names caught via content hash
* ✅ Rate limiting — 60 requests/minute per IP (Redis-backed, returns 429 on breach)
* ✅ SSRF protection — blocks private IPs and cloud metadata endpoints
* ✅ Multilingual responses (Arabic / English auto-detected)
* ✅ LangGraph workflow orchestration
* ✅ FastAPI production API layer
* ✅ Dockerized — cloud deployment (docker-compose.yml) + local deployment (docker-compose.local.yml with Ollama)
* ✅ Structured logging to console + rotating file (logs/app.log, 10 MB cap)
* ✅ 91 tests covering adapters, graph nodes, builder, rate limiter, security

## 🧩 TODO (Roadmap)

* [x] Multi-provider LLM support (14 providers)
* [x] FastEmbed local embeddings (7+ models, ONNX-based)
* [x] Chat modes (strict, open, learning with self-ingest)
* [x] Local deployment (Ollama + FastEmbed, zero API keys)
* [x] Provider comparison documentation
* [ ] Guardrails
* [ ] Evaluation (RAGAS)
* [ ] CI/CD pipeline hardening
* [ ] Learning mode review workflow (two-phase ingest for synthesized entries)

## ⚡ Tech Stack

* **Backend:** FastAPI
* **LLM:** 14 providers — OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek, Together, Mistral, Fireworks, OpenRouter, vLLM, LM Studio, llama.cpp
* **Embeddings:** OpenAI / FastEmbed (7+ models) / HuggingFace
* **Orchestration:** LangGraph
* **Framework:** LangChain
* **Vector DB:** ChromaDB
* **Cache / Memory:** Redis
* **Runtime:** Python 3.10+
* **Container:** Docker + Docker Compose (cloud + local)

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository and clone your fork
2. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Set up the dev environment** — pick one:

   **Option A — Local (Conda)**
   ```bash
   conda create -n chat-bot python=3.10
   conda activate chat-bot
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

   **Option B — Docker**
   ```bash
   docker-compose up --build
   ```
   The API will be available at `http://127.0.0.1:8000` and Redis starts automatically.
    To run tests inside the container:
    ```bash
    docker-compose -f docker-compose.test.yml up --build -d
    docker-compose -f docker-compose.test.yml exec api pytest
    ```

4. **Run the tests** before making changes:
    ```bash
    pytest                     # local
    docker-compose -f docker-compose.test.yml exec api pytest   # Docker
    ```
5. **Make your changes**, then run tests again to confirm nothing broke
6. **Install git-secrets** to prevent accidentally committing API keys:
   ```bash
   # macOS
   brew install git-secrets
   git secrets --install
   git secrets --register-aws
   git secrets --register-azure

   # Scan before committing
   git secrets --scan
   ```
7. **Open a Pull Request** with a clear description of what you changed and why

**Good first contributions:**
- Add a new document loader (e.g. DOCX, TXT) in `ingest/`
- Improve test coverage in `tests/`
- Add a two-phase review workflow for learning mode synthesized entries
- Add Guardrails or RAGAS evaluation (see TODO)
- Add a new FastEmbed model to the registry in `utils/embedding_adapter.py`

**Project layout to get oriented:**
- `graph/nodes/` — each file is one step in the LangGraph pipeline
- `graph/nodes/self_ingest.py` — learning mode auto-ingest logic
- `graph/nodes/retrieve_context.py` — mode-aware score gate + MMR retrieval
- `prompts/answer.py` — 3 mode-specific prompt builders (strict, open, learning)
- `ingest/policies.py` — full ingestion pipeline (download → chunk → diff → embed)

> Please open an issue before starting large changes so we can discuss approach first.

---

## 📌 Summary

This project demonstrates a **real-world production architecture for AI chatbots** combining:

> RAG + Memory + LLM + Backend Engineering
