# chat-bot — Improvement Proposals

**Author:** engineering review · **Date:** 2026-05-31 · **Scope:** whole project (backend, retrieval, ops, product), complementary to the existing frontend `docs/audit/web_UX_SPEC.md`.

---

## 0. Framing: what the product is, and where the leverage is

`chat-bot` is a **citations-grounded, multi-mode, multilingual, privacy-capable RAG knowledge assistant**. Its value proposition rests on one promise above all others: **"you can trust this answer because it's grounded in your documents, and you can verify it."** Everything compelling about it — strict mode, citations, the new `learning_review` human gate, local upload — serves that promise.

The frontend `web_UX_SPEC.md` already covers the *presentation* of trust (confidence badges, citation cards, refusal-as-a-feature, calm streaming, a11y). It deliberately leaves the *substance* — whether the answer is actually grounded, whether retrieval found the right thing, whether the system is reliable enough to depend on — to the backend. That is exactly where the project's own documented **Known limitations** live:

- *"Retrieval quality is not validated against a live corpus"* — the bot can retrieve poorly or hallucinate and nothing catches it.
- *In-process async ingest* (FastAPI `BackgroundTasks`) — not durable across restarts.
- *No `/chat` authentication*; rate limiter is per-IP and fails open.
- *Feedback not persisted*; *no citation deep-links*; *linear memory (no branching)*.

So the highest-leverage improvements make the **grounding promise actually true and measurable**, and make the **pipeline reliable enough to bet on**. That framing drives the ranking below.

---

## 1. The 30 ideas (thought-through, with verdicts)

Effort: **S** ≈ a node/endpoint + tests · **M** ≈ multiple modules / new dep · **L** ≈ infra/redesign.

### A. Retrieval & answer quality (the core promise)
1. **Context-aware query rewriting** — condense follow-ups ("what about damaged items?") into a standalone query using the rolling summary + recent turns *before* retrieval. Today `retrieve_context` searches the raw last message, so multi-turn retrieval is context-blind even though generation is context-aware. *Effort: S. Verdict: TOP-5 #1 — biggest correctness win per line of code.*
2. **Groundedness / faithfulness verification** — after generation, verify the answer is supported by the retrieved chunks; expose a real `grounded` signal and, in strict mode, refuse/warn when unsupported. Directly attacks hallucination, the #1 RAG failure. *Effort: S–M. Verdict: TOP-5 #2.*
3. **Hybrid retrieval (BM25 + dense)** — lexical recall for acronyms, SKUs, exact phrases that embeddings miss. *Effort: M (new index/dep). Verdict: strong, but heavier; #1 captures much of the multi-turn gain first.*
4. **Reranking after MMR** — cross-encoder or LLM rerank the candidate pool for precision. *Effort: M. Verdict: good, but latency/dep cost; do after measuring need (see #19).* 
5. **Structure-aware chunking per format** — split DOCX/HTML/MD on headings, carry section titles into chunk metadata. *Effort: M. Verdict: solid quality win; pairs with the new multi-format loaders.*
6. **Inline citation markers** — render `[1][2]` tied to specific sentences, not just a source list. *Effort: M (prompt + parse reliability). Verdict: very on-brand but overlaps the web spec's citation work; model citation discipline is finicky.*
7. **Multi-query retrieval** — fan out N paraphrases, union results. *Effort: S–M. Verdict: helps recall, adds latency/cost; lower priority than #1.*
8. **Adaptive `top_k`/threshold by query type** — short factual vs. broad. *Effort: M, fuzzy. Verdict: speculative; defer.*

### B. Trust & transparency
9. **"Why this answer" trace** — show retrieved chunks, scores, and which were actually used. *Effort: S–M. Verdict: great for power users/debugging; partly enabled by #2.*
10. **Persistent feedback + closed quality loop** — `POST /feedback` (rating, reason, captured Q/A/sources) → store → low-rated answers seed the review queue & RAGAS golden set. *Effort: S–M. Verdict: TOP-5 #3 — turns one-shot eval into continuous improvement.*
11. **Faithfulness-driven confidence** — feed the web confidence badge with #2's signal (answer-supported), not just retrieval score. *Effort: S. Verdict: merge into #2.*
12. **Answer ↔ document version surfacing** — show which doc `version` backed the answer (we already store it). *Effort: S. Verdict: nice, narrow.*

### C. Reliability & ops
13. **Durable, retryable ingestion** — replace in-process `BackgroundTasks` with a Redis-backed job + worker, retries, idempotency; survive restarts. *Effort: M. Verdict: TOP-5 #4 — the KB is the product; its population path must be reliable.*
14. **Provider retry/backoff + circuit breaker** — wrap LLM/embedding calls; transient 429/5xx shouldn't fail a turn. *Effort: S. Verdict: high-ROI hardening; honorable mention.*
15. **OpenTelemetry tracing + Prometheus metrics** — spans per graph node, latency/error/cost metrics. *Effort: M. Verdict: valuable for operators, less user-facing.*
16. **Graceful Redis-down degradation** — run statelessly (no memory) instead of 500ing. *Effort: S. Verdict: good resilience; honorable mention.*
17. **Idempotency keys** for chat/ingest retries. *Effort: S. Verdict: useful with #13.*
18. **Expanded readiness** — provider reachability, queue depth, model warmup in `/ready`. *Effort: S. Verdict: minor.*
19. **Eval as opt-in/scheduled CI + a hermetic retrieval-regression test** — seed a tiny corpus, assert recall@k so quality can't silently regress. *Effort: S–M. Verdict: strong companion to #1–#5; honorable mention.*
20. **SSE keepalive + resumable streams** — heartbeat, reconnect/resume. *Effort: M. Verdict: niche until scale.*

### D. Security & multi-tenancy
21. **Authentication for `/chat`** (JWT/session/API key). *Effort: M. Verdict: real gap, but often handled at the gateway; deployment-dependent.*
22. **Per-user rate limiting + tiered quotas** (today per-IP). *Effort: S–M. Verdict: good with auth (#21).*
23. **PII/secret redaction at ingest time** (not just output). *Effort: M. Verdict: privacy-aligned; complements guardrails.*
24. **Multi-tenant KB isolation** (per-tenant collections + ACL). *Effort: L. Verdict: powerful but a bigger redesign.*

### E. Performance & cost
25. **Answer cache (exact + semantic) with re-ingest invalidation.** *Effort: M. Verdict: good at traffic; invalidation is the catch.*
26. **Token/cost accounting in `meta` + per-user budgets.** *Effort: S–M. Verdict: useful for ops/FinOps.*
27. **Embedding cache + model warm-load** to cut first-token latency. *Effort: S–M. Verdict: incremental.*

### F. Ingestion & content ops
28. **Batch/folder ingest + KB export/import** (backup/portability). *Effort: M. Verdict: operational nicety.*
29. **Reviewer UI for the `learning_review` queue** (web). *Effort: M. Verdict: completes the feature I shipped; valuable but narrow audience.*

### G. Adoptability
30. **Configurable persona/system prompt + domain scoping** — de-hardcode "assistant for our company"; make persona, refusal copy, and domain framing config/per-request. *Effort: S. Verdict: TOP-5 #5 — turns a single-tenant demo into a deployable product.*

---

## 2. Winnowing criteria

I scored each on: **(a)** alignment to the core value prop (grounded trust), **(b)** confidence of net-positive (consensus best-practice + contained blast radius), **(c)** pragmatism (effort vs. payoff, hermetic-test-friendliness, minimal new deps), and **(d)** non-redundancy with the already-planned web spec. The top 5 deliberately span **quality (1,2)**, **continuous improvement (3)**, **reliability (4)**, and **adoptability (5)** rather than piling into one axis.

---

## 3. The 5 best ideas (best → worst)

### #1 — Context-aware query rewriting before retrieval

**What it is.** Insert a step that rewrites the user's latest message into a **self-contained search query** using the conversation summary + recent turns, then retrieve on *that* — instead of on the raw last message.

**The concrete gap it fixes.** In `graph/nodes/retrieve_context.py`, retrieval runs on `state["question"]` verbatim. But `generate_answer` already feeds history + summary to the LLM. So generation is context-aware while **retrieval is context-blind.** A turn like *"and what about damaged ones?"* embeds to nothing useful; MMR returns noise; strict mode then **falsely refuses** a question the KB can actually answer. This is the most common real-world RAG failure in multi-turn chat, and this codebase is multi-turn by design (it has summarization + memory).

**How it works.** A tiny node `condense_query` (or a helper inside `retrieve_context`) runs only when there's prior context: prompt the LLM (temperature 0, ~64 max tokens) — *"Rewrite the user's question as a standalone search query using the conversation. Output only the query."* Use the rewritten query for embedding/MMR; keep the original `question` for generation and display. Skip rewriting on the first turn or when no memory exists. Config flag `QUERY_REWRITE_ENABLED` (default on); cache by `(summary_hash, question)`.

**How users perceive it.** They won't see a new control — they'll just notice the bot "gets" follow-ups: pronouns and ellipses resolve, fewer "I don't have information about that" dead-ends, citations that actually match the question. It makes the assistant feel *conversational* rather than *one-shot*.

**Why it's obviously better, and why I'm confident.** It's textbook RAG (the "condense question" pattern is standard in LangChain/LlamaIndex for exactly this reason), the gap is demonstrably present in the code, and the blast radius is contained (one node, one cheap LLM call, fully behind a flag, easy to A/B). It improves *every* downstream signal — retrieval relevance, citation accuracy, strict-mode refusal precision, and the web spec's confidence badge — without touching the API contract. Risk: one extra short LLM call per turn (latency/cost) and occasional over-rewriting; both are mitigated by the first-turn skip, low token budget, caching, and the flag. Net: high value, very high confidence, small effort.

**Effort:** S. New node + wiring in `graph/builder.py`/`services/chat_service.py` + a prompt + unit tests (assert the rewritten query is used for retrieval while the original drives generation).

---

### #2 — Groundedness / faithfulness verification (anti-hallucination backstop)

**What it is.** After generation, check whether the answer's claims are **actually supported by the retrieved chunks**, expose that as a real signal in `meta`, and let strict mode act on it (refuse or warn when unsupported).

**The concrete gap it fixes.** The project's own docs admit retrieval/answer quality is unvalidated, and the guardrails I added cover *input* injection and *output* PII/length — **not faithfulness.** Critically, the web spec's confidence badge maps the *retrieval score*, which measures "did we find similar text," **not** "is the answer true to that text." A high-similarity chunk can still be paraphrased into a wrong/hallucinated claim. For a product whose entire pitch is "trust the grounded answer," shipping an unverified answer under a green "High confidence" badge is the most dangerous failure mode.

**How it works.** A `verify_answer` step (post-`generate_answer`) computes a groundedness verdict. Two tiers, config-selectable:
- **Cheap/deterministic:** lexical/semantic overlap between answer sentences and retrieved chunks (no extra model call) → coarse supported/partial/unsupported.
- **Accurate:** a single LLM judge call returning JSON `{grounded: bool, unsupported_claims: []}` (NLI-style).

Attach `meta.grounded` (+ optional unsupported spans). In `strict` mode, if `grounded=false`, convert to the "Not in the knowledge base" refusal the web spec already designs for. In `open`/`learning`, downgrade the confidence badge and add the existing "based on general knowledge" provenance note. Off-path and toggleable so latency-sensitive deployments can opt out.

**How users perceive it.** The confidence badge becomes *honest*: it now reflects whether the answer is backed by the cited text, not just whether similar text exists. Fewer confidently-wrong answers — the thing that destroys trust in a knowledge assistant. Pairs perfectly with the web spec's badge + citation cards.

**Why it's obviously better, and why I'm confident.** It directly operationalizes the core value proposition; "faithfulness" is the headline RAGAS metric for precisely this reason (and the eval harness I built already measures it offline — this brings it inline). Confidence is high that *some* groundedness gate is net-positive for a trust product. The honest caveat: the accurate tier adds an LLM call (cost/latency) and judges are imperfect — hence the deterministic tier and the config switch, and hence I rank it #2 not #1 (it's heavier than query rewriting and needs threshold tuning per corpus).

**Effort:** S–M. New node + prompt/heuristic + `meta` field + strict-mode wiring + tests (assert unsupported answers flip strict to refusal).

---

### #3 — Persistent feedback + a closed quality loop

**What it is.** Add `POST /api/v1/feedback` (message/correlation id, 👍/👎, optional reason, and a snapshot of the question/answer/sources), persist it, and **wire it into the machinery that already exists**: low-rated answers surface in a review list and can seed the RAGAS `eval/golden.jsonl`.

**The concrete gap it fixes.** The web spec wants inline feedback but correctly refuses to fake it without a store ("cosmetic unless stored… add the endpoint, then wire it"). Right now there is **no signal at all** from real usage back into quality. The team has the *pieces* for continuous improvement — an offline RAGAS harness and a human `review` workflow — but nothing connects production reality to them.

**How it works.** Reuse existing patterns: a typed `schemas/feedback.py`, a `controllers/v1/feedback.py`, and Redis storage mirroring `review/keys.py` (`feedback:{id}` hash + an index set). Capture the `correlation_id` already threaded through logs so feedback is traceable to the exact turn. Add `GET /api/v1/feedback?rating=down` (API-key gated, like review/ingest) and an "export to golden set" helper that appends thumbs-down items to the eval dataset for targeted regression coverage. Unblocks the web spec's inline 👍/👎.

**How users perceive it.** End users get a one-click way to flag a bad answer (and feel heard); operators get a prioritized queue of real failures and a growing, reality-based eval set. It converts the product from "ships answers" to "learns from how its answers land."

**Why it's obviously better, and why I'm confident.** It's the cheapest way to create a durable improvement *flywheel*, it's explicitly the missing backend piece the frontend already planned around, and it composes with #2 (groundedness) and #19 (eval gate) so they reinforce each other. Confidence is high because the effort is modest, the pattern is already established in this repo (review service/keys), and the value compounds over time. Lower than #1/#2 only because it improves quality *indirectly* (via humans/eval) rather than at answer time.

**Effort:** S–M. Endpoint + schema + Redis store + tests; optional golden-set exporter.

---

### #4 — Durable, retryable ingestion pipeline

**What it is.** Replace the in-process FastAPI `BackgroundTasks` ingestion with a **durable Redis-backed job** processed by a worker, with retries, idempotency, and crash-safety.

**The concrete gap it fixes.** A documented limitation: today ingestion runs inside the web process via `BackgroundTasks`. If the process restarts mid-ingest (deploy, crash, OOM during embedding of a large PDF/DOCX), the job is lost and the document is stuck in `queued`/partial — with no retry. The KB **is** the product; the path that populates it is currently the least reliable part of the system, and I just *widened* it (multi-format + local upload), so more/larger files flow through it.

**How it works.** The status model already lives in Redis (`ingest_status:{doc_id}`, `ALL_DOCS_KEY`). Add a durable job record + a worker loop (a minimal `RQ`/`arq` worker, or even a Redis list + a `python -m ingest.worker` process) that: claims a job, runs the existing `process_policy`/`process_uploaded`, retries with backoff on transient failure, and is idempotent via the content hash you already compute (re-running a half-done job converges, never duplicates). `docker-compose` gains a `worker` service; the API just enqueues. Local-dev can keep an inline fallback.

**How users perceive it.** Operators perceive it most: deploys no longer drop in-flight ingests, large files reliably finish, and failures retry instead of silently stalling. End users get a KB they can trust to actually contain what was uploaded.

**Why it's obviously better, and why I'm confident.** It closes a named reliability gap on the most value-critical path, and the design reuses primitives already present (Redis status, content-hash idempotency), so it's evolutionary, not a rewrite. Confidence is high on the *value*; it's #4 (not higher) because it's more infra than user-facing magic, and "is `BackgroundTasks` good enough?" genuinely depends on scale — small single-instance deployments feel this less, so the payoff is deployment-dependent.

**Effort:** M. Worker process + job model + retry/idempotency + compose wiring + tests (enqueue, claim, retry, idempotent re-run).

---

### #5 — Configurable persona, refusal copy & domain scoping

**What it is.** De-hardcode the assistant's identity. Today every prompt in `prompts/answer.py` says *"You are a helpful assistant for our company"* and the strict refusal says *"contact support."* Make the **persona, domain framing, and refusal/escalation copy** configurable (env defaults, optionally per-request).

**The concrete gap it fixes.** The project is a genuinely good RAG stack, but it's wearing a single tenant's clothes. Anyone adopting it must edit prompt source to make it theirs — friction that caps reuse. There's also a correctness angle: a generic persona answers a legal-policy corpus the same way it answers an internal-IT corpus, when domain framing measurably improves tone, refusal behavior, and relevance.

**How it works.** Add settings like `ASSISTANT_NAME`, `ASSISTANT_PERSONA`, `KNOWLEDGE_DOMAIN`, `SUPPORT_CONTACT`/`ESCALATION_MESSAGE`, and template them into the existing strict/open/learning/learning_review prompt builders (the builders already take parameters — this just adds a few). Keep current strings as defaults so behavior is unchanged out of the box. Optional: allow a per-request `system_hint` (length-capped, guardrail-checked) for multi-persona deployments.

**How users perceive it.** Deployers perceive it as "this is *our* assistant" with minutes of config instead of code edits; end users get answers framed for their domain and a refusal that routes them to the *right* next step rather than a generic "contact support."

**Why it's obviously better, and why I'm confident.** Low effort, low risk (defaults preserve today's behavior, covered by existing prompt tests), and it materially widens who can adopt the project while modestly improving answer fit. Confidence is high on safety/accretiveness; it's ranked #5 because it lifts *adoptability and polish* rather than core answer correctness — important, but a smaller jump than #1–#4.

**Effort:** S. Config fields + prompt templating + tests asserting overrides flow into the prompt.

---

## 4. Honorable mentions (strong, just outside the 5)

- **Provider retry/backoff + circuit breaker (#14)** — cheapest reliability win after #4; a transient provider 429 shouldn't kill a turn.
- **Hermetic retrieval-regression test + opt-in eval CI (#19)** — the guardrail that keeps #1/#2/#5 from silently regressing; natural pair to the feedback loop (#3).
- **Hybrid retrieval + rerank (#3/#4 in §1)** — the next quality tier once #1 lands and #19 can prove the lift is real.
- **Reviewer UI for `learning_review` (#29)** — completes the two-phase ingest feature already shipped.

## 5. Suggested sequence

1. **Query rewriting (#1)** and **groundedness (#2)** together — they compound and make the web spec's trust UI *mean something*.
2. **Feedback loop (#3)** + a **hermetic eval-regression test (#19)** — so #1/#2 are measurable and protected.
3. **Durable ingestion (#4)** — harden the value-critical path.
4. **Persona config (#5)** — open the door to broader adoption.
</content>
