# Web Client UX v2 — Task Breakdown

**Feature:** web-ux-v2
**Source:** spec.md (Phase 2 output)
**Estimation unit:** iterations (1 iteration = design → code → test → refine)

---

## Overview

4 task groups, 25 subtasks. Critical path: G1 → G2 → G3 → G4. Parallelization available within G2 and G3.

**Estimated total:** 12 iterations sequential, ~9 iterations parallelized (2 streams).

---

## Dependency Graph

```
G1 (Foundation) ──→ G2 (Trust & Verifiability) ──→ G3 (Streaming UX) ──→ G4 (P1 Enhancements)
     │                    │                              │
     │                    ├─ P0-1 ConfidenceBadge        ├─ P0-6 Markdown buffering
     │                    ├─ P0-2 CitationCards          ├─ P0-7 Shiki highlighting
     │                    ├─ P0-3 RefusalCard            ├─ P0-8 Smart autoscroll
     │                    ├─ P0-4 Mode/ProvenanceChip    ├─ P0-9 Stop/Regenerate/Edit
     │                    └─ P0-5 Per-message lang        └─ P0-10 Streaming affordances
     │
     └─ All P1 items depend on G3 completion
```

**Parallelization:** Within G2, items P0-1 through P0-5 are independent (different components). Within G3, P0-6 and P0-8 are independent; P0-7 depends on P0-6 (shiki needs markdown container); P0-9 and P0-10 are independent.

---

## Group 1: Foundation & Hook Extraction

**Purpose:** Extract the streaming logic into a reusable hook, extend types, add new dependencies. This unblocks all other groups.

### Tasks

- [ ] 1.1 Extend `ChatMeta` type with `grounded` and `grounded_score` fields (`types.ts`) (not_started)
  - depends: none
  - acceptance: types compile, existing code unaffected
- [ ] 1.2 Install new dependencies: `react-markdown`, `remark-gfm`, `shiki`, `react-virtuoso` (not_started)
  - depends: none
  - acceptance: `bun install` succeeds, `bun audit` clean, `tsc -b` passes
- [ ] 1.3 Extract `useChatStream` hook from `App.tsx` (`lib/useChatStream.ts`) (not_started)
  - depends: 1.1
  - acceptance: Hook returns `{ messages, busy, send, stop, patchLast }`; `App.tsx` uses hook with identical behavior; streaming still works
- [ ] 1.4 Add CSS design tokens for confidence levels, refusal, chips, code blocks (`styles.css`) (not_started)
  - depends: none
  - acceptance: New `--confidence-*`, `--refusal-*`, `--chip-*`, `--code-*` custom properties defined; no visual regression
- [ ] 1.5 Refactor `rtl.ts` to export `langFor()` helper alongside `dirFor()` (not_started)
  - depends: 1.1
  - acceptance: `langFor(content, metaLang)` returns `"ar" | "en" | "pt"` using `meta.lang` when available, falling back to script detection

**Estimated iterations:** 2

---

## Group 2: Trust & Verifiability (P0 §2)

**Purpose:** Surface trust signals — confidence, citations, refusal UX, provenance. All [FE].

### Tasks

- [ ] 2.1 ConfidenceBadge component (`components/ConfidenceBadge.tsx`) (not_started)
  - depends: G1 (1.1, 1.4)
  - acceptance: Maps score → High (≥0.7 green) / Medium (0.4–0.7 amber) / Low (<0.4 red). Tooltip shows raw score. Compact inline badge.
- [ ] 2.2 CitationCards component — refactor Sources.tsx (`components/CitationCards.tsx`) (not_started)
  - depends: G1 (1.4)
  - acceptance: Each source shows label + page + score meter (0–1 visual bar) + expandable snippet + copy-citation button. Toggle "Sources (n)" retained. Replaces `Sources` import in `MessageList`.
- [ ] 2.3 RefusalCard component (`components/RefusalCard.tsx`) (not_started)
  - depends: G1 (1.3 — needs `send` callback access)
  - acceptance: Detects strict-refusal pattern (mode=strict, sources=[], refusal text). Renders distinct card with "Not in the knowledge base" heading + "Answer from general knowledge" CTA that re-sends same `q` with `mode=open`. Not shown for non-strict or non-refusal messages.
- [ ] 2.4 ModeChip and ProvenanceChip components (`components/Chips.tsx`) (not_started)
  - depends: G1 (1.1, 1.4)
  - acceptance: ModeChip shows `meta.mode` (strict/open/learning/learning_review). When `meta.self_ingested=true`, ProvenanceChip shows "AI-synthesized — not from official docs" + "saved to knowledge base" note. Synthesized never looks authoritative (different color/italics).
- [ ] 2.5 Integrate trust components into MessageList / AssistantBubble (not_started)
  - depends: 2.1, 2.2, 2.3, 2.4
  - acceptance: Each assistant message renders ConfidenceBadge (from best score or grounded_score), CitationCards (replacing old Sources), RefusalCard (conditional), ModeChip, ProvenanceChip. Per-message `lang` attribute set from `meta.lang` + `dir` from `dirFor()`. No regression in existing message display.

**Estimated iterations:** 3 (2.1–2.4 can be parallel; 2.5 is integration)

**Parallelization:** Tasks 2.1, 2.2, 2.3, 2.4 are fully independent — can be built in parallel by different developers or sequential fast-passes. Task 2.5 depends on all four.

---

## Group 3: Streaming UX (P0 §3)

**Purpose:** Calm streaming — markdown, code highlighting, scroll discipline, actions.

### Tasks

- [ ] 3.1 MarkdownBody component with fenced-code buffering (`components/MarkdownBody.tsx`) (not_started)
  - depends: G1 (1.2, 1.4)
  - acceptance: Renders via `react-markdown` + `remark-gfm`. While `streaming=true`, detects incomplete fenced code blocks (no closing ```) and buffers them — shows a skeleton/placeholder until the fence closes. No flicker of half-rendered tables or code blocks. When `streaming=false`, renders fully.
- [ ] 3.2 CodeBlock component with shiki highlighting + copy button (`components/CodeBlock.tsx`) (not_started)
  - depends: 3.1 (needs markdown container)
  - acceptance: Overrides `react-markdown`'s `code` renderer. Uses `shiki` (lazy-loaded via `React.lazy` + `Suspense`) for syntax highlighting. Shows a "Copy" button per code block. Falls back to un-highlighted `<pre><code>` while shiki loads or if it fails.
- [ ] 3.3 Smart autoscroll with "New messages" affordance (`components/MessageList.tsx` refactor) (not_started)
  - depends: G1 (1.3)
  - acceptance: Detects whether user is pinned to bottom (scroll position within threshold of scrollHeight). If pinned → auto-scroll on new content. If scrolled up → show "↓ New messages" floating button; clicking it scrolls to bottom. No scroll hijacking.
- [ ] 3.4 Regenerate + Edit-resend actions on messages (`components/ActionRow.tsx`) (not_started)
  - depends: G1 (1.3 — needs `send`/`stop`)
  - acceptance: **Regenerate** button on the last assistant message (non-streaming) — re-sends the preceding user question. **Edit-resend**: pencil/edit icon on user messages; clicking puts the text into the composer for editing; submitting sends as a new turn. Both are client-side only.
- [ ] 3.5 Streaming affordances — typing indicator, graceful error state (not_started)
  - depends: G1 (1.3)
  - acceptance: Before first token, show a typing/skeleton indicator (3 animated dots). On SSE `error` frame, render an inline error state in the bubble (icon + message), never a blank bubble. Remove `aria-live="polite"` from streaming bubbles (moved to completion in P1-7).
- [ ] 3.6 Integrate streaming components into MessageList / AssistantBubble (not_started)
  - depends: 3.1, 3.2, 3.3, 3.4, 3.5
  - acceptance: Assistant messages use `MarkdownBody` for rendering. Code blocks highlighted with shiki. Autoscroll is smart (pin-to-bottom detection). Regenerate/edit-resend available. Typing indicator shown before first token. Error states render inline.

**Estimated iterations:** 4 (3.1, 3.3, 3.4, 3.5 parallel; 3.2 after 3.1; 3.6 integration)

**Parallelization:** Tasks 3.1, 3.3, 3.4, 3.5 are independent. Task 3.2 depends on 3.1. Task 3.6 depends on all.

---

## Group 4: P1 Enhancements

**Purpose:** Input guidance, error UX, accessibility, performance.

### Tasks

- [ ] 4.1 Suggested-prompt chips (`components/SuggestedChips.tsx`) (not_started)
  - depends: G1 (1.3)
  - acceptance: 3–4 chips on empty state and after each assistant turn. Mode/lang-aware: at least one chip sends `lang=ar`, one sends `mode=open`. Clicking a chip sends the question immediately.
- [ ] 4.2 Character counter in Composer (not_started)
  - depends: none
  - acceptance: Live counter shown; send button disabled at 2000 chars (matches server validation). Counter color changes near limit.
- [ ] 4.3 Persisted controls — session-storage for mode/lang (not_started)
  - depends: none
  - acceptance: Mode/lang persisted in `sessionStorage`. Controls display compactly near composer. Restored on page reload.
- [ ] 4.4 Friendly problem+json display (`components/InlineError.tsx`) (not_started)
  - depends: none
  - acceptance: Maps `{title, detail, status}` to inline human messages. `correlation_id` shown behind a "Report issue" affordance (small toggle/link). No raw JSON shown to user.
- [ ] 4.5 Rate-limit countdown on 429 (not_started)
  - depends: G1 (1.3 — needs to surface Retry-After to UI state)
  - acceptance: On 429, read `Retry-After` header. Show countdown timer. Disable send during cooldown. Reflect `X-RateLimit-Remaining` subtly when low (e.g., < 5 remaining).
- [ ] 4.6 Enhanced connectivity badge (not_started)
  - depends: none
  - acceptance: HealthBadge shows "degraded" state clearly (not just "warn"). On-demand `/ready` probe via click/tap. Shows which dependency is down (Redis/ChromaDB).
- [ ] 4.7 Deferred SR announcements (not_started)
  - depends: G3 (3.5)
  - acceptance: `aria-live="polite"` on assistant bubble only when `streaming=false` (completion), not during streaming. SR announces the full message once.
- [ ] 4.8 `prefers-reduced-motion` refinements (not_started)
  - depends: G3 (3.5 — typing indicator)
  - acceptance: Under `prefers-reduced-motion: reduce`, disable typing indicator animation (cursor blink, token fade). Use static "…" instead of animated dots.
- [ ] 4.9 Keyboard refinements (not_started)
  - depends: none
  - acceptance: `Esc` stops streaming (while busy). Arrow keys navigate through expanded citation cards. Visible focus maintained.
- [ ] 4.10 Virtualized message history (`react-virtuoso` integration) (not_started)
  - depends: G3 (3.3 — smart autoscroll)
  - acceptance: `react-virtuoso` wraps the message list. `followOutput="smooth"` for streaming append. 500+ messages scroll smoothly. "New messages" affordance works with virtualization.
- [ ] 4.11 Lazy highlight & code-split shiki (not_started)
  - depends: G3 (3.2 — CodeBlock)
  - acceptance: `shiki` loaded via `React.lazy` + `Suspense`. No first-paint cost. Bundle analysis shows shiki in separate chunk.

**Estimated iterations:** 4 (several items can be parallelized)

**Parallelization:** Tasks 4.1, 4.2, 4.3, 4.4, 4.6, 4.9 are independent. Tasks 4.5, 4.7, 4.8, 4.10, 4.11 have dependencies noted.

---

## Critical Path

```
G1 (2 iter) → G2 (3 iter) → G3 (4 iter) → G4 (4 iter) = 13 iterations sequential
```

With parallelization (2 streams):
```
Stream A: G1 → G2.1/.2/.3/.4 → G2.5 → G3.1 → G3.2 → G3.6 → G4.5/.7/.8/.10/.11
Stream B:                G3.3/.4/.5 ──────────→ G3.6 → G4.1/.2/.3/.4/.6/.9

~9 iterations parallelized
```

---

## Component Size Enforcement

| Component | Est. lines | Under 400? |
|-----------|-----------|------------|
| `lib/useChatStream.ts` | ~120 | ✅ |
| `components/ConfidenceBadge.tsx` | ~40 | ✅ |
| `components/CitationCards.tsx` | ~120 | ✅ |
| `components/RefusalCard.tsx` | ~60 | ✅ |
| `components/Chips.tsx` | ~80 | ✅ |
| `components/MarkdownBody.tsx` | ~100 | ✅ |
| `components/CodeBlock.tsx` | ~80 | ✅ |
| `components/ActionRow.tsx` | ~60 | ✅ |
| `components/SuggestedChips.tsx` | ~60 | ✅ |
| `components/InlineError.tsx` | ~50 | ✅ |
| `components/MessageList.tsx` (refactored) | ~200 | ✅ |
| `components/Composer.tsx` (enhanced) | ~150 | ✅ |
| `App.tsx` (slimmed) | ~100 | ✅ |
| `styles.css` (expanded) | ~550 | ⚠️ — split into component CSS files at ~400 |

**CSS strategy:** When `styles.css` approaches 400 lines, extract component-specific CSS into `components/*.css` files imported by each component. The main `styles.css` keeps tokens and global rules only.

---

## Focused Testing Approach

Per the spec-architect methodology: 2–8 tests per group, max 10 for gap-filling. Manual QA checklist for UX acceptance criteria.

### Group 1 (Foundation): 3 tests
- Types compile and `ChatMeta` fields are present
- `useChatStream` hook returns correct interface
- New dependencies install and audit clean

### Group 2 (Trust): 5 tests
- ConfidenceBadge maps scores to correct buckets
- CitationCards renders score meter, snippet, copy action
- RefusalCard detects strict-refusal pattern and fires CTA with `mode=open`
- ModeChip renders correct mode label; ProvenanceChip shows AI-synthesized warning
- Per-message `lang` attribute matches `meta.lang`

### Group 3 (Streaming): 6 tests
- MarkdownBody buffers incomplete fenced code during streaming
- CodeBlock lazy-loads shiki and renders highlighted code
- Smart autoscroll: pinned-to-bottom detection works; "New messages" shows when scrolled up
- Regenerate re-sends last user question
- Edit-resend populates composer with user message text
- Error SSE frame renders inline error state (not blank bubble)

### Group 4 (P1): 5 tests
- Character counter disables send at 2000
- SuggestedChips send with correct mode/lang overrides
- Rate-limit countdown reads `Retry-After` and disables send
- `aria-live` only on completed (non-streaming) messages
- Virtualized list renders 500+ messages without jank (manual verification)

**Total: 19 focused tests** — within the 16–34 range.

---

## Task Status Tracking

Use these markers to track progress during implementation:
- `- [ ]` — not_started
- `- [~]` — in_progress
- `- [x]` — completed
- `- [-]` — blocked

Update via: "Mark task 2.1 as in_progress", "Update task 3.6 to completed", etc.
