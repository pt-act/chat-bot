
# 🤖 AI Chatbot Backend Service (LangChain + LangGraph + RAG + FastAPI)

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![LangChain](https://img.shields.io/badge/LangChain-LLM%20Orchestration-orange)
![ChromaDB](https://img.shields.io/badge/VectorDB-Chroma-purple)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20%7C%20Anthropic%20%7C%20Groq-black)

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

```
User Query
   ↓
FastAPI (/api/chat)
   ↓
LangGraph Orchestrator
   ├── Load Memory (Redis)
   ├── Retrieve Context (ChromaDB)
   ├── Generate Answer (LLM)
   ├── Summarize Conversation
   └── Store Memory (Redis)
   ↓
Response to User
```

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

## 🧩 1. Install Miniconda

```bash
Visit:- https://www.anaconda.com/docs/getting-started/miniconda/install/mac-cli-install
bash ~/Downloads/Miniconda3-*.sh
source ~/miniconda3/bin/activate
```

## 🐍 2. Create Environment

```bash
conda create -n chat-bot python=3.10
conda activate chat-bot
```

## 📦 3. Clone and Install Dependencies

```bash
git clone https://github.com/hasandeveloper/chat-bot.git
cd chat-bot
pip install -r requirements.txt
```

## ⚠️ 4. Configure Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Key variables:

```env
👉 Get your key from: https://platform.openai.com/account/api-keys
OPENAI_API_KEY=your_openai_key_here

LLM_PROVIDER=openai          # openai | anthropic | groq
LLM_MODEL=gpt-4o-mini

REDIS_HOST=localhost
REDIS_PORT=6379
```

See [.env.example](.env.example) for the full list of options.

> **LangSmith (optional):** Tracing is disabled by default (`LANGSMITH_TRACING=false`). To enable it, set `LANGSMITH_TRACING=true` and provide a valid `LANGSMITH_API_KEY` from [smith.langchain.com](https://smith.langchain.com).

## 🚀 5. Run Server

```bash
uvicorn main:app --reload
```

📍 Server:

```
http://127.0.0.1:8000
```

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

## 🏥 8. Health Check

```bash
curl http://127.0.0.1:8000/health
```

## 🧠 Core System Design

### 🔹 Memory System
Redis stores:
- Full conversation history
- Running conversation summary (for long-term context)
- TTL-based expiry (configurable via `REDIS_TTL_SECONDS`)

### 🔹 RAG System — Incremental Ingestion + MMR Retrieval

#### Ingestion Flow

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

**Redis keys used by the ingest pipeline:**

| Key | Type | Purpose |
|-----|------|---------|
| `ingest_status:{doc_id}` | Hash | Status, file hash, version, chunk counts per document |
| `doc_chunks:{doc_id}` | Set | MD5 hash of every chunk in the current version |
| `ingest:doc_ids` | Set | Global list of all ingested doc IDs |
| `ingest:content_hashes` | Hash | Maps `file_hash → doc_id` — catches same PDF under a different filename |

#### Retrieval — MMR (Maximal Marginal Relevance)

Instead of returning the top-3 most similar chunks (which can be near-identical), MMR fetches the top-10 candidates then selects 3 that are both **relevant AND diverse** from each other — so the LLM sees a broader slice of the document.

```
ChromaDB.max_marginal_relevance_search(question, k=3, fetch_k=10)
```

### 🔹 LLM Layer
Configurable via environment variables:
- Uses conversation summary (long-term memory)
- Uses recent messages (short-term memory)
- Uses retrieved context (RAG)
- Generates final response in the user's language (Arabic / English)

## 🧠 Key Features

* ✅ Conversational memory (short + long-term via Redis)
* ✅ RAG retrieval with MMR diversity ranking (fetch 10, return 3 diverse chunks)
* ✅ Incremental ingestion — only re-embeds changed chunks, not the whole document
* ✅ Global duplicate detection — same PDF under different names is caught via content hash
* ✅ Rate limiting — 60 requests/minute per IP (Redis-backed, returns 429 on breach)
* ✅ Multi-LLM provider support (OpenAI, Anthropic, Groq)
* ✅ Multilingual responses (Arabic / English auto-detected)
* ✅ LangGraph workflow orchestration
* ✅ Strict knowledge-base-only responses — refuses to answer outside ingested documents
* ✅ FastAPI production API layer
* ✅ Dockerized with Docker Compose (Redis with AOF persistence via named volume)
* ✅ Structured logging + CORS + input validation

## 🧩 TODO (Roadmap)
* [ ] LLM: Handling tokenization differences, latency variations & fallback mechanisms
* [ ] Embeddings/Search: Hybrid Search (semantic + keyword BM25) + Query Rewriting Node + Token optimization / Cost Tracking
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

## 📌 Summary

This project demonstrates a **real-world production architecture for AI chatbots** combining:

> RAG + Memory + LLM + Backend Engineering
