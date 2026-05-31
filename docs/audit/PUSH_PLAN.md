# Push Plan — Stacked PRs

Target repo: `pt-act/chat-bot`. **11 branches, 11 PRs, each based on the previous**
(stacked), in this order. Nothing is pushed until a GitHub token is provided.

## PR stack (base ← head)

| # | PR title | Base branch | Head branch |
|---|----------|-------------|-------------|
| 1 | fix: critical LLM param crash, SSRF redirect, deps & broken tests | `main` | `audit/low-risk-fixes` |
| 2 | harden: DNS-rebinding SSRF + CI Redis service & self-sufficient env | `audit/low-risk-fixes` | `audit/ci-and-ssrf-hardening` |
| 3 | harden(api): generic 5xx, namespaced+validated memory keys, cleanup | `audit/ci-and-ssrf-hardening` | `audit/hardening-batch-2` |
| 4 | harden(rag): isolate self-ingested synthesized answers (M-5) | `audit/hardening-batch-2` | `audit/synthesized-isolation` |
| 5 | test(graph): end-to-end integration test through real get_llm path | `audit/synthesized-isolation` | `audit/graph-integration-test` |
| 6 | feat(api): v1 contract — typed envelope, problem+json, OpenAPI, /api/v1 | `audit/graph-integration-test` | `feat/api-v1-core` |
| 7 | feat(api): per-request controls, structured citations, rate-limit headers | `feat/api-v1-core` | `feat/api-controls-citations` |
| 8 | feat(api): SSE streaming chat endpoint | `feat/api-controls-citations` | `feat/api-streaming` |
| 9 | feat(api): async ingest (202 + poll) + docs pagination | `feat/api-streaming` | `feat/async-ingest` |
| 10 | feat(web): reference chat SPA (Vite + React + TS) | `feat/async-ingest` | `feat/web-client` |
| 11 | docs: refresh README + add user_guidelines.md and PTD.md | `feat/web-client` | `feat/docs` |

> Stacked review benefit: each PR's diff shows **only its own change**. Merge bottom-up
> (1→11); GitHub retargets the next PR's base automatically as each merges. Alternatively,
> merge sequentially and the stack collapses cleanly onto `main`.

## Commands (run once the token is exported)

```bash
# Auth for this push only (not persisted to disk):
export GH_TOKEN=<provided token>
REPO=pt-act/chat-bot

# Push all branches:
for b in audit/low-risk-fixes audit/ci-and-ssrf-hardening audit/hardening-batch-2 \
         audit/synthesized-isolation audit/graph-integration-test \
         feat/api-v1-core feat/api-controls-citations feat/api-streaming \
         feat/async-ingest feat/web-client feat/docs; do
  git push "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" "$b"
done

# Open the 11 stacked PRs (via API; bodies from pr-drafts/ + commit messages):
#   POST /repos/pt-act/chat-bot/pulls  { title, head, base, body }
# (Performed programmatically using GH_TOKEN.)
```

## After the push (important)
1. I will confirm each branch/PR URL.
2. **Rotate or revoke the token immediately** — a token pasted in chat can persist in
   history regardless of deletion; rotation is the only reliable invalidation.
3. The token is used only for the push/PR creation and is never written to a file or
   committed.

## Token scope needed
A fine-grained PAT limited to `pt-act/chat-bot` with:
- **Contents: Read and write** (push branches)
- **Pull requests: Read and write** (open PRs)
