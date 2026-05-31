# chat-bot web client

Reference SPA for the chat-bot API (Vite + React + TypeScript). Demonstrates the v1
API: SSE token streaming, per-request mode/language, structured citations, RTL/Arabic,
and a backend health badge.

## Run

```bash
cd web
bun install        # or: npm install
bun run dev        # http://localhost:5173 (proxies /api and /health to :8000)
```

Start the API separately (`uvicorn main:app --port 8000`).

## Build / typecheck

```bash
bun run build      # tsc -b && vite build  → dist/
bun run typecheck
```

## What it shows

- **Streaming chat** — `POST /api/v1/chat/stream` parsed as Server-Sent Events
  (`token` → `sources` → `done`); Stop aborts the request mid-stream.
- **Controls** — per-request `mode` (strict/open/learning/learning_review) and `lang` (auto/en/ar/pt).
- **Upload doc** — pick a local file (PDF/TXT/MD/DOCX/HTML) and `POST /api/v1/ingest/upload`
  (multipart); the file goes straight from the browser, no hosting/URL required.
- **Citations** — collapsible Sources with label, page, relevance score, and snippet.
- **RTL** — Arabic messages render `dir="rtl"` via logical CSS properties.
- **A11y** — `aria-live` on the streaming answer, keyboard send (Enter) / Shift+Enter
  newline, visible focus rings, `prefers-reduced-motion`.
- **Health** — polls `/health` and shows a status dot.
- **Reviewer queue (operators)** — the header **Review** toggle (or the `#/review` hash
  route) opens an operator panel over the `learning_review` queue. It lists pending entries
  (`question`, `answer`, `best_score`, `created_at`) from `GET /api/v1/review/pending` with
  **Approve** (`POST /api/v1/review/{id}/approve` — embeds the answer into the knowledge
  base) and **Reject** (`POST /api/v1/review/{id}/reject` — discards it). Resolved entries
  are removed optimistically; `next_cursor` drives a **Load more** affordance.

### Operator API key

The review endpoints (and ingest/upload) are gated by `require_api_key` when the server
runs with `REQUIRE_AUTH_FOR_INGEST=true`. The Review panel has an **API key** field; the
value is stored in `localStorage` (`chatbot.apiKey`) and sent as the `X-API-Key` header on
review and upload requests. It is a privileged operator action — only meaningful when the
server requires auth, and the key never leaves the browser except as that header. This
panel is intended for operators/moderators.

Conversation memory is scoped by a stable per-browser `X-User-Id` (localStorage).

## Roadmap

This v1 client is a clean MVP. [`UX_SPEC.md`](UX_SPEC.md) is the proposal for a v2 — a
trust-first, mode/language-fluid experience adapted to this RAG knowledge assistant
(confidence badges, citation cards, strict-refusal → "answer in open mode", markdown
buffering + virtualization, deferred screen-reader announcements, and more). It marks each
item frontend-only vs full-stack and deliberately deprioritizes Generative UI for this
product.

## Notes
- Plain CSS (no UI framework) keeps the visual budget tight: one accent color, two
  surface shades, spacing over borders.
- Production hosting: serve `dist/` from any static host; point the API at it via CORS
  (`CORS_ORIGINS`) or reverse-proxy `/api` to the backend.
