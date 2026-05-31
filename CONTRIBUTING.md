# Contributing to AI Chatbot Backend

Thank you for your interest in contributing. This guide covers setup, development workflow, code standards, and how to get your changes merged.

---

## Quick Start

1. **Fork** the repository and clone your fork
2. **Create a Conda environment** (or use Docker):
   ```bash
   conda create -n chat-bot python=3.10
   conda activate chat-bot
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
3. **Copy `.env.example` to `.env`** and fill in your API keys
4. **Run the test suite** before making changes:
   ```bash
   pytest                     # local
   docker-compose -f docker-compose.test.yml up --build -d && docker-compose -f docker-compose.test.yml exec api pytest   # Docker
   ```
5. **Run linting** to catch issues early:
   ```bash
   ruff check .
   ruff format --check .
   ```

---

## Development Workflow

### Branch Naming

- `feature/<name>` — new features
- `fix/<name>` — bug fixes
- `security/<name>` — security improvements
- `refactor/<name>` — code restructuring

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
feat(scope): add X support
fix(scope): resolve Y issue
security(scope): harden Z
refactor(scope): restructure W
chore: update dependencies
docs: add changelog
```

**Scope examples:** `graph`, `api`, `llm`, `embedding`, `security`, `ci`, `ingest`

### Before Submitting a PR

1. All tests pass: `pytest`
2. No lint issues: `ruff check .` and `ruff format --check .`
3. No security issues: `bandit -r . -x ./tests`
4. New code has tests — aim for the project's 95%+ coverage standard
5. No secrets committed — run `git secrets --scan` before pushing
6. Update `CHANGELOG.md` under `[Unreleased]` with your changes

---

## Code Standards

### Style

- **Formatter:** `ruff format` (line-length: 120, target: Python 3.10)
- **Linter:** `ruff check .` with rules E, F, W, I, UP
- **No `any` type** — use Pydantic v2 models for all API contracts
- **File limit:** 400 lines per component. Warn at 350. Decompose before hitting 400.

### Type Safety

- Pydantic v2 models for all request/response schemas (`schemas/`)
- Pydantic-Settings for configuration (`config.py`)
- No bare `except Exception:` — catch specific exception classes
- Config validators (`@model_validator`) for startup validation of required keys and values

### Architecture Patterns

- **Adapter pattern** for LLM and embedding providers — add new providers via `OPENAI_COMPATIBLE` set or native client branches in `utils/llm_adapter.py`
- **Registry pattern** for embedding models — add new models to `FASTEMBED_MODELS` dict in `utils/embedding_adapter.py` with `dim` and `description` metadata
- **Mode-specific functions** for prompt builders — each chat mode has its own builder in `prompts/answer.py` (`_build_strict_prompt`, `_build_open_prompt`, `_build_learning_prompt`)
- **Graph node pattern** — each LangGraph node is a standalone function in `graph/nodes/`, tested in isolation with mocked dependencies
- **FastAPI dependency injection** for auth — `require_api_key` in `middlewares/auth.py` enables testability via `dependency_overrides`

### Testing

- 178 tests, ~97% coverage (unit, API/contract, streaming, async-ingest, and an
  end-to-end graph integration test); hermetic via `fakeredis` + mocked boundaries
- Each provider, mode, and security control has dedicated test coverage
- Use `fakeredis` for Redis mocking, `MagicMock`/`patch` for external service mocking
- Test new features in isolation before integration
- Run `pytest -q --cov=. --cov-report=term-missing` to see coverage gaps

---

## Project Structure

```
chat-bot/
├── controllers/
│   ├── {chat,ingest}_controller.py  # Legacy /api routes (deprecated, back-compat)
│   └── v1/                          # Typed /api/v1 routes (chat + SSE stream, ingest)
├── middlewares/          # Auth, rate limiting, observability, problem+json errors, logging
├── db/                   # Redis (+ memory_key) and ChromaDB clients
├── graph/
│   ├── builder.py        # LangGraph pipeline (6 nodes + edges)
│   ├── state.py          # State TypedDict (chat_mode, best_score, lang, top_k, ...)
│   └── nodes/            # Individual graph nodes (one file per node)
├── ingest/               # Incremental ingestion (policies.py) + Redis key constants (keys.py)
├── prompts/
│   ├── answer.py         # 3 mode-specific prompt builders
│   └── summarize.py      # Conversation summarization prompt
├── schemas/              # Pydantic v2 models — chat, ingest, responses (envelopes + problem)
├── services/             # Business logic layer (conversation, stream_conversation, ingest)
├── utils/
│   ├── llm_adapter.py    # 14-provider LLM adapter with aliases
│   ├── embedding_adapter.py # 3-provider embedding adapter + FASTEMBED_MODELS registry
│   └── security.py       # SSRF protection (private IP/metadata + DNS-rebinding)
├── web/                  # Reference SPA (Vite + React + TS): streaming chat, RTL, a11y
├── docs/audit/           # Audit reports, patches, and tool evidence
├── tests/                # 178 tests, ~97% coverage
├── main.py               # App entrypoint, middleware wiring, health/ready endpoints
├── config.py             # Pydantic Settings with validators
├── pyproject.toml        # Ruff + pytest config
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # This file
├── PTD.md                # Project technical document
├── user_guidelines.md    # End-user / API-consumer guide
└── .env.example          # Configuration template with documentation
```

---

## Key Files for Common Tasks

| Task | Files to modify |
|------|----------------|
| Add a new LLM provider | `utils/llm_adapter.py`, `tests/test_adapters.py`, `config.py` (if new env vars needed), `.env.example`, `README.md` provider table |
| Add a new embedding model | `utils/embedding_adapter.py` (`FASTEMBED_MODELS` dict), `tests/test_adapters.py`, `.env.example`, `README.md` embedding table |
| Add a new chat mode | `prompts/answer.py`, `graph/nodes/retrieve_context.py`, `graph/nodes/generate_answer.py`, `config.py`, `tests/test_graph_nodes.py` |
| Add a new graph node | `graph/nodes/<name>.py`, `graph/builder.py`, `graph/state.py` (if new state fields), `tests/test_graph_nodes.py` |
| Add a new API endpoint | `controllers/`, `schemas/`, `services/`, `tests/test_api.py` or new test file |
| Add security controls | `utils/security.py` or `middlewares/`, `tests/test_security.py` or `tests/test_rate_limiter.py`, `README.md` security section |
| Add CI pipeline steps | `.github/workflows/ci.yml` |

---

## Security

### Mandatory Checks Before Every Commit

- `git secrets --scan` — prevents API keys from entering git
- No `.env` files committed (`.gitignore` blocks them)
- No `.venv/` committed (removed from git history in v2.0.0)

### Production Security Requirements

- `CORS_ORIGINS` must not contain `["*"]` — explicitly list allowed origins
- `API_KEY` must be set for production — `DELETE /ingest/{doc_id}` always requires auth
- `TRUSTED_PROXIES` must be configured when running behind nginx/Cloudflare
- `ALLOWED_HOSTS` controls which download URLs the ingest pipeline accepts

### Security Audit History

| Date | Score | Grade | Key Changes |
|------|-------|-------|-------------|
| 2026-05-28 (initial) | 72/100 | C+ | Identified 3 critical, 4 high, 5 medium, 5 low, 5 informational findings |
| 2026-05-28 (after elevation) | 95/100 | A+ | Fixed all critical/high findings, added auth, SSRF guard, proxy-aware rate limiting, CORS hardening, CI gates, structured logging, specific exception handling |

Full audit reports available in `audit_artifacts/AUDIT_REPORT.md` and `audit_artifacts/FINAL_AUDIT.md`.

---

## Fork History

This repository (`pt-act/chat-bot`) is a fork of `hasandeveloper/chat-bot` with significant enhancements:

| Version | Source | Changes |
|---------|--------|---------|
| v1.0.0 | hasandeveloper/chat-bot | Original: 3 LLM providers, strict mode only, basic security, 89% coverage |
| v2.0.0 | pt-act/chat-bot | Added: 14 providers, 3 chat modes, self-ingestion, full security elevation, 97% coverage, local deployment, observability, CI hardening |

Contributions to both the upstream and this fork are welcome. If you want your changes to reach the upstream repository, please also open a PR at `hasandeveloper/chat-bot`.

---

## Good First Contributions

- Add a new document loader (DOCX, TXT, HTML) in `ingest/`
- Add a two-phase review workflow for learning mode synthesized entries
- Add Guardrails integration
- Add RAGAS evaluation framework
- Add a new FastEmbed model to the registry in `utils/embedding_adapter.py`
- Improve test coverage for ingest controller endpoints
- Add OpenTelemetry tracing (currently using correlation IDs only)

---

## Questions?

Open an issue before starting large changes so we can discuss the approach first.