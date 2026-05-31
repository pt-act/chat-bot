# Security Policy

This document describes the supported versions, how to report vulnerabilities, the
security model, and the current known/residual risks for **`chat-bot`** — a
citations-grounded, multi-mode, multilingual, privacy-capable RAG knowledge-assistant
backend (LangChain + LangGraph + ChromaDB + FastAPI).

_Last updated: 2026-05-31 · Applies to: v2.4.0_

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.4.x   | ✅ Security fixes |
| 2.3.x   | ⚠️ Best effort (please upgrade) |
| < 2.3   | ❌ Unsupported |

Security fixes are released against the latest minor (`2.4.x`). Older lines should upgrade;
the API is backward compatible (unversioned `/api/*` remains as a deprecated alias).

---

## Reporting a Vulnerability

**Please do not open a public issue for security reports.** Disclose privately so a fix
can ship before details are public:

1. **Preferred:** open a private advisory via GitHub →
   `Security` → `Report a vulnerability` (GitHub Security Advisories) on
   `https://github.com/pt-act/chat-bot`.
2. **Alternative:** email the maintainer (replace with your contact, e.g.
   `security@your-domain`), ideally with a PGP key if available.

Please include: affected version/commit, a description and impact, reproduction steps or a
proof of concept, and any suggested remediation.

**Response targets (best effort for an open-source project):**

| Stage | Target |
|-------|--------|
| Acknowledgement | within 3 business days |
| Initial assessment / severity | within 7 business days |
| Fix or mitigation plan | within 30 days (sooner for critical) |
| Coordinated disclosure | after a fix is available, by mutual agreement |

We support coordinated disclosure and will credit reporters who wish to be named.

---

## Security Model (summary)

The threat model centers on the value-critical paths: document ingestion, retrieval,
and the chat API. Controls in place:

- **Authentication (ingest):** API-key dependency (`X-API-Key`). `DELETE /ingest/{doc_id}`
  always requires the key when `API_KEY` is set; other ingest/management endpoints require
  it when `REQUIRE_AUTH_FOR_INGEST=true`. Feedback listing and review endpoints share the
  same gate.
- **SSRF protection (downloads):** `utils/security.validate_download_url` resolves DNS and
  blocks private/loopback/link-local/reserved IPs and cloud-metadata endpoints; the
  downloader sets `allow_redirects=False`; `ALLOWED_HOSTS` is an explicit allowlist.
- **Path-traversal / file-inclusion guard (ingest):** `ingest/policies._validate_ingest_path`
  resolves symlinks and confines every file the pipeline opens (hashing + loaders) to the
  system temp dir or `INGEST_INCOMING_DIR` before any read.
- **Guardrails:** input prompt-injection/jailbreak blocking (→ HTTP 400) and output
  PII-masking + answer length cap (config-toggleable, dependency-free, deterministic).
- **Groundedness gate:** answers are verified against retrieved chunks; in strict mode an
  unsupported answer is converted to a refusal (anti-hallucination backstop).
- **Rate limiting:** per-IP sliding window in Redis, proxy-aware (`TRUSTED_PROXIES`,
  `X-Forwarded-For`/`X-Real-IP`), with `X-RateLimit-*` and `Retry-After` headers.
- **CORS:** default `[]` (no cross-origin); operators must opt in explicitly.
- **Transport-layer dependency hygiene:** `h11>=0.16.0` pinned (request-smuggling defense).
- **Container hardening:** the Docker image runs as a non-root `appuser` (least privilege).
- **Error model:** RFC 9457 `application/problem+json`; 5xx responses never leak internal
  detail (logged server-side with a correlation id).
- **Observability:** every request carries an `X-Correlation-Id` propagated through logs.
- **Supply chain:** CI runs `bandit`, `pip-audit`, and `ruff`; the test suite is hermetic
  (no live network) with a coverage gate.

See `PTD.md` (§10 Security model) and `README.md` for full details.

---

## Known Issues & Residual Risk

### 1. `chromadb` 1.5.9 — CVE-2026-45829 (Critical, unpatched upstream)

A pre-authentication code-injection vulnerability affects ChromaDB **server** mode
(`/api/v2/.../collections` with `trust_remote_code=true`).

- **Status:** no upstream-fixed release is available at this time.
- **Exposure here:** this project uses ChromaDB in **embedded (in-process) mode**, not as a
  network server, so the vulnerable server endpoint is **not exposed**.
- **Mitigations:** do **not** run or expose the Chroma server API on the network; keep the
  store embedded. The CI `pip-audit` step explicitly `--ignore-vuln`s this CVE with a note
  to remove the ignore once a patched release ships.
- **Action:** tracked; upgrade `chromadb` as soon as a fixed version is released.

### 2. `/chat` is unauthenticated by default

`X-User-Id` is validated and namespaced for memory isolation, but it is **not**
authentication. If conversation content is sensitive, place an authenticating gateway in
front of the service (or extend `middlewares/auth.py`).

### 3. SSRF guard has a TOCTOU window

`validate_download_url` resolves DNS at check time; the subsequent request re-resolves.
Combined with `allow_redirects=False` this is a strong mitigation, **not airtight** —
pinning the validated IP for the connection would close the residual window.

### 4. Rate limiter fails open

If Redis is unavailable, requests are allowed (availability over strict enforcement). Pair
with alerting on Redis loss.

### 5. Guardrails are heuristic

Tuned for precision; novel prompt-injection phrasings may pass, and streaming PII masking
applies to the persisted answer, not tokens already streamed. Treat as one defense layer.

---

## Static Analysis (SAST) Findings & Dispositions

| Finding | Location | Disposition |
|---------|----------|-------------|
| Potential SSRF via user-controlled HTTP request | ingest downloader (`ingest/policies._download_file`) | **Mitigated.** Guarded by `validate_download_url` (DNS-aware private/metadata-IP blocking), `allow_redirects=False`, and the `ALLOWED_HOSTS` allowlist. The scanner cannot see these cross-function mitigations. |
| Potential file-inclusion via `open()` | `ingest/loaders.py`, `ingest/policies._file_hash` | **Mitigated.** All ingest paths are server-created temp/staged files; `_validate_ingest_path` (called at the `_run_ingest` chokepoint) resolves symlinks and confines reads to the system temp dir / `INGEST_INCOMING_DIR`. |
| Container runs as root | `Dockerfile` | **Fixed.** Image now runs as non-root `appuser` (uid 10001); runtime dirs are pre-created and owned by it. |

These dispositions are recorded so reviewers can mark the corresponding dashboard alerts
resolved with justification when the scanner does not auto-trace the mitigations.

---

## Dependency Security

- **CI gates:** `pip-audit` (on `requirements.txt`) and `bandit` (High/High) run on every
  push/PR; `ruff` enforces lint/format.
- **Embeddings:** the default local embedding path (FastEmbed / ONNX) is chosen to avoid
  `torch`-related CVEs; HuggingFace/`sentence-transformers` (and thus `torch`) are kept
  **out** of the production requirements and remain opt-in.
- **Recent fixes (v2.4.0):**
  - `pypdf` 6.11.0 → **6.12.0** (PDF-parsing DoS: AIKIDO-2026-10938 / -10937).
  - Pinned **`h11>=0.16.0`** (request smuggling, CVE-2025-43859; transitive via uvicorn/httpx).
- **Pinning policy:** runtime dependencies are version-pinned for reproducibility; security
  floors (`>=`) are used where a transitive dependency needs a minimum safe version.

---

## Hardening Checklist for Deployers

Before exposing this service to untrusted traffic:

- [ ] Set a strong `API_KEY` and `REQUIRE_AUTH_FOR_INGEST=true`.
- [ ] Set explicit `CORS_ORIGINS` (never `["*"]` in production).
- [ ] Configure `ALLOWED_HOSTS` to an allowlist (avoid `["*"]` if you accept ingest URLs).
- [ ] Set `TRUSTED_PROXIES` to your load-balancer CIDRs so rate limiting sees real client IPs.
- [ ] Put an authenticating gateway in front of `/chat` if conversations are sensitive.
- [ ] Keep ChromaDB **embedded** — do not expose the Chroma server API on the network.
- [ ] Run the container as the provided **non-root** user; mount writable volumes for
      `logs/`, `chroma_db/`, and (queue mode) `ingest_incoming/`.
- [ ] Use `INGEST_MODE=queue` with the worker for durable, retryable ingestion at scale.
- [ ] Set `LOG_FORMAT=json` and ship logs (with correlation IDs) to your aggregator.
- [ ] Watch Redis availability (the rate limiter fails open on outage).

---

_This file is a point-in-time summary. For change history see `CHANGELOG.md`; for the full
technical security model see `PTD.md`._
