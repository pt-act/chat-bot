# Tasks: OpenDataLoader Full Leverage

## Overview

**Total task groups**: 10  
**Total tasks**: 46 subtasks  
**Iteration estimate**: 24 iterations sequential · 14–16 iterations with 2 developers (parallel tracks)  
**Critical path**: Group 1 → Group 2 → Group 3 → Group 4 → Group 5 → Group 6 → Group 9

---

## Dependency Graph

```
Group 1 (Foundation)
  ↓
Group 2 (Adapter + Markdown)           ← TRACK 1 GATE
  ↓                    ↘
Group 3 (Tree Walker)   Group 7 (Hybrid infra)
  ↓                          ↓
Group 4 (Hierarchical    Group 8 (Enrichment)
          chunks)
  ↓
Group 5 (Retrieval)     ← depends on 4
  ↓
Group 6 (Citations +
          API)          ← depends on 5
  ↓
Group 9 (Frontend)      ← depends on 6

Group 10 (Testing + Eval)  ← depends on 2, 4, 5
Group 11 (Obs + Docs)      ← depends on 2, 7, 10
```

---

## Parallelization Strategy (2 developers)

| Developer A | Developer B |
|-------------|-------------|
| Groups 1 → 2 → 3 → 4 → 5 → 6 | Group 2 done → Groups 7 → 8 |
| Group 10 (eval) alongside Group 5 | Group 9 (frontend) after Group 6 |
| Group 11 (docs) last | — |

**Efficiency gain**: ~35% (14–16 iterations vs 24 sequential)

---

## Task Status Legend
- `[ ]` not_started
- `[~]` in_progress
- `[x]` completed
- `[-]` blocked

---

## Group 1 — Foundation: Parser Abstraction + Preflight

**Depends on**: nothing  
**Blocks**: Group 2  
**Estimate**: 2 iterations

### Implementation Tasks
- [ ] 1.1 Add `ODL_*` config env vars to `config.py:Settings` with Pydantic validators
  - `ODL_FORMAT=json,markdown` → `str`
  - `ODL_READING_ORDER=xycut` → `str`
  - `ODL_USE_STRUCT_TREE=false` → `bool`
  - `ODL_INCLUDE_HEADER_FOOTER=false` → `bool`
  - `ODL_HYBRID=` → `str | None`
  - `ODL_HYBRID_MODE=auto` → `Literal["auto","full"]`
  - `ODL_HYBRID_URL=` → `str | None`
  - `ODL_HYBRID_FALLBACK=false` → `bool`
  - `ODL_ENRICH_FORMULA=false` → `bool`
  - `ODL_ENRICH_PICTURES=false` → `bool`
  - `PDF_PARSER_FALLBACK=true` → `bool`
  - `PDF_PARSER=` → `Literal["pypdf","opendataloader"] | None` (None = auto-detect)
- [ ] 1.2 Add `preflight_check() -> tuple[bool, str]` to new `ingest/pdf_preflight.py`
  - Checks `java -version`, verifies version ≥ 11
  - Checks `opendataloader_pdf` is importable
  - Checks `ODL_HYBRID_URL` is reachable when `ODL_HYBRID` is set
  - Returns `(ok: bool, reason: str)` — never raises
- [ ] 1.3 Refactor `ingest/loaders.py:load_documents()` to accept optional `parser` kwarg
  - Existing PyPDF path preserved as default/fallback
  - ODL branch stubbed (returns `[]`, raises `NotImplementedError`) until Group 2
- [ ] 1.4 Update `.env.example` and `PTD.md` with all new config fields

### Validation Tier 1 — Focused Tests
- [ ] 1.5 `test_preflight_java_missing`: mock `subprocess.run` to raise `FileNotFoundError` →
  preflight returns `(False, reason containing "Java")`)
- [ ] 1.6 `test_preflight_java_old`: mock `java -version` output as `1.8.0` → returns
  `(False, reason containing "Java 11")`
- [ ] 1.7 `test_preflight_ok`: mock valid Java 17 + importable package → returns `(True, "")`
- [ ] 1.8 `test_config_pdf_parser_default`: `PDF_PARSER=None`, Java present → active parser = ODL

### Validation Tier 2 — PBT
- [ ] 1.9 PBT: `∀ java_version_string: parse_java_version(s)` returns correct major version
  (arbitrary version string inputs — catches edge cases like `"openjdk 11.0.21"`, `"17.0.1"`,
  `"1.8.0_202"`)

### Security Readiness
- [ ] 1.10 Verify `preflight_check()` never logs or surfaces the PDF file path
- [ ] 1.11 Verify config validators reject `PDF_PARSER=arbitrary_string` with clear error

---

## Group 2 — ODL Adapter + Markdown Fast Win (Track 1 Gate)

**Depends on**: Group 1  
**Blocks**: Groups 3, 7  
**Estimate**: 3 iterations

### Implementation Tasks
- [ ] 2.1 Create `ingest/pdf_opendataloader.py` with `load_pdf_odl(file_path, settings) -> list[Document]`
  - Calls `preflight_check()` — raises `RuntimeError` with reason on failure
  - Creates `tempfile.mkdtemp()` as `output_dir`
  - Calls `opendataloader_pdf.convert(input_path=file_path, output_dir=tmp, format="markdown", quiet=True, ...)`
  - Reads `{tmp}/{stem}.md` → splits into `Document` objects via existing `RecursiveCharacterTextSplitter`
  - Always cleans up `tmp` in `finally` block
  - Returns `list[Document]` with `metadata={"page": 0, "parser": "opendataloader"}`
  - On any exception: if `PDF_PARSER_FALLBACK=true`, log warning and call `PyPDFLoader(file_path).load()`
    with `metadata["parser"]="pypdf"` and `metadata["fallback_used"]=True`
- [ ] 2.2 Wire `load_documents()` dispatcher in `ingest/loaders.py`:
  - `.pdf` extension → `load_pdf_odl()` when Java present (or `PDF_PARSER=opendataloader`)
  - `.pdf` extension → `PyPDFLoader` when `PDF_PARSER=pypdf` or Java absent
- [ ] 2.3 Extend `ingest/policies.py:_persist_ingest_status()` to write FR8 fields
  (`parser`, `fallback_used`, `page_count`, `element_count`, `parser_mode`) from
  chunk metadata or a returned diagnostics dict
- [ ] 2.4 Add `page_count` extraction from Markdown line count heuristic (Track 1 approximation;
  replaced by JSON `"number of pages"` in Group 3)

### Validation Tier 1 — Focused Tests
- [ ] 2.5 `test_track1_e2e`: use a real small PDF (fixture) → `load_pdf_odl()` returns
  `list[Document]` where at least one `page_content` contains a `|` (Markdown table pipe)
- [ ] 2.6 `test_fallback_on_odl_failure`: mock `convert()` to raise `RuntimeError` →
  `PDF_PARSER_FALLBACK=true` → returns PyPDF documents with `fallback_used=True` in metadata
- [ ] 2.7 `test_fallback_disabled`: mock `convert()` to raise → `PDF_PARSER_FALLBACK=false`
  → `load_pdf_odl()` raises, ingest status shows `status=failed`
- [ ] 2.8 `test_temp_dir_cleaned_on_success`: after successful convert, `tmp_dir` does not exist
- [ ] 2.9 `test_temp_dir_cleaned_on_failure`: mock convert to raise → `tmp_dir` does not exist

### Validation Tier 2 — PBT
- [ ] 2.10 PBT: `∀ successful convert call: os.path.exists(temp_dir) == False`
  (property: temp cleanup invariant holds regardless of file contents)
- [ ] 2.11 PBT: `∀ ODL failure with fallback_enabled=True: result documents have parser="pypdf"`
  (property: fallback invariant — all returned docs carry correct parser tag)

### Security Readiness
- [ ] 2.12 Verify `file_path` passed to `convert()` is output of `_validate_ingest_path()` only
- [ ] 2.13 Verify `output_dir` is always under `tempfile.gettempdir()`, never under
  `INGEST_INCOMING_DIR`
- [ ] 2.14 Verify error messages from ODL exceptions do not leak `output_dir` path to API response

---

## Group 3 — JSON Tree Walker + Section Propagation

**Depends on**: Group 2  
**Blocks**: Group 4  
**Estimate**: 3 iterations

### Implementation Tasks
- [ ] 3.1 Extend `pdf_opendataloader.py` with `walk_tree(doc: dict) -> list[OdlElement]`
  where `OdlElement` is a dataclass with snake_case attributes mapped from ODL JSON keys:
  - `"page number"` → `page_number`
  - `"bounding box"` → `bbox` (list[float])
  - `"heading level"` → `heading_level`
  - `"element type"` (from `"type"`) → `element_type`
  - `content: str` (extracted recursively from `kids` / `rows` / `list items`)
  - `section_title: str | None` (injected by walker)
  - `id_: int`, `page_end: int | None`
- [ ] 3.2 Implement section title propagation: walker maintains a `current_heading` state;
  every non-heading element receives `section_title = current_heading.content`
- [ ] 3.3 Implement `_extract_content(element: dict) -> str` recursive helper:
  - `heading` / `paragraph` / `caption` → `element["content"]`
  - `list` → recurse into `element["list items"]` → `element["content"]` of each
  - `table` → recurse into `element["rows"]` → `cells` → `element["kids"]`
  - `header` / `footer` → `""` unless `ODL_INCLUDE_HEADER_FOOTER=true`
  - `image` → `""` (no text content for RAG)
  - `formula` → `element.get("content", "")` (LaTeX string)
  - `picture` → `element.get("description", "")` (SmolVLM description)
- [ ] 3.4 Implement `merge_tables(elements: list[OdlElement]) -> list[OdlElement]`:
  - Detects tables where `next_table_id` is non-null
  - Chains contiguous table fragments into one logical element
  - Sets merged element's `page_end` to last fragment's `page_number`
  - Removes fragment elements from output list
- [ ] 3.5 Update `load_pdf_odl()` to call `convert(format="json,markdown", ...)` and run
  walker on the JSON output; use Markdown file for chunk `page_content` (not walker text output)

### Validation Tier 1 — Focused Tests
- [ ] 3.6 `test_walker_heading_propagation`: fixture JSON with H1 → paragraph → paragraph →
  H2 → paragraph → all paragraphs under H1 have `section_title=H1_text`; paragraph under H2
  has `section_title=H2_text`
- [ ] 3.7 `test_walker_table_extraction`: fixture JSON with 2-row table →
  `_extract_content()` returns non-empty string containing cell text
- [ ] 3.8 `test_table_merge`: fixture with `next_table_id` linking two tables on pages 3–4 →
  `merge_tables()` returns one element with `page_end=4`

### Validation Tier 2 — PBT
- [ ] 3.9 PBT: `∀ valid ODL JSON doc: walk_tree(doc)` produces no element with a missing
  or null `element_type` (tests against arbitrary JSON conforming to ODL schema)
- [ ] 3.10 PBT: `∀ valid ODL JSON doc with N heading elements: walk_tree(doc)` produces
  elements where every non-heading element's `section_title` equals the content of the
  most-recently-seen heading with lower or equal level (section propagation invariant)
- [ ] 3.11 PBT: `∀ element list with M table chains of total length L: merge_tables(elements)`
  returns exactly `len(elements) - (L - M)` elements (merger reduces count correctly)

### Security Readiness
- [ ] 3.12 Verify walker handles malformed / missing `"kids"` gracefully (no uncaught exception)
- [ ] 3.13 Verify `_extract_content()` does not execute or eval any string content

---

## Group 4 — Hierarchical Chunk Indexing

**Depends on**: Group 3  
**Blocks**: Group 5  
**Estimate**: 2 iterations

### Implementation Tasks
- [ ] 4.1 Add `build_hierarchical_chunks(elements: list[OdlElement], doc_id, file_name, ...)
  -> tuple[list[Document], list[Document]]` returning `(l1_chunks, l2_chunks)`:
  - **L1**: one `Document` per heading section, `page_content` = full section Markdown
    (heading + all element Markdown until next heading, respecting `chunk_size` max;
    oversized sections get recursive split), metadata `chunk_level=1`
  - **L2**: one `Document` per leaf element, `page_content` = element Markdown from ODL
    Markdown file slice (matched by page + bbox heuristic or direct walker content),
    metadata `chunk_level=2`, `parent_chunk_id = l1_chunk.metadata["chunk_hash"]`
- [ ] 4.2 Extend `_build_chunks()` in `policies.py` to branch:
  - PDF + ODL parser → `build_hierarchical_chunks()` → returns L1 + L2 combined list
  - Everything else → existing `RecursiveCharacterTextSplitter` path (unchanged)
- [ ] 4.3 Ensure `_sync_vectorstore()` and `_persist_ingest_status()` handle the combined
  L1+L2 chunk list correctly (dedup, hash, upsert logic unchanged)

### Validation Tier 1 — Focused Tests
- [ ] 4.4 `test_l1_l2_structure`: fixture ODL JSON with 2 sections, 3 paragraphs each →
  builder returns 2 L1 chunks and 6+ L2 chunks; all L2 `parent_chunk_id` values match
  an L1 `chunk_hash`
- [ ] 4.5 `test_oversized_l1_split`: fixture section with text > 800 chars → L1 chunk is
  split; each resulting chunk carries `chunk_level=1` and same `section_title`
- [ ] 4.6 `test_non_pdf_unchanged`: DOCX fixture → `_build_chunks()` uses existing splitter,
  no `chunk_level` field in output metadata

### Validation Tier 2 — PBT
- [ ] 4.7 PBT: `∀ L2 chunk produced by build_hierarchical_chunks(): chunk.metadata["parent_chunk_id"]`
  is present in the L1 chunk list produced for the same document (referential integrity)

### Security Readiness
- [ ] 4.8 Verify `parent_chunk_id` is a `chunk_hash` (MD5 of content), not a raw user value
- [ ] 4.9 Existing `_check_duplicate_content()` path unchanged (L1+L2 use same file hash key)

---

## Group 5 — Hierarchical Retrieval Strategy

**Depends on**: Group 4  
**Blocks**: Group 6  
**Estimate**: 3 iterations

### Implementation Tasks
- [ ] 5.1 Add `hierarchical_retrieve(vs, query, k, fetch_k) -> list[Document]` to
  `ingest/retrieval.py`:
  - Fetches top-`fetch_k` candidates from Chroma (both L1 and L2)
  - Applies element-type heuristics:
    - `TABLE_QUERY_TERMS = {"table","row","column","compare","vs","versus","list of"}`
    - `OVERVIEW_QUERY_TERMS = {"overview","summary","introduction","what is","about"}`
    - Boost table-typed chunks by adding them to front of candidate list when query
      contains table terms
    - Prefer L1 chunks when query contains overview terms
  - Context expansion: for each selected L2 chunk, if its L1 parent is not already in
    result set and the result set has fewer than `k` items, append L1 parent
  - Returns at most `k` documents
- [ ] 5.2 Add `"hierarchical"` case to `_select_documents()` in `retrieve_context.py`
- [ ] 5.3 Add `RETRIEVAL_STRATEGY=hierarchical` as valid value in `config.py`
- [ ] 5.4 Update `_snippet()` helper to prefer the first 200 chars after the first `\n`
  when chunk starts with a Markdown heading (avoids `# Title` as the entire snippet)

### Validation Tier 1 — Focused Tests
- [ ] 5.5 `test_table_query_boosts_table_chunks`: mock Chroma with mixed chunk types →
  query containing "table" returns table-typed chunks in top-k
- [ ] 5.6 `test_overview_query_prefers_l1`: query "overview of section 2" → L1 section
  chunk ranked above L2 paragraph chunks
- [ ] 5.7 `test_context_expansion`: mock L2 chunk with parent → expansion adds L1 parent
  when result set has room
- [ ] 5.8 `test_non_odl_chunks_unaffected`: Chroma returns legacy chunks (no `chunk_level`) →
  heuristics skip them, no KeyError

### Validation Tier 2 — PBT
- [ ] 5.9 PBT: `∀ query, result = hierarchical_retrieve(vs, query, k, fetch_k):
  len(result) <= k` (never returns more than requested)

### Security Readiness
- [ ] 5.10 Heuristic term matching is case-insensitive substring check, no regex on
  user input (no ReDoS risk)
- [ ] 5.11 `_select_documents()` strategy dispatch rejects unknown strategy values with
  clear error before any DB call

---

## Group 6 — Extended Citations + Per-Request API Override

**Depends on**: Group 5  
**Blocks**: Group 9  
**Estimate**: 2 iterations

### Implementation Tasks
- [ ] 6.1 Add four optional fields to `schemas/responses.py:Source`:
  `section`, `element_type`, `page_end`, `bbox` — all `None`-defaulting
- [ ] 6.2 Update `retrieve_context.py:_to_source()` to map new metadata fields:
  `meta.get("section_title")`, `meta.get("element_type")`, `meta.get("page_end")`,
  `meta.get("bbox")` — all fall through to `None` for non-ODL chunks
- [ ] 6.3 Update `schemas/ingest.py` to accept three new optional fields on both
  `IngestRequest` and upload form: `parser`, `hybrid_mode`, `pages` (FR9)
- [ ] 6.4 Thread `parser`, `hybrid_mode`, `pages` overrides through `process_policy()`,
  `process_uploaded()`, `_run_ingest()` → `load_pdf_odl()` call
- [ ] 6.5 Update OpenAPI schema (auto-generated from Pydantic — verify `fastapi` picks up
  new fields correctly; add docstrings to new fields)

### Validation Tier 1 — Focused Tests
- [ ] 6.6 `test_source_new_fields_present`: ODL PDF ingest → `ChatResponse.sources[0]`
  contains non-None `section` and `element_type`
- [ ] 6.7 `test_source_new_fields_absent_for_legacy`: non-ODL chunk → all new Source
  fields are `None`, no KeyError in `_to_source()`
- [ ] 6.8 `test_parser_override_pypdf`: request with `parser="pypdf"` even when Java
  present → ingest uses PyPDF, status shows `parser=pypdf`
- [ ] 6.9 `test_invalid_parser_value`: request with `parser="unknown"` → 422 response

### Security Readiness
- [ ] 6.10 `bbox` is stored as `list[float]` — validate it is a 4-element list of finite
  floats before writing to Redis/Chroma (guard against malformed ODL output)
- [ ] 6.11 `pages` override is passed as-is to `convert(pages=...)` — validate against
  pattern `^\d+(-\d+)?(,\d+(-\d+)?)*$` before subprocess call

---

## Group 7 — Hybrid Server Deployment

**Depends on**: Group 2  
**Blocks**: Group 8  
**Estimate**: 2 iterations

### Implementation Tasks
- [ ] 7.1 Add `odl-hybrid` service to `docker-compose.yml`:
  - Base: Python image with `opendataloader-pdf[hybrid]`
  - Command: `opendataloader-pdf-hybrid --port 5002`
  - Healthcheck: `GET http://localhost:5002/health` interval 30s, retries 3
  - Environment: `ODL_HYBRID_OCR_LANG`, `ODL_HYBRID_FORCE_OCR`, `ODL_HYBRID_DEVICE`
- [ ] 7.2 Add `odl-hybrid` service to `docker-compose.local.yml` and `docker-compose.test.yml`
  with `profiles: ["hybrid"]` so it only starts when explicitly enabled
- [ ] 7.3 Add `ODL_HYBRID_URL` env var defaulting to `http://odl-hybrid:5002` to `.env.example`
- [ ] 7.4 Add hybrid server reachability check to `preflight_check()` (Group 1.2 extension):
  `GET {ODL_HYBRID_URL}/health` with 3s timeout; if unreachable and `ODL_HYBRID_FALLBACK=false`
  → preflight returns `(False, "hybrid server unreachable")`
- [ ] 7.5 Pass `ODL_HYBRID_*` config values through `load_pdf_odl()` to `convert()` call

### Validation Tier 1 — Focused Tests
- [ ] 7.6 `test_hybrid_url_unreachable_fallback_enabled`: mock GET healthcheck to fail →
  `ODL_HYBRID_FALLBACK=true` → ingest proceeds with local Java, `parser_mode=local`
- [ ] 7.7 `test_hybrid_url_unreachable_fallback_disabled`: same mock → `ODL_HYBRID_FALLBACK=false`
  → ingest fails with clear reason
- [ ] 7.8 `test_hybrid_compose_profile`: `docker-compose.yml` without hybrid profile →
  `odl-hybrid` service not started (functional / compose config test)

### Security Readiness
- [ ] 7.9 `ODL_HYBRID_URL` validated as HTTP/HTTPS URL with no path traversal before use in
  healthcheck and passed to `convert(hybrid_url=...)`
- [ ] 7.10 Hybrid server binds to `0.0.0.0` inside container only; no external port exposed
  in `docker-compose.yml` by default

---

## Group 8 — Enrichment Support

**Depends on**: Group 7  
**Blocks**: Group 10 (partial)  
**Estimate**: 2 iterations

### Implementation Tasks
- [ ] 8.1 Extend `_extract_content()` (Group 3.3) to handle `formula` and `picture`
  element types from enriched JSON output
- [ ] 8.2 Add `ODL_ENRICH_FORMULA` and `ODL_ENRICH_PICTURES` config flags; when true,
  require `ODL_HYBRID_MODE=full` (enrichment requires full-page routing)
  — raise clear config error if `ODL_HYBRID_MODE=auto` with enrichment enabled
- [ ] 8.3 Ensure `element_type="formula"` and `element_type="picture"` L2 chunks are stored
  and retrieved correctly (no special handling needed — they follow the same L2 path)

### Validation Tier 1 — Focused Tests
- [ ] 8.4 `test_formula_chunk_stored`: fixture JSON with `formula` element →
  `build_hierarchical_chunks()` includes L2 chunk with `element_type=formula`,
  `page_content` contains LaTeX-like string
- [ ] 8.5 `test_enrichment_requires_full_mode`: `ODL_ENRICH_FORMULA=true` +
  `ODL_HYBRID_MODE=auto` → config validation raises `ValueError`

### Security Readiness
- [ ] 8.6 Formula content (LaTeX string) stored as raw text in ChromaDB — no execution path;
  verify it's never passed to a rendering context without sanitization in the API response

---

## Group 9 — Frontend: Citation Card Update

**Depends on**: Group 6  
**Blocks**: nothing  
**Estimate**: 1 iteration

### Implementation Tasks
- [ ] 9.1 Update TypeScript `Source` type (wherever it is defined in the web client) to
  add optional fields: `section?: string`, `element_type?: string`, `page_end?: number`,
  `bbox?: number[]`
- [ ] 9.2 Update citation card component to display when present:
  - Section title (below document label, lighter weight)
  - Element type badge (`table`, `formula`, etc.) when not `paragraph`
  - Page range (e.g. `pp. 3–4`) using `page` and `page_end`
  - Collapse `bbox` values into a `<details>` element (debug/advanced view)
- [ ] 9.3 Ensure citation card renders cleanly when all new fields are `null`/`undefined`
  (no empty labels, no broken layout)

### Validation Tier 1 — Focused Tests
- [ ] 9.4 Compile + typecheck passes (`tsc --noEmit`)
- [ ] 9.5 Snapshot test: citation card with all new fields populated → matches expected markup
- [ ] 9.6 Snapshot test: citation card with all new fields null → renders identically to
  current (no regression)

### Security Readiness
- [ ] 9.7 `section` and `element_type` values are rendered as text content, not injected as
  HTML — verify no XSS surface in citation card component
- [ ] 9.8 `bbox` values are floats — render as `toFixed(2)` strings only

---

## Group 10 — Testing + Regression Evaluation

**Depends on**: Groups 2, 4, 5  
**Blocks**: Group 11  
**Estimate**: 3 iterations

### Implementation Tasks
- [ ] 10.1 Add integration test fixtures:
  - `tests/fixtures/simple.pdf` — small text PDF with one table and two headings
  - `tests/fixtures/multipage_table.pdf` — PDF with a table spanning 2 pages
  - `tests/fixtures/scanned_mock.json` — mock ODL JSON output for scanned PDF test
    (avoids real hybrid server dependency in CI)
- [ ] 10.2 Integration test: `test_full_odl_ingest_pipeline` — PDF fixture →
  `process_uploaded()` → verify Chroma contains L1 + L2 chunks with correct metadata
- [ ] 10.3 Integration test: `test_hierarchical_retrieval_e2e` — ingest fixture PDF →
  query "show me the table" → verify table chunk is in top-k results
- [ ] 10.4 Integration test: `test_multipage_table_merged` — multipage table fixture →
  Chroma contains one merged table chunk spanning both pages
- [ ] 10.5 Eval harness: `eval/pdf_comparison.py` comparing PyPDF vs ODL-Markdown vs
  ODL-Hierarchical on `tests/fixtures/simple.pdf`:
  - Metrics: recall@3, citation accuracy (section present), table question correctness
  - Output: `eval/results/pdf_comparison.json`
- [ ] 10.6 Eval script outputs comparison summary; at least one metric improves for ODL
  paths vs PyPDF baseline (gate for merge readiness)

### Validation Tier 1 — Focused Tests
- [ ] 10.7 All existing ingest tests pass unchanged (non-PDF formats)
- [ ] 10.8 `test_legacy_chunks_no_regression`: retrieve from store with mixed ODL + non-ODL
  chunks → `_to_source()` returns valid `Source` for all without KeyError

### Security Readiness
- [ ] 10.9 Eval harness reads fixture PDFs only; no network calls in eval script
- [ ] 10.10 CI does not start hybrid server; scanned PDF tests use mocked ODL JSON output

---

## Group 11 — Observability + Documentation

**Depends on**: Groups 2, 7, 10  
**Blocks**: nothing  
**Estimate**: 1 iteration

### Implementation Tasks
- [ ] 11.1 Update `README.md`:
  - Java 11+ requirement
  - ODL setup and installation
  - Config env vars table (`ODL_*`)
  - When to enable hybrid mode
  - Fallback behaviour
- [ ] 11.2 Update `PTD.md`:
  - Tech stack section: add ODL, Java dependency
  - Components table: add `ingest/pdf_opendataloader.py`, `ingest/pdf_preflight.py`
  - Storage model: add L1/L2 chunk metadata fields
  - Retrieval section: add `hierarchical` strategy
- [ ] 11.3 Add operator troubleshooting guide `docs/odl-operator-guide.md`:
  - Java not found
  - Hybrid server not starting
  - Enrichment producing empty chunks
  - Falling back to PyPDF manually
- [ ] 11.4 Update `CHANGELOG.md` with Track 1, 2, 3 entries

### Validation Tier 1 — Focused Tests
- [ ] 11.5 Docs link check: all code references in README/PTD point to files that exist
  (simple grep-based CI check)

### Security Readiness
- [ ] 11.6 Operator guide explicitly warns against exposing `odl-hybrid` port externally
- [ ] 11.7 `ODL_HYBRID_URL` documentation notes it should never point to an untrusted host

---

## Acceptance Criteria Summary

| Milestone | Gate | Criteria |
|-----------|------|----------|
| Track 1 | Group 2 | PDF ingest produces Markdown chunks; table pipe characters present in `page_content`; `parser=opendataloader` in ingest status |
| Track 2 | Group 5 | L1+L2 chunks in Chroma; table query returns table chunk in top-3; `section` populated in Source citations |
| Track 3 | Group 7 | Hybrid service starts with `docker compose --profile hybrid up`; ODL uses hybrid URL; fallback respected |
| Eval | Group 10 | Eval harness shows at least one metric improvement for ODL vs PyPDF on fixture set |
| Full | Group 11 | All tests green; README and PTD updated; no non-PDF regression |

---

## Iteration Summary

| Group | Name | Iterations | Can parallel |
|-------|------|-----------|-------------|
| 1 | Foundation | 2 | No (first) |
| 2 | Adapter + Markdown | 3 | No |
| 3 | Tree Walker | 3 | No |
| 4 | Hierarchical chunks | 2 | No |
| 5 | Retrieval strategy | 3 | No |
| 6 | Citations + API | 2 | No |
| 7 | Hybrid infra | 2 | Parallel with 3+ |
| 8 | Enrichment | 2 | Parallel with 4+ |
| 9 | Frontend | 1 | Parallel with 5+ |
| 10 | Testing + eval | 3 | Parallel with 5 |
| 11 | Obs + docs | 1 | Last |
| **Total** | | **24 sequential** | **~15 with 2 devs** |
