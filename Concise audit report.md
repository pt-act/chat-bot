# Re-Audit: chat-bot — 2026-05-28

Re-evaluation of the 8 original findings against the current codebase. Changes since the original audit are noted.

---

## 1. ~~High~~ **Resolved — Graph node tests added**

- **Location:** `tests/test_graph_nodes.py` (11 tests), `tests/test_api.py` (16 tests), `tests/test_ingest.py` (16 tests)
- **Change since original:** **Fixed.** The original audit found only ingest tests. `test_api.py` now covers health, home, chat (success/failure/validation), ingest (success/failure/validation), and the custom validation error handler. `test_graph_nodes.py` now covers all 5 graph nodes in isolation with mocked Redis, LLM, and vectorstore. 43 tests total, all passing.
- **Remaining gap:** `RateLimitMiddleware` is still tested only indirectly through integration.
- **Remediation:** Add rate limiter test with a mock Redis counter.

---

## 2. High — `process_policy` is still a god function

- **Location:** `ingest/policies.py:164-218`
- **Change since original:** **Partially improved.** The function was decomposed into helpers (`_download_file`, `_file_hash`, `_chunk_hash`, `_check_duplicate_content`, `_build_chunks`, `_sync_vectorstore`, `_persist_ingest_status`) and the main body is now a thin orchestrator. But it's still a single 55-line function that owns the full lifecycle including error handling and cleanup.
- **Why it matters:** The function is easier to read now, but still hard to test individual steps in isolation (e.g., testing `_sync_vectorstore` without going through the full flow).
- **Remediation:** Consider extracting the try/except/finally orchestration into a class or making each helper independently testable with explicit parameter passing (not relying on Redis state side effects).

---

## 3. Medium — Import-time singletons persist

- **Location:** `services/chat_service.py:6`, `db/redis_client.py:7`, `config.py:49`
- **Change since original:** **Marginally improved.** The graph is now lazily initialized via `lru_cache(maxsize=1)` in `chat_service.py:6` instead of at import time. Redis and settings still use `@lru_cache` global singletons.
- **Why it matters:** `@lru_cache` makes dependency override in tests require `lru_cache.cache_clear()` or `patch` on the factory function — awkward but workable. The real cost is that `main.py:17` calls `get_settings()` at module level, which means settings load on import.
- **Remediation:** Move `settings = get_settings()` inside the `lifespan` function. Accept Redis/vectorstore as parameters to controllers via FastAPI `Depends`.

---

## 4. ~~Medium~~ **Resolved — Private Chroma internals wrapped in adapter**

- **Location:** `db/vector.py:21-57`, `ingest/policies.py:116-143`
- **Change since original:** **Fixed.** `VectorStoreRepository` now encapsulates all `_collection` access. `get_by_doc_id(doc_id)`, `delete_by_ids(ids)`, and `add_documents(docs)` are exposed as public methods. `ingest/policies.py` creates a `VectorStoreRepository` instance and uses it for all vectorstore operations. `tests/test_ingest.py` assertions also use the public adapter instead of touching `_collection` directly.
- **Why it matters:** `_collection` is an implementation detail of ChromaDB. A library upgrade could break these calls silently. The adapter localizes that risk to one module.
- **Remediation:** — resolved.

---

## 5. ~~Medium~~ **Resolved — Health checks now reflect dependency status**

- **Location:** `main.py:26-45`, `main.py:77-81`
- **Change since original:** **Fixed.** The lifespan handler tests Redis ping and Chroma similarity search, setting `_redis_ok`/`_chroma_ok` flags. The `/health` endpoint returns `"degraded"` when either dependency is down, with per-dependency status in the response. Tests in `test_api.py` verify all four states (all ok, redis down, chroma down, both down).

---

## 6. ~~Medium~~ **Partially resolved — CI exists, but lint is failing**

- **Location:** `.github/workflows/ci.yml`
- **Change since original:** **Fixed.** A GitHub Actions CI workflow now runs on push/PR to main: installs deps, runs `ruff check .`, runs `pytest -q`.
- **New issue:** `ruff check .` currently reports **40 errors** (14 unsorted imports, 14 missing newlines, 5 line-too-long, 4 unused imports, 1 unused variable, 1 deprecated `typing.List`). CI would fail on the lint step today.
- **Remediation:** Run `ruff check . --fix` (33 auto-fixable) and manually fix the remaining 7. Add a `ruff.toml` or `[tool.ruff]` config if stricter rules are desired.

---

## 7. ~~Medium~~ **Resolved — docker-compose.test.yml created, README updated**

- **Location:** `Dockerfile:18-23`, `docker-compose.yml`, `docker-compose.test.yml`, `README.md:463-471`
- **Change since original:** **Fixed.** A multi-stage build has a `test` target that installs `requirements-dev.txt`, `httpx`, and `ruff`. A new `docker-compose.test.yml` builds the `api` service with `target: test`, so pytest and all dev dependencies are available inside the container. The README now references `docker-compose -f docker-compose.test.yml exec api pytest`.
- **Remaining issue:** None.
- **Remediation:** — resolved.

---

## 8. Low — Code hygiene still needs cleanup

- **Location:** Multiple files
- **Change since original:** **Not addressed.** Ruff reports 40 lint violations:
  - `F401` unused imports: `services/chat_service.py:1` (`HumanMessage`), `tests/conftest.py:4` (`MagicMock`), `tests/test_api.py:1` (`MagicMock`), `graph/nodes/retrieve_context.py:2` (`re`)
  - `F841` unused variable: `tests/test_ingest.py:208` (`result_v1`)
  - `UP035`/`UP006` deprecated typing: `graph/state.py:1` (`typing.List`)
  - `E501` line too long: `config.py:9`, `ingest/policies.py:79,114,141,193`
  - `I001` unsorted imports: 14 files
  - `W292` missing trailing newline: 14 files
  - Dead code: `ingest_controller.py:66-67` defines `_ALL_DOCS_KEY`/`_CONTENT_HASHES_KEY` after they're referenced on lines 36/56 (works due to Python function-level scoping, but misleading)
- **Remediation:** `ruff check . --fix` handles 33 issues. Manual fixes for the 5 `E501` lines and the `F841`/`UP035` issues.

---

## Summary: Scorecard

| # | Finding | Original | Current | Delta |
|---|---|---------|----------|---------|-------|
| 1 | Test coverage narrow | High | Resolved | **Fixed** — 43 tests, graph nodes covered |
| 2 | process_policy god function | High | High | **Partial** — decomposed into helpers, still monolithic |
| 3 | Import-time singletons | Medium | Medium | **Marginal** — graph lazy, others still global |
| 4 | Private Chroma internals | Medium | Resolved | **Fixed** — VectorStoreRepository adapter added |
| 5 | Health checks misleading | Medium | Resolved | **Fixed** |
| 6 | No CI/CD | Medium | Medium | **CI added but lint failing** (40 errors) |
| 7 | Docker/test mismatch | Medium | Resolved | **Fixed** — docker-compose.test.yml + README updated |
| 8 | Code hygiene | Low | Low | **No change** — 40 ruff violations |

## Priority actions

1. **Run `ruff check . --fix`** then manually fix the 7 remaining issues — unblocks CI.
2. **Refactor `process_policy`** into a class or explicit parameter-passing for independent testability.
3. **Move `settings = get_settings()` inside `lifespan`** and accept Redis/vectorstore via FastAPI `Depends`.
