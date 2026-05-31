# UI/UX Improvement Spec — `pt-act/chat-bot`

**Status:** Draft for review · **Author:** Poncho · **Date:** 2026-05-30
**Target:** branch `audit/graph-integration-test` @ `68239cd` (post-remediation)

---

## 0. Reality check (read this first)

`chat-bot` is a **headless FastAPI service**. There is **no frontend, no templates, no
static assets** in the repo — the only human/consumer-facing surface is the **HTTP API**
(plus the auto-generated `/docs` Swagger page). So "UI/UX" splits into two workstreams:

- **Workstream A — API & Developer Experience (DX).** The API *is* the UI for every
  integrator. This is where the highest-leverage, lowest-cost wins are, and several
  concrete rough edges exist today (verified in code, see §2).
- **Workstream B — Reference Chat Web Client.** A thin, optional first-party UI so the
  product is usable/demoable by humans (streaming chat, mode selector, citations, ingest
  admin). Greenfield.

This document is a **high-level spec**: goals, current-state findings, proposed contracts,
tech choices, prioritization, milestones, and acceptance criteria. It is intentionally
implementation-light; each P0 item is small enough to land as its own PR.

---

## 1. Goals & non-goals

**Goals**
- G1. Make the API predictable and self-describing (consistent envelopes, one error model,
  rich OpenAPI) so a new integrator can build against it in <30 min.
- G2. Make chat feel responsive (token streaming) and controllable (per-request mode,
  language, retrieval params).
- G3. Make answers trustworthy and inspectable (structured citations with score/snippet/
  page; expose `self_ingested`, correlation id, token usage).
- G4. Provide a minimal, accessible reference web client (incl. **RTL/Arabic** support,
  which the backend already special-cases).
- G5. Surface operational state to clients (rate-limit headers, `Retry-After`, health).

**Non-goals (this phase)**
- Multi-tenant admin console, analytics dashboards, auth/SSO product (tracked separately).
- Replacing LangGraph or the storage layer.

---

## 2. Current-state findings (verified in code)

| # | Area | Finding (file) | UX impact |
|---|------|----------------|-----------|
| F1 | Response shape | `POST /api/chat` returns `{"status":"success","data":<answer>,"sources":[...]}` (`controllers/chat_controller.py:20`). `data` is an opaque name for "the answer". | Ambiguous contract; clients guess field meaning. |
| F2 | Inconsistent errors | Three different error shapes: validation → `{"error":"Validation failed","details":[...]}`, `ValueError` → `{"error":"Bad request","detail":...}` (`main.py:84,90`), and `HTTPException` → FastAPI default `{"detail":...}`. | Clients must handle 3 schemas; brittle. |
| F3 | No streaming | Chat uses synchronous `graph.invoke(...)` (`services/chat_service.py:11`); no SSE/WebSocket. | User stares at a spinner for the whole LLM completion. |
| F4 | Mode not per-request | `chat_mode` is read from **global settings** (`services/chat_service.py:10`); `ChatRequest` only has `q` (`schemas/chat.py`). | A client cannot choose strict/open/learning per call. |
| F5 | Thin citations | `sources` is a deduped list of labels only (`graph/nodes/retrieve_context.py`). No score, snippet, page, or doc id. | Can't render "why this answer" or link to source. |
| F6 | Hidden signals | `self_ingested` is computed (`services/chat_service.py:22`) but **not returned** by the controller; `X-Correlation-Id` is a header only; no token usage. | Clients can't show learning state, trace, or cost. |
| F7 | OpenAPI quality | Routers declare no `response_model`, `tags`, `summary`, or examples. | `/docs` is generic; weak SDK generation. |
| F8 | Rate-limit opacity | 429 body has no `Retry-After` / `X-RateLimit-*` headers (`middlewares/rate_limiter.py:98`). | Clients can't back off intelligently. |
| F9 | Ingest blocks | `process_policy` downloads + parses synchronously inside the request (`ingest/policies.py`); a status endpoint exists but ingest itself is blocking. | Large PDFs → long request, timeouts. |
| F10 | No list pagination | `GET /api/ingest/docs` returns all docs at once (`controllers/ingest_controller.py:41`). | Doesn't scale; heavy responses. |
| F11 | No human UI | No frontend at all. | Not demoable to non-developers. |

---

## 3. Workstream A — API & Developer Experience

### A1 (P0). One response envelope + one error model
Adopt a single success envelope and **RFC 9457 (problem+json)** for all errors.

**Success (chat):**
```jsonc
// 200 POST /api/v1/chat
{
  "answer": "Returns are accepted within 30 days...",
  "sources": [
    { "doc_id": "return_policy", "label": "return_policy.pdf",
      "score": 0.82, "page": 3, "snippet": "Customers may return..." }
  ],
  "meta": { "mode": "strict", "self_ingested": false,
            "correlation_id": "f3c1...", "model": "gpt-4o-mini",
            "usage": { "prompt_tokens": 812, "completion_tokens": 96 } }
}
```
**Error (everything):**
```jsonc
// 4xx/5xx — application/problem+json
{ "type": "https://errors.chat-bot/validation",
  "title": "Validation failed", "status": 422,
  "detail": "Question cannot be empty",
  "correlation_id": "f3c1...",
  "errors": [ { "field": "q", "message": "Question cannot be empty" } ] }
```
*Implementation:* register one exception handler that emits problem+json for
`RequestValidationError`, `HTTPException`, and unhandled errors; include `correlation_id`
(already in `contextvars`, `middlewares/observability.py`). Fixes **F1, F2, F6**.

### A2 (P0). Per-request controls in `ChatRequest`
Extend the schema (keep `q`), all optional with safe server defaults:
```python
class ChatRequest(BaseModel):
    q: str
    mode: Literal["strict", "open", "learning"] | None = None  # overrides global default
    lang: Literal["auto", "en", "ar"] = "auto"                  # overrides auto-detect
    top_k: int | None = Field(default=None, ge=1, le=10)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
```
Thread `mode` through `conversation(user_id, q, mode=...)` instead of reading global
settings. Validate against the same allowed set as `config.check_chat_mode`. Fixes **F4**
(and exposes the language override the backend already computes).

### A3 (P0). Streaming responses (SSE)
Add `POST /api/v1/chat/stream` returning `text/event-stream`, driven by LangGraph/LangChain
`astream`/`astream_events`. Event contract:
```
event: token   data: {"delta": "Ret"}
event: token   data: {"delta": "urns"}
event: sources data: {"sources": [ ... ]}
event: done    data: {"meta": { "self_ingested": false, "correlation_id": "..." }}
event: error   data: {problem+json}
```
Keep the non-streaming endpoint for simple clients. Fixes **F3** (largest perceived-latency
win). Make the LLM adapter `streaming=True`-capable; ensure middleware doesn't buffer SSE.

### A4 (P1). Rich citations
Return the structured `sources[]` from A1 (doc_id, label, score, page, snippet). Source
data already exists in chunk metadata (`source_file`, `page_number`, `chunk_index`) and
relevance scores are available from `similarity_search_with_relevance_scores`; thread them
out of `retrieve_context` instead of collapsing to labels. Fixes **F5**.

### A5 (P1). Operational headers
- 429 → `Retry-After: <seconds>` + `X-RateLimit-Limit/Remaining/Reset` (compute from the
  Redis window in `rate_limiter.py`). Fixes **F8**.
- Echo `X-Correlation-Id` (already done) and document it.

### A6 (P1). OpenAPI quality + versioning
- Add `response_model`, `tags`, `summary`, `description`, and `examples` to every route;
  set `app = FastAPI(..., description=..., contact=..., license_info=...)`.
- Introduce a versioned prefix `/api/v1` (alias current `/api` for one deprecation cycle).
- Result: a usable `/docs`, accurate `/redoc`, and clean client-SDK codegen. Fixes **F7**.

### A7 (P2). Async ingest + pagination
- Make `POST /api/v1/ingest` enqueue a job (return `202 Accepted` + `doc_id` + status URL);
  do the download/parse in a background worker (the roadmap already mentions Celery). The
  existing `GET /ingest/status/{doc_id}` becomes the poll endpoint. Fixes **F9**.
- Add `?limit=&cursor=` pagination to `GET /ingest/docs`. Fixes **F10**.

---

## 4. Workstream B — Reference Chat Web Client

A small, self-contained SPA served separately (not coupled to the API process).

**Tech (proposed, low-budget):** Vite + React + TypeScript + Tailwind; `fetch` +
`EventSource`/`@microsoft/fetch-event-source` for SSE; TanStack Query for ingest/admin
calls. Single design system, minimal component set (see Design Budget below).

**Screens / components**
- **Chat view:** streaming message list (user/assistant bubbles), composer with
  send/stop, **mode selector** (strict/open/learning), language indicator. Auto-scroll,
  copy-message, regenerate.
- **Citations:** collapsible "Sources (n)" under each answer; each item shows label, page,
  score badge, and snippet on expand. "No sources" state for refusals.
- **Empty/zero states:** first-run prompt suggestions; strict-mode "I don't have info"
  rendered distinctly (not as an error).
- **Ingest admin (optional, gated):** upload/submit PDF URL, live status (poll
  `/ingest/status`), docs table with delete (uses `X-API-Key`).
- **Connection/health badge:** poll `/health`; show degraded state.

**Cross-cutting UX requirements**
- **RTL & i18n:** the backend already routes Arabic vs English (`generate_answer.py`,
  `summarize.py`). The UI **must** support `dir="rtl"` and mirror layout when the answer/UI
  language is Arabic; use logical CSS properties (`margin-inline-start`, etc.).
- **Accessibility:** WCAG 2.2 AA — keyboard-navigable composer, `aria-live="polite"` on the
  streaming answer region, visible focus, ≥4.5:1 contrast, `prefers-reduced-motion`.
- **Resilience:** render `token` deltas incrementally; handle `error` events and
  reconnect; show `Retry-After` countdown on 429; never block the composer on a failed
  request.
- **Correlation:** display `correlation_id` in a details/debug affordance to make support
  tickets traceable.

**Design budget (per repo guidance):** one type scale, one accent color, two surface
shades, spacing-over-borders. Differentiate hierarchy with weight/size *or* color, not
both. No component or token without a job.

---

## 5. Prioritization & milestones

| Priority | Items | Outcome |
|---|---|---|
| **P0 — API contract (≈1 wk)** | A1 envelope+problem+json, A2 per-request mode/lang, A3 SSE streaming | Predictable, controllable, responsive API |
| **P1 — Trust & ergonomics (≈1 wk)** | A4 rich citations, A5 rate-limit headers, A6 OpenAPI+`/v1` | Inspectable answers, great `/docs`, SDK-ready |
| **P2 — Scale & human UI (2–3 wk)** | A7 async ingest+pagination, **Workstream B** reference client | Demoable product, scalable ingest |

**Milestone exit criteria**
- M1 (P0): every endpoint returns the unified envelope; one error schema validated by
  contract tests; `/chat/stream` streams tokens end-to-end; `mode`/`lang` honored per
  request.
- M2 (P1): `/docs` shows typed models + examples; `sources[]` carries score/page/snippet;
  429 includes `Retry-After`; `/api/v1` live with `/api` alias.
- M3 (P2): ingest returns `202` + pollable status; docs list paginated; web client can hold
  a streaming, cited, multi-mode conversation in both LTR and RTL.

---

## 6. Acceptance criteria (testable)

- **Contract:** OpenAPI schema validates; a generated TypeScript client compiles and round-
  trips chat + ingest. Snapshot tests pin the success + problem+json shapes.
- **Streaming:** an SSE client receives ≥2 `token` events before `done`; first token < 1s
  after model start (mockable in tests via the existing `ChatOpenAI`-level seam used in
  `tests/test_graph_integration.py`).
- **Mode/lang:** `mode=open` vs `strict` produce the documented behaviors per request
  without changing server config; `lang=ar` forces Arabic output.
- **Citations:** every non-refusal answer returns ≥1 source with non-null
  `score`/`label`; refusals return `sources: []`.
- **Rate limit:** exceeding the window returns 429 with a numeric `Retry-After`.
- **A11y (UI):** axe-core: 0 critical violations; full keyboard path for send/stop/expand-
  sources; RTL snapshot for an Arabic conversation.

---

## 7. Risks & mitigations

- **SSE through middleware/proxies:** ensure `RequestTimingMiddleware`/CORS don't buffer
  the stream; disable response buffering for the stream route; document proxy config.
- **Streaming + summary/self-ingest ordering:** the graph runs summarize/store/self-ingest
  *after* answer generation — stream the answer first, then emit `sources`/`done` once
  post-steps finish; persist memory regardless of client disconnect.
- **Backwards compatibility:** keep `/api` (legacy envelope) for one deprecation cycle
  behind a feature flag; announce in `CHANGELOG.md`.
- **Scope creep on the UI:** ship the chat view first; ingest admin is independently
  optional and auth-gated.

---

## 8. Out of scope / follow-ups
- Authn/Z product for `/chat` (separate security workstream — see audit M-4 follow-up).
- Persistent conversation history UI beyond the current Redis TTL window.
- Analytics/observability dashboards.
