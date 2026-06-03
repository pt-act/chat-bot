# Web Client UX v2 — Specification

**Feature:** web-ux-v2
**Status:** Specification (Phase 2)
**Scope:** `web/` only — no backend changes required for P0/P1
**Consciousness Gate 1:** PASS (see planning/requirements.md §9)

---

## Goal

Upgrade the chat-bot web client from a functional MVP to a trust-first, calm-streaming RAG assistant that fully leverages the data the backend already returns. Users should be able to assess answer confidence at a glance, trace every claim to its source, recover gracefully from strict-mode refusals, and experience smooth streaming with proper markdown rendering — all without a single backend change.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ App.tsx (orchestrator)                                   │
│   ├── useChatStream hook (extracted from App.send())     │
│   ├── session state (mode, lang, userId, suggestions)    │
│   └── message state (messages[], busy, error)            │
├─────────────────────────────────────────────────────────┤
│ Header                                                   │
│   ├── Controls (compact, near composer in P1)           │
│   ├── UploadButton                                       │
│   ├── Review toggle                                      │
│   └── HealthBadge (+ /ready probe in P1)                │
├─────────────────────────────────────────────────────────┤
│ MessageList (virtualized in P1)                          │
│   ├── UserBubble                                         │
│   └── AssistantBubble                                    │
│       ├── MarkdownBody (react-markdown + remark-gfm)    │
│       ├── ConfidenceBadge (score → High/Med/Low)        │
│       ├── ModeChip + ProvenanceChip                     │
│       ├── RefusalCard (strict mode → CTA to re-send)    │
│       ├── CitationCards (score meter + snippet + copy)   │
│       └── ActionRow (Regenerate / Edit-resend)          │
├─────────────────────────────────────────────────────────┤
│ Composer                                                 │
│   ├── SuggestedPromptChips (P1)                          │
│   ├── Textarea + CharCounter (P1)                        │
│   └── Send / Stop button                                │
├─────────────────────────────────────────────────────────┤
│ NewMessageAffordance ("↓ New messages" when scrolled up) │
└─────────────────────────────────────────────────────────┘

Data flow (unchanged):
  Composer → useChatStream → POST /api/v1/chat/stream (SSE)
           → onToken/onSources/onDone/onError callbacks
           → message state updates
```

## User Stories

### US-1: Trust at a glance
As a **user asking a policy question**, I want to see a confidence level (High/Medium/Low) on each answer so that I know how much to trust it without reading the raw score.

### US-2: Trace every claim
As a **user verifying an answer**, I want citation cards showing the source document, page, a visual score meter, and an expandable snippet so that I can confirm the answer comes from an actual document.

### US-3: Refusal is a path, not a wall
As a **user in strict mode who gets a refusal**, I want a distinct "Not in the knowledge base" card with a one-click "Answer from general knowledge" action so that I can escalate to open mode without retyping.

### US-4: Know what mode produced this answer
As a **user switching between modes**, I want each assistant message to show its answering mode and whether the answer was AI-synthesized so that I never mistake a synthesized answer for an authoritative one.

### US-5: Calm streaming
As a **user reading a streaming answer**, I want complete markdown (no half-rendered code blocks), smooth auto-scroll when pinned to bottom, and no scroll hijacking when I'm reading history.

### US-6: Recover from errors gracefully
As a **user hitting a rate limit or server error**, I want a friendly inline message (not a blank bubble), a countdown on 429, and the correlation ID accessible for support.

### US-7: Multilingual correctness
As an **Arabic-speaking user**, I want each message bubble to carry `dir="rtl"` and `lang="ar"` so that screen readers pronounce it correctly and layout mirrors properly.

### US-8: Prompted, not stuck
As a **new user facing an empty chat**, I want suggested prompt chips (including one that sends `lang=ar`) so that I know what the bot can do without reading docs.

## Specific Requirements

### P0 — Trust & Verifiability

| ID | Requirement | Success criteria |
|----|-------------|------------------|
| P0-1 | Confidence badge on each assistant message | Score ≥ 0.7 → green "High"; 0.4–0.7 → amber "Medium"; < 0.4 → red "Low". Tooltip shows raw score. Uses `meta.grounded_score` when available, otherwise best `sources[].score`. |
| P0-2 | Citation cards replace plain source list | Each source shows: label, page, score meter (0–1 bar), expandable snippet, copy-citation button. "Sources (n)" toggle retained. |
| P0-3 | Strict-refusal card | When `mode=strict`, `sources=[]`, and answer matches refusal pattern → render a distinct "Not in the knowledge base" card with primary CTA "Answer from general knowledge" that re-sends same `q` with `mode=open`. |
| P0-4 | Mode chip on each assistant message | Show `meta.mode` as a chip/badge on the message. In `learning` mode when `meta.self_ingested=true`, badge as "AI-synthesized — not from official docs" with a "saved to knowledge base" note. |
| P0-5 | Per-message `lang` attribute | Set `lang` (`ar`/`en`/`pt`) on each bubble element using `meta.lang` from the done event, plus `dir` from `dirFor()`. SR pronunciation correct for Arabic. |

### P0 — Streaming UX

| ID | Requirement | Success criteria |
|----|-------------|------------------|
| P0-6 | Markdown rendering with fenced-code buffering | Render assistant content via `react-markdown` + `remark-gfm`. While streaming, buffer incomplete fenced code blocks (no ``` closer yet) — show a placeholder/skeleton until the fence closes. No flicker of half-rendered tables or code. |
| P0-7 | Code block syntax highlighting + copy | Use `shiki` (lazy-loaded) for syntax highlighting inside fenced code blocks. Add a "Copy" button per code block. Falls back to un-highlighted `<pre><code>` if shiki hasn't loaded. |
| P0-8 | Smart autoscroll | Auto-scroll to bottom only when user is pinned to the bottom (detection: scroll position near bottom threshold). If user scrolled up to read history, do NOT yank — show a "↓ New messages" button that jumps to bottom when clicked. |
| P0-9 | Stop / Regenerate / Edit-resend | **Stop**: shown only while streaming (abort fetch) — already exists. **Regenerate**: button on the last assistant message, re-sends the preceding user question. **Edit-resend**: pencil icon on user messages; clicking edits the text and re-sends as a new turn (client-side; no server branching). |
| P0-10 | Streaming affordances | Typing/skeleton indicator before first token. Steady token flush. On SSE `error` frame, render an inline error state in the bubble (not blank). |

### P1 — Input, Errors, A11y, Perf

| ID | Requirement | Success criteria |
|----|-------------|------------------|
| P1-1 | Suggested-prompt chips | On empty state and after each turn, show 3–4 chips. Chips are mode/lang-aware: "Summarize this", "اشرح بالعربية" (sends `lang=ar`), "Answer from general knowledge" (sends `mode=open`). |
| P1-2 | Character counter | Show live counter; disable send at 2000 chars (matches server validation). |
| P1-3 | Persisted controls | Session-storage for mode/lang; display compactly near composer. |
| P1-4 | Friendly problem+json | Map `{title, detail, status}` to inline human messages. Surface `correlation_id` behind a small "Report issue" affordance. |
| P1-5 | Rate-limit countdown | On 429, read `Retry-After` header, show countdown, disable send during cooldown. |
| P1-6 | Enhanced connectivity badge | Poll `/health` (existing); add on-demand `/ready` check; show "degraded" state clearly. |
| P1-7 | Deferred SR announcements | `aria-live="polite"` only on stream completion, not per token. Announce the full message once. |
| P1-8 | `prefers-reduced-motion` | Disable cursor blink and token fade under the media query. |
| P1-9 | Keyboard refinements | `Esc` to stop streaming; arrow-navigation through citation cards. |
| P1-10 | Virtualized history | `react-virtuoso` so 500+ messages scroll smoothly. `followOutput` for streaming append. |
| P1-11 | Lazy highlight & code-split | Load shiki via `React.lazy` + `Suspense`. No first-paint cost. |

### P2 — Conversation Management (deferred)

| ID | Requirement | Success criteria |
|----|-------------|------------------|
| P2-1 | New conversation | Rotate `X-User-Id` to start fresh. Expose in UI. |
| P2-2 | Memory transparency | Show TTL (~24h) note; offer "export transcript" (JSON/text download). |
| P2-3 | Edit & fork (true branching) | [FS] Requires backend non-linear memory store. Client-side edit-resend ships in P0. |

## Out of Scope

- **Tailwind / shadcn/ui migration** — spec marks these optional; staying with plain CSS
- **Vercel AI SDK `useChat`** — protocol mismatch with our SSE (§9 of UX spec)
- **Generative UI / tool-calling** — low value for a policy-RAG bot
- **Backend branching / non-linear memory** — server redesign needed
- **Inline 👍/👎 feedback** — backend has the endpoint; wiring is trivial but explicitly P2+ per spec
- **Citation deep-links** — [FS] needs backend to return URL/page anchors
- **Light/dark mode toggle** — not in the spec
- **Authentication on chat** — not in the spec; backend already validates `X-User-Id`

## Existing Code to Leverage

| Existing | Reuse strategy |
|----------|---------------|
| `lib/api.ts` — `streamChat()` | Extract into `useChatStream` hook; keep `streamChat` for non-hook consumers |
| `components/Sources.tsx` | Refactor into `CitationCards` component; keep toggle pattern |
| `components/MessageList.tsx` | Add virtualization wrapper; refactor bubble into `UserBubble`/`AssistantBubble` sub-components |
| `components/Composer.tsx` | Add char counter, suggested chips |
| `lib/rtl.ts` — `dirFor()` | Extend to return `lang` attribute too (or compute from `meta.lang`) |
| `styles.css` — design tokens | Add new tokens: `--confidence-high/med/low`, `--refusal-bg`, `--chip-bg`; keep existing palette |
| `types.ts` — `ChatMeta` | Add `grounded` and `grounded_score` fields |

## Acceptance Criteria (testable)

1. Strict refusal renders a dedicated card; its CTA re-sends with `mode=open`
2. Confidence badge bucket matches score thresholds; raw score in tooltip
3. A fenced code block is never rendered until its closing fence arrives
4. Auto-scroll happens **only** when pinned to bottom; otherwise "New messages" shows
5. Screen reader announces an assistant turn **once at completion**, not per token; Arabic messages carry `lang="ar"`
6. `429` shows a `Retry-After` countdown and disables send
7. History of 500+ messages scrolls smoothly (virtualization)
8. `prefers-reduced-motion` disables cursor blink and token fade
9. `tsc -b && vite build` passes; `bun audit` clean
10. All new components under 400 lines

## Verification note (from spec)

UX qualities (no layout thrash, SR cadence, RTL polish) **cannot be asserted in CI** — they require manual/browser QA (axe-core pass + VoiceOver spot-check). Treat acceptance criteria 1–8 as a manual QA checklist, not an automated gate.
