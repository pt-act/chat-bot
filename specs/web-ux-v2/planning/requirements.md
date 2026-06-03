# Web Client UX v2 — Planning / Requirements

**Feature:** web-ux-v2
**Source spec:** `docs/audit/web_UX_SPEC.md` (v2, 2026-05-31)
**Current client:** `web/` — Vite + React 18 + TypeScript, plain CSS, 7 components, SSE streaming, RTL, basic citations
**Date:** 2026-06-02

---

## 1. Problem Statement

The current web client is a clean MVP — streaming works, mode/lang selectors exist, citations render, and RTL/a11y basics are in place. But it fails to leverage the *product's differentiators*: **trust/verifiability** (scores, groundedness, provenance) and **mode/language fluidity** (per-request controls). A user cannot tell how confident an answer is, whether it was synthesized by AI or grounded in docs, or what to do when strict mode refuses. The streaming UX has no markdown rendering, no scroll discipline, and no graceful error states.

## 2. What this product is (from the spec)

A **citations-grounded, multi-mode, multilingual RAG knowledge assistant**. Core questions:
- *"Can I trust this?"* → confidence badge, groundedness signal, provenance chips
- *"Where did it come from?"* → citation cards with score + snippet
- *"Can I get it in the mode/language I need?"* → mid-conversation mode/lang switching

**Explicitly deprioritized:** Generative UI, Vercel AI SDK `useChat`, backend branching — these are low value for a policy-RAG bot.

## 3. Backend data already available (no FS work needed for P0/P1)

The backend already returns everything P0/P1 needs. No backend changes required until P2+.

| Data | Where it comes from | Currently used in web client? |
|------|---------------------|-------------------------------|
| `sources[].score` (0–1) | `POST /api/v1/chat` response / SSE `sources` event | Partially — shown as raw decimal in Sources |
| `meta.mode` | SSE `done` event | No |
| `meta.grounded` / `meta.grounded_score` | SSE `done` event | No |
| `meta.self_ingested` | SSE `done` event | Partially — "learned" badge, but no AI-synthesized warning |
| `meta.lang` | SSE `done` event | No |
| `meta.correlation_id` | SSE `done` event | No |
| `meta.model` | SSE `done` event | No |
| `Retry-After` header | 429 response | Partially — shown as text, no countdown |
| `X-RateLimit-Remaining` | Response headers | No |
| `/health` status | HealthBadge component | Yes |
| `/ready` endpoint | Not polled | No |
| `sources[].snippet` | Chat response / SSE | Partially — shown in expanded sources |

## 4. Existing code to reuse / extend

| Component | Current state | What to extend |
|-----------|--------------|----------------|
| `App.tsx` | State management, `send()` callback, SSE wiring | Add `useChatStream` hook extraction, regenerate/edit-resend logic, suggested prompts state |
| `MessageList.tsx` | Flat list, `scrollIntoView` on every update, `aria-live="polite"` per bubble | Virtualization (`react-virtuoso`), smart autoscroll with "New" affordance, `aria-live` only on stream completion, per-message `lang` attribute, confidence badge, mode/provenance chips, refusal card |
| `Sources.tsx` | Collapsible list with label/page/score/snippet | Citation cards with score meter, copy action, expandable snippet |
| `Composer.tsx` | Textarea + send/stop buttons | Character counter (2000 limit), suggested prompt chips, persisted mode/lang display |
| `Controls.tsx` | Mode/lang `<select>` dropdowns | Compact inline display near composer |
| `HealthBadge.tsx` | Polls `/health` every 15s | Add `/ready` on-demand, degraded indicator |
| `lib/api.ts` | `streamChat()`, `uploadDocument()`, review functions | `useChatStream` React hook, rate-limit header extraction, markdown buffering helpers |
| `lib/rtl.ts` | `dirFor()` based on Arabic script | Also set `lang` attribute per message |
| `styles.css` | Plain CSS, dark theme, 390 lines | New tokens for confidence levels, citation cards, refusal state, chips, markdown/code blocks |

## 5. New dependencies (from spec recommendations)

| Package | Purpose | Justified? |
|---------|---------|------------|
| `react-markdown` + `remark-gfm` | Markdown rendering with GFM tables/lists, fenced code buffering | Yes — P0 streaming UX |
| `shiki` | Syntax highlighting for code blocks (lazy loaded) | Yes — P1 perf (lazy), P0 code blocks |
| `react-virtuoso` | Virtualized message list for long conversations | Yes — P1 perf, acceptance criterion: 500+ messages smooth |

**Not adding:** Tailwind, shadcn/ui, Vercel AI SDK — spec says they're optional and P0/P1 doesn't depend on them. Staying with plain CSS to match existing convention.

## 6. Phasing (from the spec)

### P0 — Trust & Calm Streaming (ship first)

**Trust & Verifiability (§2 of UX spec):**
1. Confidence badge per answer (High ≥ 0.7 / Medium 0.4–0.7 / Low < 0.4)
2. Citation cards (label · page · score meter · expandable snippet · copy)
3. Strict-mode refusal card with "Answer from general knowledge" CTA
4. Mode & provenance chips on each assistant message
5. Per-message `lang` attribute (correct SR pronunciation)

**Streaming UX (§3 of UX spec):**
6. Markdown rendering with fenced-code buffering (react-markdown + remark-gfm)
7. Code block syntax highlighting (shiki, lazy) + copy button
8. Smart autoscroll (pin-to-bottom detection, "↓ New" affordance)
9. Stop / Regenerate / Edit-resend buttons
10. Streaming affordances (typing indicator, graceful error state)

### P1 — Input, Errors, A11y, Perf

**Input & Guidance (§4):**
11. Suggested-prompt chips (mode/lang-aware, on empty + after turns)
12. Character counter (≤ 2000, disable send past limit)
13. Persisted controls (session-storage mode/lang near composer)

**Errors, Limits & Connectivity (§5):**
14. Friendly problem+json display (inline, correlation_id behind "Report issue")
15. Rate-limit countdown on 429 (Retry-After, disable send)
16. Enhanced connectivity badge (poll `/ready` on demand)

**Accessibility (§6):**
17. Deferred SR announcements (announce once on stream complete, not per token)
18. `prefers-reduced-motion` — disable cursor blink and token fade
19. Keyboard refinements (Esc to stop, arrow-nav through citations)
20. Per-message `lang` for bilingual SR (already in P0 item 5)

**Performance (§7):**
21. Virtualized history (react-virtuoso)
22. Lazy highlight & code-split shiki

### P2 — Conversation Management (§8)

23. New conversation (rotate X-User-Id)
24. Memory transparency (show TTL, export transcript)
25. Edit & fork — client-side edit-resend ships in P0 (#9); true branching is [FS], deferred

### Optional / Future [FS] (§9 — explicitly deprioritized)

26. Feedback persistence — backend already has `POST /api/v1/feedback`; wire inline 👍/👎
27. Generative UI — low value for policy-RAG, requires tool-calling
28. Vercel AI SDK — protocol mismatch with our SSE, not worth adopting
29. Branching memory store — backend redesign needed

## 7. Constraints

- **No backend changes** for P0/P1 — all data is already returned
- **400-line component limit** — decompose if approaching
- **Plain CSS** — no Tailwind/shadcn unless team decides otherwise later
- **Keep existing a11y** — RTL, focus rings, aria-live, keyboard send — build on them, don't regress
- **Keep build clean** — `tsc -b && vite build` must pass, `bun audit` clean
- **No new runtime deps beyond** react-markdown, remark-gfm, shiki, react-virtuoso
- **Mobile-responsive** — the current layout is desktop-focused; new components should not break mobile viewport

## 8. Risks

| Risk | Mitigation |
|------|-----------|
| Markdown buffering complexity (incomplete fences) | Buffer detection is a regex on the token stream — well-understood pattern, test with fixture streams |
| shiki bundle size | Lazy-load via `React.lazy` + `Suspense`; no first-paint cost |
| react-virtuoso + streaming append | Virtuoso has `followOutput` prop designed for chat; test with 500+ messages |
| Edit-resend is client-side only (no server branching) | Accept the limitation — re-send creates a new turn; document it |
| CSS grows beyond 400 lines | Extract component-specific CSS files if needed |
| Strict refusal → "Answer from general knowledge" CTA requires re-sending the same question with mode=open | This is a simple client re-call — `send()` already accepts `mode` override |

## 9. Consciousness alignment (Gate 1)

- **Integrity over efficiency:** Every claim is one click from its source — confidence badges and citation cards make trust verifiable, not assumed. ✅
- **Glass box over black box:** Mode/provenance chips reveal *how* the answer was produced. Groundedness is surfaced, not hidden. ✅
- **Contemplation over distraction:** Calm streaming, no layout thrash, scroll discipline. No generative widgets that create noise. ✅
- **Co-creation, not performance:** Strict refusal becomes a guided path, not a dead end. The user chooses whether to relax mode. ✅

**Gate 1: PASS** — The spec serves genuine progress (verifiability, trust, calm UX), not performative productivity.
