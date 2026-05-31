# User Guidelines

A practical guide for **using** the chatbot — through the HTTP API or the reference web
client. For internals and operations, see [`PTD.md`](PTD.md).

- Base URL (local): `http://127.0.0.1:8000`
- Versioned API: **`/api/v1`** (recommended). The unversioned `/api/*` is deprecated.
- Errors: `application/problem+json` (RFC 9457).

---

## 1. Identity & authentication

| Header | Purpose | Required? |
|--------|---------|-----------|
| `X-User-Id` | Scopes your conversation memory. Allowed: `[A-Za-z0-9_.@-]`, ≤128 chars. | Optional (defaults to `anonymous`) |
| `X-API-Key` | Protects ingest management. | `DELETE` always; others when `REQUIRE_AUTH_FOR_INGEST=true` |

Use a **stable** `X-User-Id` per user so the bot remembers the conversation (memory has a
TTL, default 24h). Different ids are fully isolated.

> Chatting (`/chat`) is not authenticated by default. Don't send personal data unless the
> operator has put authentication in front of the service.

---

## 2. Chatting

### Endpoint
`POST /api/v1/chat`

### Body
Only `q` is required; everything else is an optional per-request override.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `q` | string | — | Your question (1–2000 chars). |
| `mode` | `strict` \| `open` \| `learning` | server default | See modes below. |
| `lang` | `auto` \| `en` \| `ar` | `auto` | Force the reply language. Auto detects Arabic vs English. |
| `top_k` | int 1–10 | 3 | How many document chunks to consider. |
| `score_threshold` | float 0–1 | 0.3 | Minimum relevance for a chunk to be used. |

### Modes

| Mode | What it does |
|------|--------------|
| **strict** | Answers **only** from approved documents. If nothing relevant is found, it says it doesn't have the information. Best for policy/regulated answers. |
| **open** | Prefers documents, but may use general knowledge and tells you when it does. |
| **learning** | Like open, but when no document matches it synthesizes an answer and saves it to a **separate** learning store for future questions (never mixed into authoritative answers). |

### Example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" -H "X-User-Id: alice" \
  -d '{"q":"How long do I have to return an item?","mode":"strict","top_k":4}'
```

```json
{
  "answer": "You can return any item within 30 days of purchase.",
  "sources": [
    {"label": "return_policy.pdf", "doc_id": "return_policy", "score": 0.86, "page": 1,
     "snippet": "Customers may return any item within 30 days..."}
  ],
  "meta": {"mode": "strict", "lang": "en", "self_ingested": false,
           "correlation_id": "b1f3…", "model": "gpt-4o-mini"}
}
```

**Reading the response**
- `answer` — the reply text.
- `sources` — the citations behind it. `score` is relevance (0–1); `page`/`snippet` help
  you verify. In strict mode with no match, `sources` is `[]` and the bot declines.
- `meta.self_ingested` — `true` only in learning mode when the answer was saved.
- `meta.correlation_id` — quote this in support requests (also returned as the
  `X-Correlation-Id` header).

---

## 3. Streaming (typing effect)

`POST /api/v1/chat/stream` returns **Server-Sent Events** so you can render tokens as they
arrive. Same request body.

Event order: `token` (repeated) → `sources` → `done`. On failure: `error`.

```
event: token    data: {"delta": "You can "}
event: token    data: {"delta": "return..."}
event: sources  data: {"sources": [ … ]}
event: done     data: {"meta": { … }}
```

Browser example (POST → can't use `EventSource`, so read the stream):

```js
const res = await fetch("/api/v1/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-User-Id": "alice" },
  body: JSON.stringify({ q: "What is the return policy?" }),
});
const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += dec.decode(value, { stream: true });
  // split on blank lines → SSE frames; parse "event:" and "data:" lines
}
```

(The reference web client in `web/` does exactly this, including a **Stop** button that
aborts mid-stream.)

---

## 4. Errors (problem+json)

All errors share one shape:

```json
{ "type": "https://errors.chat-bot/validation", "title": "Validation failed",
  "status": 422, "detail": "Question cannot be empty",
  "correlation_id": "…", "errors": [{"field": "q", "message": "..."}] }
```

| Status | Meaning | What to do |
|--------|---------|------------|
| 400 | Bad request (e.g. invalid `X-User-Id`) | Fix the input. |
| 401 | Missing/invalid `X-API-Key` (ingest) | Provide a valid key. |
| 404 | Unknown `doc_id` | Check the id. |
| 422 | Validation error | See `errors[]` for the offending field. |
| 429 | Rate limited | Back off (see below). |
| 500 | Server error | Retry later; quote `correlation_id`. 5xx bodies never include internal details. |

---

## 5. Rate limits

Every response includes:
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (epoch seconds).

On `429` you also get `Retry-After` (seconds). **Honor it** — wait that long before
retrying. Default limit is 60 requests/minute per client IP.

---

## 6. Conversation memory

- Stored per `X-User-Id`, with a TTL (default 24h) — old conversations expire.
- The bot summarizes long chats automatically to stay coherent.
- To "start fresh", use a new `X-User-Id`.

---

## 7. Managing documents (ingestion)

Ingestion is asynchronous on v1.

```bash
# Queue (returns 202 + Location header)
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"file_name":"returns","s3_url":"https://example.com/returns.pdf"}'

# Poll status
curl http://127.0.0.1:8000/api/v1/ingest/status/returns

# List (paginated)
curl "http://127.0.0.1:8000/api/v1/ingest/docs?limit=50&cursor=0"

# Delete (needs X-API-Key)
curl -X DELETE http://127.0.0.1:8000/api/v1/ingest/returns -H "X-API-Key: <key>"
```

Rules: `file_name` must be non-empty, ≤128 chars, **no dots or slashes**; `s3_url` must be
a public `https` URL ending in `.pdf`. The server re-ingests only when content changes and
skips duplicates.

---

## 8. Tips

- **Quote sources** in your UI using the `sources[]` objects — they make answers
  verifiable.
- **Pick the right mode**: `strict` for compliance, `open` for general help, `learning`
  to grow the knowledge base.
- **Mixed-language** questions reply in Arabic if any Arabic is present (or set
  `lang` explicitly).
- **Use streaming** for chat UIs; the non-streaming endpoint for simple integrations.
- **Always send a correlation-friendly client**: log `X-Correlation-Id` from responses.
