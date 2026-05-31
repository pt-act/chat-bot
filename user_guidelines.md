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
| `mode` | `strict` \| `open` \| `learning` \| `learning_review` | server default | See modes below. |
| `lang` | `auto` \| `en` \| `ar` \| `pt` | `auto` | Force the reply language (`pt` = European Portuguese). Auto-detects Arabic / Portuguese / English. |
| `top_k` | int 1–10 | 3 | How many document chunks to consider. |
| `score_threshold` | float 0–1 | 0.3 | Minimum relevance for a chunk to be used. |

> **Follow-ups just work.** On a multi-turn chat the bot rewrites elliptical follow-ups
> ("and what about damaged items?") into a standalone search query before retrieving, so
> pronouns and shorthand resolve to the right documents. You don't do anything — keep a
> stable `X-User-Id` and ask naturally.

### Modes

| Mode | What it does |
|------|--------------|
| **strict** | Answers **only** from approved documents. If nothing relevant is found — or the drafted answer isn't actually supported by them — it says it doesn't have the information. Best for policy/regulated answers. |
| **open** | Prefers documents, but may use general knowledge and tells you when it does. |
| **learning** | Like open, but when no document matches it synthesizes an answer and saves it to a **separate** learning store for future questions (never mixed into authoritative answers). |
| **learning_review** | Like learning, but synthesized answers are **queued for a human to approve** before they're saved — unverified answers never enter the knowledge base on their own. |

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
           "grounded": "supported", "grounded_score": 0.86,
           "correlation_id": "b1f3…", "model": "gpt-4o-mini"}
}
```

**Reading the response**
- `answer` — the reply text.
- `sources` — the citations behind it. `score` is relevance (0–1); `page`/`snippet` help
  you verify. In strict mode with no match, `sources` is `[]` and the bot declines.
- `meta.grounded` — how well the answer is backed by the cited documents:
  `supported`, `partial`, or `unsupported` (with `grounded_score`, the fraction of the
  answer supported). This reflects whether the answer is *true to the sources*, not just
  whether similar text was found — use it to drive a confidence indicator. In **strict**
  mode an `unsupported` answer is automatically replaced by a refusal and its sources
  cleared. It's `null` when there were no documents to check against.
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

The `done` event's `meta` carries the same fields as the non-streaming response, including
`grounded`/`grounded_score`. Note that the groundedness check runs after the answer is
assembled, so in strict mode a refusal override applies to the stored answer and the `done`
meta — it can't retract tokens already streamed to your screen.

(The reference web client in `web/` does exactly this, including a **Stop** button that
aborts mid-stream, and an operator **Review** panel for the `learning_review` queue.)

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

Ingestion is asynchronous on v1: you get `202 Accepted` with a `Location` header, then poll
the status endpoint. Supported formats: **PDF, TXT, Markdown (`.md`/`.markdown`), DOCX, and
HTML (`.html`/`.htm`)** — the format is inferred from the file/URL extension.

```bash
# (a) Ingest from a URL (returns 202 + Location header)
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"file_name":"returns","s3_url":"https://example.com/returns.pdf"}'

# (b) Upload a local file directly — no public URL needed (privacy-friendly)
curl -X POST http://127.0.0.1:8000/api/v1/ingest/upload \
  -F "file=@/path/to/returns.docx"            # or .pdf/.txt/.md/.html
  # optional explicit id: -F "file_name=returns"

# Poll status
curl http://127.0.0.1:8000/api/v1/ingest/status/returns

# List (paginated)
curl "http://127.0.0.1:8000/api/v1/ingest/docs?limit=50&cursor=0"

# Delete (needs X-API-Key)
curl -X DELETE http://127.0.0.1:8000/api/v1/ingest/returns -H "X-API-Key: <key>"
```

Rules: `file_name` must be non-empty, ≤128 chars, **no dots or slashes**; a URL must be a
public `https` link ending in a supported extension. Uploads are validated by extension
(PDFs also get a file-header check) and capped at the server's `MAX_FILE_SIZE_MB`. The
server re-ingests only when content changes and skips duplicates (the same file under a
different name is caught by content hash).

> **Status values:** `queued` → `done` (or `skipped` for unchanged/duplicate content, or
> `failed`). Where the operator has enabled durable ingestion, a queued job keeps
> processing — and retries transient download failures — even across a server restart.
> Management endpoints require `X-API-Key` when the operator sets `REQUIRE_AUTH_FOR_INGEST=true`
> (`DELETE` always does).

---

## 8. Rating answers (feedback)

Help improve the bot by rating an answer. Submission is open (no key needed); include the
`correlation_id` from the answer you're rating so operators can trace it.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{"rating":"down","reason":"cited the wrong policy","correlation_id":"b1f3…",
       "question":"return window?","answer":"…"}'
# → 201 {"feedback_id":"a1b2c3d4e5f6","rating":"down","status":"recorded"}
```

`rating` is `up` or `down`; `reason`, `question`, and `answer` are optional. Downvotes feed
the operator's review queue and the evaluation set, so flagging a bad answer genuinely helps.
(Listing feedback is an operator action and requires `X-API-Key`.)

---

## 9. Tips

- **Quote sources** in your UI using the `sources[]` objects — they make answers
  verifiable; pair them with `meta.grounded` for an honest confidence indicator.
- **Pick the right mode**: `strict` for compliance, `open` for general help, `learning`
  to grow the knowledge base, `learning_review` to grow it with a human approving first.
- **Languages**: replies come in Arabic, English, or European Portuguese. Auto-detection
  handles mixed input; set `lang` (`en`/`ar`/`pt`) explicitly when you want certainty.
- **Keep a stable `X-User-Id`** so multi-turn follow-ups resolve correctly (the bot
  condenses them into standalone queries behind the scenes).
- **Use streaming** for chat UIs; the non-streaming endpoint for simple integrations.
- **Rate bad answers** via `/api/v1/feedback` (with the `correlation_id`) — it feeds the
  review queue and the evaluation set.
- **Always send a correlation-friendly client**: log `X-Correlation-Id` from responses.
