# Web Client — UX Improvement Spec (v2)

**Status:** Proposal / RFC · **Audience:** whoever implements the web client next ·
**Scope:** `web/` only (backend touchpoints called out explicitly) · **Date:** 2026-05-31

> This is a **spec, not an implementation.** Items are prioritized for *this* product and
> labelled **[FE]** (frontend-only, no backend change) or **[FS]** (full-stack, needs
> backend work). Several ideas originate from an external "2026 best-practices" critique;
> they are treated here as **suggestions**, re-prioritized against what this app actually
> is. The current v1 client (streaming, RTL, a11y, citations) is a clean MVP — this builds
> on it, it does not replace it wholesale.

---

## 0. What this product is (and why priorities differ)

`chat-bot` is a **citations-grounded, multi-mode, bilingual RAG knowledge assistant**:

- **Grounded:** answers come from ingested documents (PDF/TXT/MD/DOCX/HTML); every answer
  ships structured citations (`label`, `doc_id`, `score`, `page`, `snippet`).
- **Multi-mode (per request):** `strict` (answer only from docs, else refuse), `open`
  (docs + general knowledge), `learning` (synthesize + self-ingest).
- **Bilingual:** auto EN/AR detection, or forced `lang`.
- **Honest about limits:** strict mode *refuses* when nothing matches; problem+json errors;
  rate-limit headers.

**Implication for UX priorities.** For a knowledge assistant, the differentiators are
**trust/verifiability** and **mode + language fluidity** — *not* "chat as app" generative
widgets. A user's core questions are *"can I trust this?"*, *"where did it come from?"*,
and *"can I get it in the mode/language I need?"* We therefore rank trust and
mode/language UX as P0, and explicitly **deprioritize Generative UI** (high effort, low
value for a policy-RAG bot) to an optional future track.

### The contract we build on (already shipped)

| Capability | Contract |
|---|---|
| Chat | `POST /api/v1/chat` → `{ answer, sources[], meta }` |
| Streaming | `POST /api/v1/chat/stream` SSE: `event: token` `{delta}` → `sources` `{sources}` → `done` `{meta}` → `error` |
| Citations | `sources[]`: `{label, doc_id, score (0–1), page, snippet}` |
| Meta | `{mode, lang, self_ingested, correlation_id, model}` |
| Controls (per request) | `mode`, `lang` (auto/en/ar), `top_k` (1–10), `score_threshold` (0–1) |
| Identity | `X-User-Id` header (validated `[A-Za-z0-9_.@-]{1,128}`) |
| Errors | RFC 9457 problem+json everywhere |
| Limits | `X-RateLimit-Limit/Remaining/Reset`, `Retry-After` on 429 |
| Health | `GET /health` (cached), `GET /ready` (live) |
| Ingest | async `202` + `GET /ingest/status/{id}`, paginated `GET /ingest/docs` |

---

## 1. Design principles

1. **Grounded by default** — every claim is one click from its source.
2. **Mode & language are first-class and switchable mid-conversation** (we support
   per-request `mode`/`lang` — exploit it).
3. **A refusal is a feature, not a dead end** — offer the user a next step.
4. **Calm streaming** — no layout thrash, no half-rendered markdown, no scroll hijacking.
5. **Bilingual to the core** — correct direction *and* correct screen-reader pronunciation.
6. **Spend the design budget deliberately** — one type scale, one accent, two surfaces;
   add a component/token only when it earns its place.

---

## 2. P0 — Trust & verifiability  *(all [FE]; uses data we already return)*

This is the heart of a RAG assistant and our biggest UX leverage.

- **Confidence badge per answer [FE].** Map `meta`/source `score` to **High ≥ 0.7 /
  Medium 0.4–0.7 / Low < 0.4** with a tooltip showing the raw score. Drives trust at a
  glance; we already return the numbers.
- **Citation cards [FE].** Replace the plain "Sources (n)" list with cards showing
  `label` · `page` · a score meter · expandable `snippet`. Expanded view highlights the
  snippet; "Copy citation" action. (Optional [FS]: add a source deep-link/anchor — needs
  the backend to return a URL/page anchor.)
- **Strict-mode refusal as a first-class state [FE].** When `mode=strict`, `sources=[]`
  and the bot declines, render a distinct **"Not in the knowledge base"** card — not an
  error — with a primary CTA **"Answer from general knowledge"** that re-sends the *same*
  question with `mode=open`. This is the single most product-specific win: it turns a dead
  end into a guided path using the per-request `mode` override we already support.
- **Mode & provenance chips [FE].** Show the answering `meta.mode` on each assistant
  message. In `learning` mode, when `meta.self_ingested` is true, badge the answer
  **"AI-synthesized — not from official docs"** (and "saved to knowledge base"). Never let
  synthesized content look authoritative.
- **Per-message language correctness [FE].** Set both `dir` (rtl/ltr) **and** `lang`
  (`ar`/`en`) on each bubble so screen readers pronounce Arabic correctly and layout
  mirrors via logical CSS properties.

---

## 3. P0 — Streaming UX  *(all [FE])*

- **Markdown buffering [FE].** Do not render an incomplete fenced code block / table while
  tokens stream — buffer until the closing ``` ``` ``` (or row) arrives, to avoid flicker.
  Use `react-markdown` + `remark-gfm`; render code with **shiki** + a copy button.
- **Calm autoscroll [FE].** Auto-scroll only if the user is pinned to the bottom; if they
  scrolled up to read history, **do not** yank them — show a "↓ New" affordance instead.
- **Stop / Regenerate / Edit-resend [FE].** Show **Stop** only while streaming (abort the
  fetch). Add **Regenerate** on the last assistant message. Allow **edit a previous user
  message and resend** as a *client-side* re-ask (lightweight; true server-side branching
  is [FS] — see §8).
- **Streaming affordances [FE].** Typing/skeleton indicator before first token; steady
  token flush; graceful handling of the `error` SSE frame (render an inline error state,
  never a blank bubble).

---

## 4. P1 — Input & guidance  *(all [FE])*

- **Suggested-prompt chips, mode/lang-aware [FE].** On empty state and after each turn,
  offer 3–4 chips. Tie them to our controls: "Summarize this", **"اشرح بالعربية"** (sends
  `lang=ar`), "Answer from general knowledge" (sends `mode=open`). Beats an empty box.
- **Character counter [FE].** `q` is validated to ≤ 2000 chars server-side — surface a live
  counter and disable send past the limit (avoid a round-trip 422).
- **Persisted controls [FE].** Remember the user's `mode`/`lang` choice for the session;
  show them compactly near the composer.

---

## 5. P1 — Errors, limits & connectivity  *(all [FE]; consumes our headers/problem+json)*

- **Friendly problem+json [FE].** Map `{title, detail, status}` to inline, human messages.
  Surface `correlation_id` behind a small "Report issue" affordance so support is traceable.
- **Rate-limit countdown [FE].** On `429`, read `Retry-After` and show a disabled-send
  countdown; reflect `X-RateLimit-Remaining` subtly when low.
- **Connectivity badge [FE].** Poll `/health` (and `/ready` on demand); show a calm
  "degraded" indicator when Redis/Chroma are down rather than failing silently.

---

## 6. P1 — Accessibility refinements  *(all [FE])*

- **Defer screen-reader announcements [FE].** `aria-live="polite"` over a token stream
  makes SRs stutter. Announce the assistant message **once when the stream completes** (or
  in chunked, throttled updates for very long answers) rather than per token.
- **Reduced-motion = no flashing [FE].** Under `prefers-reduced-motion`, disable the cursor
  blink and token fade (a blinking cursor is flashing content).
- **Focus & keyboard [FE].** Don't steal focus/scroll while the user reads history; `Esc`
  to stop, `Enter`/`⌘+Enter` to send, arrow-navigation through citations; visible focus.
- **Bilingual SR [FE].** The per-message `lang` attribute (see §2) is the a11y fix that
  matters most here — Arabic read with an English voice is unusable.

---

## 7. P1 — Performance  *(all [FE])*

- **Virtualized history [FE].** Use `react-virtuoso` (or TanStack Virtual) so long
  conversations stay smooth; keep streaming append correct under virtualization.
- **Lazy highlight & code-split [FE].** Load shiki/highlighter lazily; the first paint
  shouldn't pay for syntax highlighting that isn't on screen.

---

## 8. P2 — Conversation management

- **New conversation [FE].** Rotate the `X-User-Id` to start fresh; expose it.
- **Memory transparency [FE].** Show that history is summarized and **expires (~24h TTL)**;
  offer "export transcript".
- **Edit & fork (branching) [FS].** True branching history requires a **non-linear
  conversation store** on the backend — today memory is a single linear per-user Redis blob
  with summarization. Ship the client-side edit-and-resend (§3) now; treat real branching as
  a backend redesign, not a client feature.

---

## 9. Optional / future (full-stack) — deliberately deprioritized

Honest assessment for *this* product; none are needed for P0/P1.

- **Feedback persistence (👍/👎 + reasons) [FS].** Valuable, but cosmetic unless stored.
  Needs a backend `POST /api/v1/feedback` endpoint + store. Recommend: add the endpoint,
  then wire inline message feedback. Until then, omit rather than fake it.
- **Generative UI (backend-emitted components) [FS].** Rendering forms/charts requires the
  graph to do **tool-calling** and emit a UI-component schema. For a policy-RAG bot this is
  **low value vs. effort** — our users want trustworthy citations, not embedded widgets.
  Park it behind a future tool-calling capability; the client can grow a renderer later.
- **Vercel AI SDK `useChat` [FS/FE].** `useChat` expects the **AI SDK Data Stream Protocol**,
  not our `event: token/sources/done` SSE. Adopting it means either adding an
  AI-SDK-compatible stream on FastAPI (another contract) or a client-side transport adapter.
  **Recommendation: do not adopt now** — our SSE + a small typed `useChatStream` hook covers
  P0/P1 cleanly. Revisit only if/when we pursue tool-calling/Generative UI, where the SDK's
  tool plumbing pays for itself.
- **Branching memory store [FS].** See §8.

---

## 10. Recommended tech (adapted; mind the design budget)

| Concern | Recommendation | Note |
|---|---|---|
| Framework | **Keep** Vite + React + TS | No rewrite needed |
| Styling | Tailwind + **shadcn/ui** (optional) | Good a11y primitives + dark mode; if staying with plain CSS, keep the one-accent/two-surface budget |
| Streaming/state | **Keep our SSE** + a typed `useChatStream` hook; TanStack Query for ingest/health | Avoids the `useChat` protocol mismatch (§9) |
| Markdown | `react-markdown` + `remark-gfm` | GFM tables/lists |
| Code blocks | **shiki** (lazy) + copy button | |
| Virtualization | `react-virtuoso` | Long histories |

> Every new dependency draws on the design/perf budget — justify it. shadcn/ui and the
> AI SDK are *optional*; the spec's P0/P1 value does not depend on either.

---

## 11. Backend touchpoints (only if pursuing [FS] items)

- **Citation deep-links:** add a source URL / page anchor to `Source` so "open source" can
  jump into the document.
- **Feedback:** `POST /api/v1/feedback` (message id, rating, reason) + store.
- **Generative UI:** LangGraph tool nodes + a UI-component schema in the stream.
- **Branching:** non-linear conversation store (replaces the linear Redis memory blob).

None are required for the P0/P1 frontend work.

---

## 12. Phasing & acceptance criteria

**Phase P0 (trust + calm streaming) → P1 (input, errors, a11y, perf) → P2 (conversation mgmt) → optional [FS].**

Testable acceptance criteria (samples):
- Strict refusal renders the dedicated card and its "Answer from general knowledge" CTA
  re-sends with `mode=open`.
- Confidence badge bucket matches the score thresholds; raw score in tooltip.
- A fenced code block is never rendered until its closing fence arrives (no flicker).
- Autoscroll happens **only** when pinned to bottom; otherwise a "New" affordance shows.
- Screen reader announces an assistant turn **once at completion**, not per token; Arabic
  messages carry `lang="ar"`.
- `429` shows a `Retry-After` countdown and disables send.
- History of 500+ messages scrolls smoothly (virtualization).
- `prefers-reduced-motion` disables cursor blink and token fade.

---

## 13. Verification note

UX qualities like "no layout thrash," screen-reader cadence, and RTL polish **cannot be
asserted in CI** — they require manual/browser QA (and ideally an axe-core pass +
VoiceOver/NVDA spot-check). Treat the acceptance criteria above as a manual QA checklist,
not an automated gate.
