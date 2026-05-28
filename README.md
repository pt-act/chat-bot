<div align="center">

# 🤖 AI Chatbot Backend Service

### LangChain + LangGraph + RAG + FastAPI

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![LangChain](https://img.shields.io/badge/LangChain-LLM%20Orchestration-orange)
![ChromaDB](https://img.shields.io/badge/VectorDB-Chroma-purple)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20%7C%20Anthropic%20%7C%20Groq-black)

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
* Strict knowledge-base-only responses — the bot refuses to answer outside ingested documents
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
          │  2. retrieve_context (Chroma)│
          │  3. generate_answer  (LLM)   │
          │  4. summarize                │
          │  5. store_memory  (Redis)    │
          └──────────────────────────────┘
                         │
                         ▼
                  Response to User
```

</div>

## 🧠 How It Works

1. User sends a question
2. System loads conversation history from Redis
3. Relevant documents are retrieved from ChromaDB (RAG)
4. LangGraph orchestrates the flow:
   - memory → retrieval → reasoning → response
5. LLM generates a final contextual answer
6. Conversation is updated + summarized for future use

## 🗂️ Project Structure

```
chat-bot/
├── controllers/          # Route handler logic (chat, ingest endpoints)
├── middlewares/          # Rate limiting middleware
├── db/                   # Redis and ChromaDB clients
├── graph/
│   ├── builder.py        # LangGraph pipeline definition
│   └── nodes/            # Individual graph nodes (load_memory, retrieve_context, generate_answer, summarize, store_memory)
├── ingest/               # Incremental document ingestion pipeline
├── prompts/
│   ├── answer.py         # Answer generation prompt
│   └── summarize.py      # Conversation summarization prompt
├── schemas/
│   ├── chat.py           # ChatRequest schema
│   └── ingest.py         # IngestRequest schema
├── tests/                # Pytest test suite (ingest pipeline)
├── main.py               # App entrypoint
├── config.py             # Settings (pydantic-settings)
├── pytest.ini            # Test configuration
├── requirements.txt
├── requirements-dev.txt  # Test dependencies (pytest, fakeredis, responses, fpdf2)
└── docker-compose.yml
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
- Supports popular models: `BAAI/bge-small-en-v1.5`, `sentence-transformers/all-MiniLM-L6-v2`, etc.

**Alternative — HuggingFace (torch-based):**

```bash
pip install langchain-huggingface sentence-transformers transformers numpy
```

> ⚠️ `sentence-transformers` and `transformers` pull in `torch` which has known CVEs on older versions. Only install these if you explicitly need HuggingFace-specific models not available in FastEmbed.

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

Retrieval runs in two steps to prevent the LLM from hallucinating against weak or unrelated matches:

<div align="center">

```
User question
      │
      ▼
Step 1 — Relevance gate
similarity_search k=1  →  score < 0.3 ?
      │                         │
      │                         └──► docs = ""  →  "I don't have information
      │                                             about that in our knowledge
      │                                             base. Please contact support."
      │ score ≥ 0.3
      │ (question is on-topic)
      ▼
Step 2 — MMR retrieval
max_marginal_relevance_search k=3, fetch_k=10
      │
      ▼
3 diverse, relevant chunks → LLM → grounded answer
```

</div>

**Step 1 — Score gate:** fetches the single closest chunk and checks its cosine similarity score. If even the best match is below `0.3` the question is off-topic and the LLM is never called with guesswork context.

**Step 2 — MMR:** only runs when step 1 passes. Fetches 10 candidates and picks the 3 that are both relevant AND diverse — avoiding 3 near-identical paragraphs being sent to the LLM.

**ChromaDB is configured with cosine distance** (`hnsw:space: cosine`) — the correct metric for text embeddings. Without this, scores are L2-based and can go negative, making the threshold meaningless.

> Threshold is configurable via `RETRIEVAL_SCORE_THRESHOLD` in `.env` (default `0.3`). Raise to `0.7` for stricter grounding, lower to `0.2` if too many valid questions are being rejected.

### 🔹 LLM Layer

Configurable via environment variables:
- Uses conversation summary (long-term memory)
- Uses recent messages (short-term memory)
- Uses retrieved context (RAG)
- Generates final response in the user's language (Arabic / English)

## 🧠 Key Features

* ✅ Conversational memory (short + long-term via Redis)
* ✅ RAG retrieval with cosine score gate (threshold 0.3) + MMR diversity ranking
* ✅ Hallucination prevention — off-topic questions blocked before LLM is called
* ✅ Citations — every answer includes which source documents were used
* ✅ Conversational follow-ups — context-aware replies when no document match exists
* ✅ Incremental ingestion — only re-embeds changed chunks, not the whole document
* ✅ Ingestion safeguards — duplicate submission protection, file size limits, failed status saved to Redis, status polling endpoint
* ✅ Global duplicate detection — same PDF under different names caught via content hash
* ✅ Rate limiting — 60 requests/minute per IP (Redis-backed, returns 429 on breach)
* ✅ Multi-LLM provider support (OpenAI, Anthropic, Groq)
* ✅ Multilingual responses (Arabic / English auto-detected)
* ✅ LangGraph workflow orchestration
* ✅ Strict knowledge-base-only responses — refuses to answer outside ingested documents
* ✅ FastAPI production API layer
* ✅ Dockerized with Docker Compose (Redis with AOF persistence via named volume)
* ✅ Structured logging to console + rotating file (logs/app.log, 10 MB cap)

## 🧩 TODO (Roadmap)

* [ ] Guardrails
* [ ] Evaluation (RAGAS)

## ⚡ Tech Stack

* **Backend:** FastAPI
* **LLM:** OpenAI / Anthropic / Groq
* **Orchestration:** LangGraph
* **Framework:** LangChain
* **Vector DB:** ChromaDB
* **Cache / Memory:** Redis
* **Runtime:** Python 3.10
* **Container:** Docker + Docker Compose

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
- Add support for a new LLM provider in `utils/llm_adapter.py`
- Add a new document loader (e.g. DOCX, TXT) in `ingest/`
- Improve test coverage in `tests/`
- Add Guardrails or RAGAS evaluation (see TODO)

**Project layout to get oriented:**
- `graph/nodes/` — each file is one step in the LangGraph pipeline
- `ingest/policies.py` — full ingestion pipeline (download → chunk → diff → embed)
- `graph/nodes/retrieve_context.py` — score gate + MMR retrieval logic
- `prompts/answer.py` — the LLM prompt (easiest place to start experimenting)

> Please open an issue before starting large changes so we can discuss approach first.

---

## 📌 Summary

This project demonstrates a **real-world production architecture for AI chatbots** combining:

> RAG + Memory + LLM + Backend Engineering
