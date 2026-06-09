# Tasks: OpenDataLoader Full Leverage

## Overview

**Total task groups**: 11 — **ALL COMPLETE [x]**
**Total tasks**: 46 subtasks — **ALL COMPLETE [x]**
**Iteration estimate**: 24 iterations sequential · 14–16 iterations with 2 developers (parallel tracks)
**Critical path**: Group 1 → Group 2 → Group 3 → Group 4 → Group 5 → Group 6 → Group 9
**Completed**: 2026-06-06

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

## Group 1 — [x] Foundation: Parser Abstraction + Preflight

**Depends on**: nothing  
**Blocks**: Group 2  
**Estimate**: 2 iterations

### Implementation Tasks
- [x] 1.1 Add `ODL_*` config env vars to `config.py:Settings` with Pydantic validators
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
- [x] 1.2 Add `preflight_check() -> tuple[bool, str]` to new `ingest/pdf_preflight.py`
  - Checks `java -version`, verifies version ≥ 11
  - Checks `opendataloader_pdf` is importable
  - Checks `ODL_HYBRID_URL` is reachable when `ODL_HYBRID` is set
  - Returns `(ok: bool, reason: str)` — never raises
- [x] 1.3 Refactor `ingest/loaders.py:load_documents()` to accept optional `parser` kwarg
  - Existing PyPDF path preserved as default/fallback
  - ODL branch stubbed (returns `[]`, raises `NotImplementedError`) until Group 2
- [x] 1.4 Update `.env.example` and `PTD.md` with all new config fields

### Validation Tier 1 — Focused Tests
- [x] 1.5 `test_preflight_java_missing`: mock `subprocess.run` to raise `FileNotFoundError` →
  preflight returns `(False, reason containing "Java")`)
- [x] 1.6 `test_preflight_java_old`: mock `java -version` output as `1.8.0` → returns
  `(False, reason containing "Java 11")`
- [x] 1.7 `test_preflight_ok`: mock valid Java 17 + importable package → returns `(True, "")`
- [x] 1.8 `test_config_pdf_parser_default`: `PDF_PARSER=None`, Java present → active parser = ODL

### Validation Tier 2 — PBT
- [x] 1.9 PBT: `∀ java_version_string: parse_java_version(s)` returns correct major version
  (arbitrary version string inputs — catches edge cases like `"openjdk 11.0.21"`, `"17.0.1"`,
  `"1.8.0_202"`)

### Security Readiness
- [x] 1.10 Verify `preflight_check()` never logs or surfaces the PDF file path
- [x] 1.11 Verify config validators reject `PDF_PARSER=arbitrary_string` with clear error

---

## Group 2 — [x] ODL Adapter + Markdown Fast Win (Track 1 Gate)

**Depends on**: Group 1  
**Blocks**: Groups 3, 7  
**Estimate**: 3 iterations

### Implementation Tasks
- [x] 2.1 Create `ingest/pdf_opendataloader.py` with `load_pdf_odl(file_path, settings) -> tuple[list[Document], dict]`
  - Calls `preflight_check()` — raises `RuntimeError` with reason on failure
  - Creates `tempfile.mkdtemp()` as `output_dir`
  - Calls `opendataloader_pdf.convert(input_path=file_path, output_dir=tmp, format="markdown", quiet=True, ...)`
  - Reads `{tmp}/{stem}.md` → splits into `Document` objects via existing `RecursiveCharacterTextSplitter`
  - Always cleans up `tmp` in `finally` block
  - Returns `(list[Document], diagnostics)` with `metadata={"page": 0, "parser": "opendataloader"}`
  - On any exception: if `PDF_PARSER_FALLBACK=true`, log warning and call `PyPDFLoader(file_path).load()`
    with `metadata["parser"]="pypdf"` and `metadata["fallback_used"]=True`
- [x] 2.2 Wire `load_documents()` dispatcher in `ingest/loaders.py`:
  - `.pdf` extension → `load_pdf_odl()` when Java present (or `PDF_PARSER=opendataloader`)
  - `.pdf` extension → `PyPDFLoader` when `PDF_PARSER=pypdf` or Java absent
- [x] 2.3 Extend `ingest/policies.py:_persist_ingest_status()` to write FR8 fields
  (`parser`, `fallback_used`, `page_count`, `element_count`, `parser_mode`) from
  diagnostics dict returned by `_build_chunks()`
- [x] 2.4 Add `page_count` extraction from Markdown `---` page-separator heuristic (Track 1 approximation;
  replaced by JSON `"number of pages"` in Group 3)

### Validation Tier 1 — Focused Tests
- [x] 2.5 `test_track1_e2e`: marked skip (requires real Java + ODL); structure verified
- [x] 2.6 `test_fallback_on_odl_failure`: mock `convert()` to raise `RuntimeError` →
  `PDF_PARSER_FALLBACK=true` → returns PyPDF documents with `fallback_used=True` in metadata
- [x] 2.7 `test_fallback_disabled`: mock `convert()` to raise → `PDF_PARSER_FALLBACK=false`
  → `load_pdf_odl()` raises
- [x] 2.8 `test_temp_dir_cleaned_on_success`: after successful convert, `tmp_dir` does not exist
- [x] 2.9 `test_temp_dir_cleaned_on_failure`: mock convert to raise → `tmp_dir` does not exist

### Validation Tier 2 — PBT
- [x] 2.10 PBT: `∀ successful convert call: os.path.exists(temp_dir) == False`
  (property: temp cleanup invariant holds regardless of file contents)
- [x] 2.11 PBT: `∀ ODL failure with fallback_enabled=True: result documents have parser="pypdf"`
  (property: fallback invariant — all returned docs carry correct parser tag)

### Security Readiness
- [x] 2.12 Verify `file_path` passed to `convert()` is output of `_validate_ingest_path()` only
- [x] 2.13 Verify `output_dir` is always under `tempfile.gettempdir()`, never under
  `INGEST_INCOMING_DIR` — tested in `test_output_dir_under_tempdir`
- [x] 2.14 Verify error messages from ODL exceptions do not leak `output_dir` path to API response
  — tested in `test_error_message_does_not_leak_output_dir`

---

## Group 3 — [x] JSON Tree Walker + Section Propagation

**Depends on**: Group 2  
**Blocks**: Group 4  
**Estimate**: 3 iterations

### Implementation Tasks
- [x] 3.1 Add `OdlElement` dataclass and `walk_tree(doc, include_header_footer) -> list[OdlElement]`
  - All ODL JSON keys mapped to snake_case attributes
  - `section_title` injected by walker during traversal
- [x] 3.2 Section title propagation — `current_heading_text` state variable in walker
- [x] 3.3 `_extract_content(element, include_header_footer) -> str` — handles all element types
- [x] 3.4 `merge_tables(elements) -> list[OdlElement]` — forward-chain merging
- [x] 3.5 `load_pdf_odl()` upgraded to `format=settings.odl_format` ("json,markdown");
  walks JSON with `walk_tree()` + `merge_tables()`; uses MD for chunk content;
  returns `(chunks, elements, diagnostics)` 3-tuple; accurate page_count from JSON

### Validation Tier 1 — Focused Tests
- [x] 3.6 `test_walker_heading_propagation` — in `tests/test_odl_walker.py`
- [x] 3.7 `test_walker_table_extraction` — in `tests/test_odl_walker.py`
- [x] 3.8 `test_table_merge` — in `tests/test_odl_walker.py`

### Validation Tier 2 — PBT
- [x] 3.9 PBT: `element_type` never null — `test_pbt_walk_tree_no_null_element_type`
- [x] 3.10 PBT: section propagation invariant — `test_pbt_section_propagation_invariant`
- [x] 3.11 PBT: merger count formula — `test_pbt_merge_tables_count_formula`

### Security Readiness
- [x] 3.12 `TestWalkerSecurity` — missing/None kids, malformed tables/lists, deep nesting
- [x] 3.13 `test_extract_content_does_not_eval_content` — content treated as plain string

---

## Group 4 — [x] Hierarchical Chunk Indexing

**Depends on**: Group 3  
**Blocks**: Group 5  
**Estimate**: 2 iterations

### Implementation Tasks
- [x] 4.1 `build_hierarchical_chunks(elements, chunk_size, chunk_overlap) -> (l1, l2)`
  - L1: heading + body content, oversized sections split; `chunk_level=1`, pre-computed `chunk_hash`
  - L2: per-element content; `chunk_level=2`, `parent_chunk_id` = first L1 hash of section
  - `_clean_odl_text` + `_odl_chunk_hash` mirror `policies._clean_text/_chunk_hash` for hash consistency
- [x] 4.2 `_build_chunks()` branching — ODL path calls `build_hierarchical_chunks(odl_elements)`;
  `raw_chunks = l1 + l2`; non-PDF/non-ODL path unchanged
- [x] 4.3 `_ODL_PASSTHROUGH_KEYS` copies L1/L2 metadata through the loop;
  `_sync_vectorstore` and `_persist_ingest_status` require no changes (dedup/hash/upsert unchanged)

### Validation Tier 1 — Focused Tests
- [x] 4.4 `TestL1L2Structure` — 2 sections × 3 paragraphs → 2 L1 + 6 L2; parent links valid
- [x] 4.5 `TestOversizedL1Split` — >300 char content → multi-part L1; all parts `chunk_level=1`
- [x] 4.6 `TestNonPdfUnchanged` — DOCX and TXT paths produce no `chunk_level` in metadata

### Validation Tier 2 — PBT
- [x] 4.7 `test_pbt_l2_parent_chunk_id_always_resolvable` — arbitrary section counts and sizes

### Security Readiness
- [x] 4.8 `test_parent_chunk_id_is_md5_hex` — 32-char hex pattern; user content not in hash
- [x] 4.9 `test_check_duplicate_content_path_unchanged` — file-hash dedup unaffected

---

## Group 5 — [x] Hierarchical Retrieval Strategy

**Depends on**: Group 4  
**Blocks**: Group 6  
**Estimate**: 3 iterations

### Implementation Tasks
- [x] 5.1 `hierarchical_retrieve()` in `ingest/retrieval.py`
  - `TABLE_QUERY_TERMS` / `OVERVIEW_QUERY_TERMS` frozensets — plain strings, no regex
  - Heuristic reordering: table boost or L1 boost applied to similarity-ordered candidates
  - Inline L2→L1 context expansion: parent appended immediately after L2 when in pool and room < k
  - Returns `results[:k]`
- [x] 5.2 `"hierarchical"` case added to `_select_documents()` in `retrieve_context.py`;
  `_VALID_STRATEGIES` frozenset + guard raises `ValueError` before any DB call
- [x] 5.3 `check_retrieval_strategy` model_validator added to `config.py`;
  rejects any value outside `{"mmr","hybrid","hybrid_rerank","hierarchical"}`
- [x] 5.4 `_snippet()` updated — skips `# Title` heading line for L1 chunks

### Validation Tier 1 — Focused Tests
- [x] 5.5 `TestTableQueryBoost` — table chunk moved to front; all TABLE terms tested; case-insensitive
- [x] 5.6 `TestOverviewQueryPrefersL1` — L1 first for overview terms; neutral query preserves order
- [x] 5.7 `TestContextExpansion` — parent appended, dedup, missing-parent safe, k-limit respected
- [x] 5.8 `TestNonOdlChunksUnaffected` — legacy chunks, mixed ODL/legacy, no KeyError

### Validation Tier 2 — PBT
- [x] 5.9 `test_pbt_result_count_never_exceeds_k` — arbitrary docs, queries, k values

### Security Readiness
- [x] 5.10 `TestTermMatchingSecurity` — terms are plain strings; injection queries don't crash
- [x] 5.11 `TestStrategyDispatchSecurity` — unknown strategy raises before DB call; config validator

---

## Group 6 — [x] Extended Citations + Per-Request API Override

**Depends on**: Group 5  
**Blocks**: Group 9  
**Estimate**: 2 iterations

### Implementation Tasks
- [x] 6.1 `schemas/responses.py:Source` — 4 new optional fields: `section`, `element_type`, `page_end`, `bbox`
- [x] 6.2 `_to_source()` maps `section_title`→`section`, `element_type`, `page_end`, `bbox`; None for non-ODL
- [x] 6.3 `schemas/ingest.py:IngestRequest` — `parser` (Literal), `hybrid_mode` (Literal), `pages` (str+validator)
- [x] 6.4 Full threading: controllers → services → policies (_run_ingest/_build_chunks) → load_pdf_odl;
  queue.py also threads overrides through durable jobs
- [x] 6.5 OpenAPI auto-updated via Pydantic Field docstrings on all new fields

### Validation Tier 1 — Focused Tests
- [x] 6.6 `TestToSourceNewFields.test_odl_chunk_maps_all_four_fields`
- [x] 6.7 `TestToSourceNewFields.test_legacy_chunk_new_fields_are_none`
- [x] 6.8 `TestParserOverride.test_pypdf_override_in_build_chunks`
- [x] 6.9 `TestIngestRequestValidation.test_invalid_parser_raises` + `TestApiParserValidation.test_invalid_parser_returns_422`

### Security Readiness
- [x] 6.10 `_validate_bbox()` — 4-element finite-float check; wired into `build_hierarchical_chunks`
- [x] 6.11 `_PAGES_RE` pattern validated in `load_pdf_odl()` before convert(); also in `IngestRequest.validate_pages_format` and upload controller

---

## Group 7 — [x] Hybrid Server Deployment

**Depends on**: Group 2  
**Blocks**: Group 8  
**Estimate**: 2 iterations

### Implementation Tasks
- [x] 7.1 `odl-hybrid` service added to `docker-compose.yml` with `profiles: ["hybrid"]`,
  `python:3.12-slim` image, `opendataloader-pdf-hybrid --port 5002`, healthcheck on `/health`
- [x] 7.2 Same service added to `docker-compose.local.yml` and `docker-compose.test.yml`
  with `profiles: ["hybrid"]`
- [x] 7.3 `.env.example` ODL hybrid section updated with default URL `http://odl-hybrid:5002`
  and inline docs for all hybrid/enrichment vars
- [x] 7.4 `preflight_check()` already calls `_hybrid_reachable()` from Group 1; now appends
  `/health` to the URL and validates HTTP/HTTPS scheme before any network call
- [x] 7.5 `load_pdf_odl()` now does its own `_hybrid_reachable()` check per call so it can
  correctly strip hybrid params when server is unreachable + fallback enabled

### Validation Tier 1 — Focused Tests
- [x] 7.6 `TestHybridFallbackEnabled` — mock unreachable + fallback=true → parser_mode=local,
  no hybrid key in convert() kwargs
- [x] 7.7 `TestHybridFallbackDisabled` — mock unreachable + fallback=false → RuntimeError,
  convert() not called
- [x] 7.8 `TestComposeProfile` — YAML parse of all three compose files; verifies profile,
  healthcheck, and service presence

### Security Readiness
- [x] 7.9 `TestHybridUrlValidation` — ftp/file/credential URLs rejected before network call;
  health endpoint path verified; trailing-slash handling tested
- [x] 7.10 `TestNoExternalPort` — all three compose files checked for absent `ports` on odl-hybrid

---

## Group 8 — [x] Enrichment Support

**Depends on**: Group 7  
**Blocks**: Group 10 (partial)  
**Estimate**: 2 iterations

### Implementation Tasks
- [x] 8.1 `_extract_content()` handles `formula` (`element["content"]`) and `picture`
  (`element["description"]`) — implemented in Group 3, confirmed by tests
- [x] 8.2 `ODL_ENRICH_FORMULA` / `ODL_ENRICH_PICTURES` config flags with
  `check_odl_enrichment` validator — implemented in Group 1
- [x] 8.3 Formula/picture elements follow the same L2 path: `walk_tree` → `OdlElement`
  → `build_hierarchical_chunks` → L2 chunk with correct `element_type` and content

### Validation Tier 1 — Focused Tests
- [x] 8.4 `TestFormulaChunkStored` — element_type, LaTeX content, parent_chunk_id,
  chunk_level; full walk_tree → build_hierarchical_chunks pipeline for both formula and picture
- [x] 8.5 `TestEnrichmentRequiresFullMode` — config raises for auto mode; passes for full;
  `enrich_formula`/`enrich_pictures` passed to convert() only when hybrid active

### Security Readiness
- [x] 8.6 `TestFormulaContentSecurity` — snippet is plain str, not executed; callable
  metadata check; dangerous strings stored verbatim and never evaluated

---

## Group 9 — [x] Frontend: Citation Card Update

**Depends on**: Group 6  
**Blocks**: nothing  
**Estimate**: 1 iteration

### Implementation Tasks
- [x] 9.1 `web/src/types.ts:Source` — 4 new optional nullable fields added
- [x] 9.2 `web/src/components/CitationCards.tsx` updated:
  - `citation-section` div below label (hidden when null)
  - `citation-element-type` badge (hidden for "paragraph" and null)
  - Page range: `pp. N–M` for multi-page, `p. N` for single
  - `citation-bbox` collapsible `<details>` with `toFixed(2)` values
- [x] 9.3 All new fields guard with `!= null` — null/undefined renders nothing

### Validation Tier 1 — Focused Tests
- [x] 9.4 `bun run typecheck` (`tsc -b --noEmit`) passes with zero errors
- [x] 9.5 `CitationCards.test.tsx` — ODL fields populated: section title, element badge,
  multi-page range, bbox details, XSS strings as literal text
- [x] 9.6 Legacy source (new fields absent) — existing label/page/score/snippet unchanged,
  no new elements rendered

### Security Readiness
- [x] 9.7 XSS injection test verifies `<script>` and `<img onerror>` appear as text, no
  DOM elements created (React JSX text content escaping)
- [x] 9.8 `bbox` toFixed(2) tests; malformed bbox (length ≠ 4) silently omitted

---

## Group 10 — [x] Testing + Regression Evaluation

**Depends on**: Groups 2, 4, 5  
**Blocks**: Group 11  
**Estimate**: 3 iterations

### Implementation Tasks
- [x] 10.1 Fixtures in `tests/fixtures/`:
  - `simple_mock.json` + `simple_mock.md` — 2-section doc with pricing table
  - `multipage_table_mock.json` — table spanning pages 3–4 via `next table id`
  - `scanned_mock.json` — invoice doc (avoids hybrid server in CI)
  - PDF bytes generated via `_make_simple_pdf_bytes()` / `_make_multipage_table_pdf_bytes()`
    session-scoped fixtures in `conftest.py`
- [x] 10.2 `TestFullOdlIngestPipeline` (4 tests) — mocked convert → `_build_chunks` →
  L1+L2 present, L1 has section metadata, L2 has parent links, table L2 chunk with pricing
- [x] 10.3 `TestHierarchicalRetrievalE2E` (3 tests) — fixture JSON → Chroma →
  table query surfaces table chunk, overview query surfaces L1 chunk
- [x] 10.4 `TestMultipageTableMerged` (5 tests) — two linked tables merge to one;
  page_end=4; both pages' content in merged element; scanned_mock processes without hybrid
- [x] 10.5 `eval/pdf_comparison.py` — standalone script + `tests/test_odl_eval.py` (14 tests);
  offline metrics: table_content_quality, section_metadata_coverage, table_element_present;
  output written to `eval/results/pdf_comparison.json`
- [x] 10.6 Gate test `TestEvalGate.test_gate_passes` — ODL-Markdown table_content_quality > 0,
  ODL-Hierarchical section_metadata_coverage > 0 and table_element_present=1.0

### Validation Tier 1 — Focused Tests
- [x] 10.7 `TestNonPdfIngestUnchanged` — TXT and DOCX produce no chunk_level/element_type
- [x] 10.8 `TestLegacyChunksNoRegression` — mixed ODL+legacy+synthesized chunks all return
  valid Source; _dedup works; no KeyError

### Security Readiness
- [x] 10.9 `test_eval_makes_no_network_calls` — monkeypatches urlopen and confirms no access
- [x] 10.10 `test_scanned_mock_json_processes_without_hybrid` — all fixture JSON tests run
  without any network access to the hybrid sidecar

---

## Group 11 — [x] Observability + Documentation

**Depends on**: Groups 2, 7, 10  
**Blocks**: nothing  
**Estimate**: 1 iteration

### Implementation Tasks
- [x] 11.1 `README.md` — new "OpenDataLoader PDF Parser" section with: Java 11+ requirement,
  installation, ODL config vars table, auto-detect/fallback behaviour, hybrid mode docker-compose
  setup, enrichment flags, per-request parser override, security note, link to operator guide
- [x] 11.2 `PTD.md` — storage model extended with L1/L2 chunk metadata fields; config table
  extended with ODL_* vars and `hierarchical` retrieval strategy
- [x] 11.3 `docs/odl-operator-guide.md` — new file: Java not found, ODL not installed,
  hybrid server not starting, enrichment empty chunks, manual PyPDF fallback, hierarchical
  retrieval not activating, full env var reference table
- [x] 11.4 `CHANGELOG.md` — v2.5.0 entry with Track 1/2/3 sections (Groups 1–11 summary)

### Validation Tier 1 — Focused Tests
- [x] 11.5 `tests/test_odl_docs.py` — 14 tests: backtick path refs in README/PTD/guide resolve
  to real files (scoped to project directories); ODL components in PTD; config vars present;
  L1/L2 fields in storage model; Java requirement in README; CHANGELOG has ODL entry

### Security Readiness
- [x] 11.6 `TestOperatorGuideSecurity.test_warns_against_external_port` — operator guide warns
  explicitly against exposing `odl-hybrid` container port externally
- [x] 11.7 `test_warns_about_hybrid_url_trust` — guide warns ODL_HYBRID_URL must be a trusted
  internal host with http/https scheme; `test_http_https_scheme_validation_documented`

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
