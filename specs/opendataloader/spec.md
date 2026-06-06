# OpenDataLoader Full Leverage — Specification

## Goal

Transform chat-bot's PDF pipeline from text-extraction into document understanding by
exploiting all three value layers OpenDataLoader provides:

- **Layer 1 (Content)**: ODL Markdown as chunk content — tables, headings, and lists survive
  ingestion and reach the LLM intact
- **Layer 2 (Retrieval)**: hierarchical chunks (section-level L1 + element-level L2) and
  element-type-aware retrieval heuristics — better recall@k on complex documents
- **Layer 3 (Context)**: the LLM prompt receives structured Markdown, not plain text — better
  answers on tables, structured data, and section-specific questions

Each layer compounds the previous one. Better chunks → better retrieval → better LLM answers
→ better citations.

---

## Consciousness Gate 1 ✓

| Question | Answer |
|---|---|
| Does this enhance human capability? | Yes — operators extract accurate, structured answers from complex PDFs |
| Does it foster contemplation, not distraction? | Yes — richer citations with section and element context encourage source verification |
| Is the system transparent (glass-box)? | Yes — ingest status exposes parser used, fallback decisions, and element counts |

**Gate 1: PASS. Proceed.**

---

## Architecture Overview

```mermaid
graph TD
    A[PDF file] --> B{Preflight: Java 11+ present?}
    B -- Yes --> C[ODL convert: format=json+markdown]
    B -- No / ODL fails --> D[PyPDFLoader fallback]
    C --> E[JSON tree walk + section propagation]
    C --> F[Markdown output]
    E --> G[Multi-page table merge]
    G --> H[L1 Section chunks]
    G --> I[L2 Element chunks]
    F --> I
    D --> J[Legacy flat chunks]
    H --> K[(ChromaDB: policies)]
    I --> K
    J --> K
    K --> L{retrieve_context}
    L --> M[Element-type heuristics]
    L --> N[L2 → L1 context expansion]
    M --> O[LangGraph graph]
    N --> O
    O --> P[LLM: Markdown-structured context]
    P --> Q[Answer + rich Source citations]

sequenceDiagram
    participant Op as Operator
    participant API as Ingest API
    participant ODL as ODL Adapter
    participant J as Java/JAR
    participant R as Redis
    participant C as ChromaDB

    Op->>API: POST /ingest/upload (pdf)
    API->>ODL: _run_ingest(file_path, ext=.pdf)
    ODL->>ODL: preflight_check()
    ODL->>J: convert(format=json+markdown, output_dir=tmp)
    J-->>ODL: {stem}.json + {stem}.md written
    ODL->>ODL: walk_tree(json) → L1 + L2 chunks
    ODL->>C: upsert(chunks)
    ODL->>R: persist_status(parser=odl, elements=N)
    ODL-->>API: IngestResult(done)
    API-->>Op: 200 OK
```

---

## Three-Track Delivery

### Track 1 — Fast Win: Markdown Content

**Effort**: ~5 iterations  
**Ships**: ODL Markdown as `page_content` in all PDF chunks

ODL's `format="markdown"` output replaces raw PyPDF text. Tables become pipe tables, headings
become `# Title`, lists become `- item`. No new chunker required — `RecursiveCharacterTextSplitter`
already splits on `\n\n` and `\n`, which Markdown headings and section breaks naturally provide.
The LLM receives structured text on the first day this ships.

Parser default logic: if Java 11+ is detected at preflight, ODL is active. PyPDF is the
fallback only when Java is absent or ODL throws. No operator config required to benefit.

**Milestone gate**: end-to-end PDF ingest produces Markdown chunks; LLM answers a table-based
question correctly; ingest status shows `parser=opendataloader`.

---

### Track 2 — Structural: JSON Tree + Hierarchical Retrieval

**Effort**: ~8 iterations (can parallel-run with Track 1 completion)  
**Ships**: L1/L2 chunk hierarchy + section-aware retrieval + rich citations

Dual-format conversion (`format="json,markdown"`) runs in a single JVM call. The JSON output
drives a tree walker that:
1. Propagates the current heading text as `section_title` down to every sibling/child element
2. Merges table fragments chained by `"previous table id"` / `"next table id"` before chunking
3. Recursively walks `kids` / `rows → cells → kids` / `list items → kids` to extract text

Two chunk granularities are indexed:
- **L1 (section)**: one chunk per heading section; content = full section Markdown up to
  `chunk_size`; `chunk_level=1`
- **L2 (element)**: one chunk per leaf (paragraph, table, list); content = element Markdown;
  `chunk_level=2`; `parent_chunk_id` points to the L1 chunk

A new `"hierarchical"` retrieval strategy in `_select_documents()` queries both granularities,
applies element-type heuristics (table bias for table-like queries; L1 bias for overview
queries), and expands L2 results to their L1 parent when section context improves groundedness.

**Milestone gate**: a table query retrieves the table chunk; an overview query retrieves a
section chunk; `_to_source()` populates `section`, `element_type`, `bbox`, `page_end`.

---

### Track 3 — Advanced: Hybrid/OCR + Enrichment

**Effort**: ~5 iterations (runs after Track 1, parallel with Track 2 later tasks)  
**Ships**: scanned PDF support + formula/picture enrichment

`docker-compose.yml` gains an `odl-hybrid` sidecar service running
`opendataloader-pdf-hybrid`. ODL adapter passes `hybrid="docling-fast"`,
`hybrid_mode=ODL_HYBRID_MODE`, `hybrid_url=ODL_HYBRID_URL` when `ODL_HYBRID` is set.
Hybrid server healthcheck gates hybrid ingest paths; if unreachable, behavior follows
`ODL_HYBRID_FALLBACK`.

When the hybrid server runs with `--enrich-formula` / `--enrich-picture-description`,
`formula` and `picture` element types appear in JSON. These become L2 chunks with
`element_type="formula"` (content = LaTeX string) or `element_type="picture"` (content =
natural-language image description). Enrichment is enabled client-side via
`ODL_ENRICH_FORMULA=true` / `ODL_ENRICH_PICTURES=true`.

**Milestone gate**: scanned PDF ingested successfully under hybrid mode; formula chunk
appears in ChromaDB with `element_type=formula`; misconfigured hybrid URL fails clearly.

---

## User Stories

| ID | Story | Track |
|----|-------|-------|
| US1 | As an operator, PDF chunks preserve table and heading structure so the LLM answers structured questions correctly | 1 |
| US2 | As an operator, ODL is the default parser when Java is present without explicit config | 1 |
| US3 | As a user, citations include section title, element type, and page range | 2 |
| US4 | As an operator, retrieval favours table chunks for table-like queries and section chunks for overview queries | 2 |
| US5 | As an operator, context expansion retrieves full sections when paragraph-level matches are insufficient | 2 |
| US6 | As an operator, scanned PDFs are ingested via OCR when hybrid mode is configured | 3 |
| US7 | As an operator, per-request `hybrid_mode` and `pages` override deployment defaults | 3 |
| US8 | As a developer, ingest status shows parser, element count, page count, fallback, and mode | 1+2 |

---

## Specific Requirements

### Functional Requirements

**FR1 — Parser Default Logic**  
Preflight at `_run_ingest()` entry checks `java -version`. If Java 11+ is detected and the
`opendataloader_pdf` package is importable, ODL is the active parser — no config change
required. `PDF_PARSER_FALLBACK=true` (default) enables PyPDF fallback on ODL failure.
`PDF_PARSER=pypdf` forces PyPDF regardless.

**FR2 — Markdown as Chunk Content**  
ODL-ingested PDF chunks store ODL Markdown fragments as `page_content`. The existing
`RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)` runs on the Markdown text.
Chunk boundaries align with Markdown block separators (`\n\n`).

**FR3 — JSON Tree Walker**  
`ingest/pdf_opendataloader.py` implements `walk_tree(doc: dict) -> list[Element]`:
- Depth-first traversal of `doc["kids"]`
- Tracks `current_section_title` (last seen `type=heading` content); injects into every
  non-heading element's metadata
- Skips `header` / `footer` elements unless `ODL_INCLUDE_HEADER_FOOTER=true`
- Recursively descends `kids` inside tables (cells), lists (list items), and nested containers
- All JSON keys mapped from space-separated ODL names to snake_case attributes

**FR4 — Multi-Page Table Merge**  
Before building chunks, the walker identifies tables where `"next table id"` is non-null.
Contiguous table chains are merged into a single logical table element. The merged element
spans `page_start` through `page_end` of the last fragment.

**FR5 — Hierarchical Chunk Indexing**  
Two chunk levels written to ChromaDB:

| Field | L1 (section) | L2 (element) |
|-------|-------------|-------------|
| `chunk_level` | `1` | `2` |
| `section_title` | heading text | propagated heading text |
| `element_type` | `"section"` | `"paragraph"`, `"table"`, `"list"`, etc. |
| `parent_chunk_id` | `None` | L1 chunk's `chunk_hash` |
| `heading_level` | `1`–`6` | `None` |
| `bbox` | `None` | `[left, bottom, right, top]` in PDF points |
| `page_end` | last page of section | last page of element |

Existing non-ODL chunks carry none of these fields. Retrieval code must tolerate absence.

**FR6 — Hierarchical Retrieval Strategy**  
New strategy `"hierarchical"` in `_select_documents()`:
- Queries ChromaDB for both L1 and L2 chunks in a single pass
- Applies element-type query heuristics:
  - Query contains `table|row|column|compare|vs\.|versus` → boost `element_type=table` results
  - Query contains `overview|summary|what is|introduction|about` → boost `element_type=section` (L1)
- Context expansion: L2 results with score > threshold whose L1 parent has not been fetched
  are expanded; L1 replaces L2 in the context window when token budget allows
- Heuristics are keyword-based, reversible, and configurable via `RETRIEVAL_STRATEGY`

**FR7 — Extended Source Schema**  
`schemas/responses.py:Source` adds four optional fields:
```
section: str | None       # heading text of containing section
element_type: str | None  # "paragraph", "table", "list", "heading", "formula"
page_end: int | None      # last page for multi-page elements
bbox: list[float] | None  # [left, bottom, right, top] in PDF points
```
All new fields default to `None`. Old clients receiving `null` must not error (non-breaking).

**FR8 — Ingest Status Diagnostics**  
`ingest_status:{doc_id}` Redis hash gains five new string fields:
```
parser          "opendataloader" | "pypdf"
fallback_used   "true" | "false"
page_count      str(int)
element_count   str(int)
parser_mode     "local" | "hybrid"
```

**FR9 — Per-Request Parser Override**  
`POST /api/v1/ingest` and `POST /api/v1/ingest/upload` accept three new optional body fields
(all `null`-defaulting, backward compatible):
```
parser:       "pypdf" | "opendataloader" | null
hybrid_mode:  "auto" | "full" | null
pages:        str | null   (e.g. "1-10", passed to convert(pages=...))
```
Validation rejects unknown `parser` values. `hybrid_mode` is only honoured when ODL is the
active parser and `ODL_HYBRID` is configured.

**FR10 — Hybrid Server Sidecar**  
`docker-compose.yml` gains an `odl-hybrid` service:
- Image: `python` base with `opendataloader-pdf[hybrid]`
- Command: `opendataloader-pdf-hybrid --port 5002`
- Healthcheck: `GET http://localhost:5002/health`
- `ODL_HYBRID_URL` defaults to `http://odl-hybrid:5002` when service is present
- Hybrid mode active only when `ODL_HYBRID=docling-fast` env var is set
- Unreachable server + `ODL_HYBRID_FALLBACK=true` → falls back to local Java only

**FR11 — Enrichment Support**  
When hybrid server runs with enrichment flags and `ODL_ENRICH_FORMULA=true` /
`ODL_ENRICH_PICTURES=true`:
- `formula` elements produce L2 chunks with `element_type=formula`, content = LaTeX string
- `picture` elements produce L2 chunks with `element_type=picture`, content = description text
- Requires `ODL_HYBRID_MODE=full` (enrichment does not work in triage mode)

---

### Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | ODL local conversion adds ≤ 2s overhead vs PyPDF for PDFs ≤ 50MB |
| Performance | Batch JVM invocation (`input_path=[...]`) used when queue flushes ≥ 2 PDFs simultaneously |
| Reliability | Missing Java → clear ingest failure reason in `ingest_status` within 500ms |
| Compatibility | All existing non-PDF ingest tests pass unchanged |
| Compatibility | New `Source` fields are `None` for non-ODL chunks; no consumer breaks |
| Observability | Ingest status distinguishes `parser=odl/local`, `odl/hybrid`, `pypdf` |
| Security | Temp dir from `convert()` always removed — including on exception |
| Security | ODL output dir is scoped to `tempfile.mkdtemp()`, never to `INGEST_INCOMING_DIR` |
| Security | `input_path` passed to `convert()` is the validated path from `_validate_ingest_path()` |

---

## PBT Validation Strategy

### Focused Testing Components
- HTTP endpoint routing: parser override fields accepted and validated (FR9)
- Ingest pipeline branching: ODL vs PyPDF dispatch logic in `_build_chunks`
- Fallback path: ODL failure + `PDF_PARSER_FALLBACK=true` → PyPDF succeeds
- Ingest status: all FR8 fields present and correct after successful ingest
- Citation card rendering: new Source fields present / absent without breaking UI
- End-to-end Track 1: PDF in → Markdown chunks in Chroma → LLM answer includes table content
- Hybrid healthcheck: server unreachable → graceful degradation

### Property-Based Testing Components
- **JSON field mapper** (data transformation — automatic PBT candidate)
- **Tree walker** (recursive stateful traversal — PBT for structural invariants)
- **Section title propagation** (stateful walk — PBT for consistency across arbitrary docs)
- **Multi-page table merger** (linked-list traversal — PBT for merge invariants)
- **Temp dir lifecycle** (resource management — PBT for cleanup guarantee)
- **Fallback invariant** (error handling — PBT for reliability)
- **Hierarchical parent link** (referential integrity — PBT across chunk store)

### Security Properties to Validate

1. **Path traversal**  
   `∀ file_path: validate_ingest_path(file_path) → passed to convert() only if within allowed dirs`

2. **Temp cleanup**  
   `∀ convert_call (success or failure): os.path.exists(temp_dir) == False after call`

3. **Subprocess input safety**  
   `∀ pdf_path: path_passed_to_convert() is the result of _validate_ingest_path(), not raw user input`

4. **Field injection guard**  
   `∀ odl_metadata: no user-supplied string appears in system metadata keys (doc_id, file_hash, chunk_hash)`

5. **Parser override validation**  
   `∀ parser_field: parser_field not in {"pypdf", "opendataloader", None} → 422 response`

---

## Validation Timeline

| Phase | What | When |
|-------|------|------|
| 3a | Focused tests: parser routing, Markdown chunks, ingest status fields | During Track 1 |
| 3b | PBT: field mapper, temp cleanup, fallback invariant | End of Track 1 |
| 3c | PBT: tree walker, section propagation, table merger | During Track 2 |
| 3d | Focused tests: hierarchical retrieval, context expansion, citation fields | End of Track 2 |
| 3e | Focused tests: hybrid sidecar, enrichment chunks, scanned PDF | Track 3 |
| 4  | Security audit: path safety + temp cleanup pre-validated by PBT; manual review for hybrid URL injection | After Track 3 |

---

## Existing Code to Leverage

| File | How it's used |
|------|--------------|
| `ingest/loaders.py:load_documents()` | Extend dispatcher — add ODL branch, all others untouched |
| `ingest/policies.py:_build_chunks()` | Branch here for ODL PDFs vs existing splitter path |
| `ingest/policies.py:_run_ingest()` | Preflight call entry point + status metadata extension |
| `ingest/policies.py:_persist_ingest_status()` | Add FR8 diagnostic fields to existing call |
| `ingest/policies.py:_validate_ingest_path()` | Pass its output directly to `convert()` |
| `ingest/retrieval.py:hybrid_retrieve()` | Model the `hierarchical` strategy on this existing pattern |
| `graph/nodes/retrieve_context.py:_to_source()` | Extend to map 4 new metadata fields |
| `graph/nodes/retrieve_context.py:_select_documents()` | Add `"hierarchical"` alongside `"mmr"` / `"hybrid"` |
| `schemas/responses.py:Source` | Add 4 optional fields with `None` defaults |
| `config.py:Settings` | Add `ODL_*` env vars following existing Pydantic validator patterns |
| `controllers/v1/ingest.py:IngestRequest` | Add 3 optional override fields |
| `docker-compose.yml` | Add `odl-hybrid` following Redis/Chroma service pattern |

---

## Out of Scope

- Image extraction or image content in vector store
- Tagged PDF / accessibility output (`format="tagged-pdf"`)
- PII sanitization via ODL's `sanitize` parameter
- Non-PDF format improvements (TXT, MD, DOCX, HTML unchanged)
- Reranking model integration
- Multi-tenant chunk isolation
- Full chat UI redesign (citation card fields only)
- Async streaming of ODL conversion progress
- ODL outside the ingest pipeline (e.g., chat-time PDF parsing)
- Hancom AI hybrid backend (Docling only)
- ODL `use_struct_tree=True` (safe to add as config flag, but no dedicated issue — just wire it)
