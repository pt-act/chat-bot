# Requirements: OpenDataLoader Full Leverage in chat-bot

## Problem Statement

chat-bot treats PDFs as bags of extracted text. `PyPDFLoader` discards document structure —
headings, tables, lists, reading order — at ingestion time. This produces three compounding
problems that no amount of retrieval tuning can fully compensate for:

1. **Content degradation** — a PDF table arrives in ChromaDB as loose words or garbled columns.
   The LLM can't answer table-based questions because the structure never survived ingestion.

2. **Flat retrieval** — all chunks are semantically equal regardless of whether they are a
   section heading, a data table, or a footnote. No retrieval strategy can privilege the right
   granularity because granularity was never recorded.

3. **Shallow citations** — `Source` objects know `page` and `snippet` but not `section`, not
   `element_type`, not even whether the matched content came from a table or a heading. Users
   can't navigate to the right place in the source document.

OpenDataLoader solves all three layers simultaneously. The existing implementation plan (Issues
1–17) addresses only the parser replacement layer — it produces better text via ODL but stores
it the same way and retrieves it the same way. The full vision adds two more layers on top.

---

## Three Value Layers

### Layer 1 — Content (what goes into chunks)
ODL's Markdown output preserves tables as pipe tables, headings as `#` markers, lists as
bullet points. Feeding that Markdown into the existing `RecursiveCharacterTextSplitter` gives
immediate quality gains with near-zero new code. The LLM receives structured text, not
PyPDF noise.

### Layer 2 — Retrieval (how chunks are found)
ODL's JSON output exposes full document structure: heading hierarchy, element types, bounding
boxes, page numbers, multi-page table chains. Building two chunk granularities (section-level
L1 and element-level L2) plus element-type-aware retrieval heuristics improves recall@k on
complex documents.

### Layer 3 — Context (what the LLM sees)
Chunk content stored as Markdown means `retrieve_context.py` assembles Markdown context for
the LLM prompt, not plain text. Tables, lists, and headings survive all the way to answer
generation. No new prompt engineering needed — just better content in the same slots.

---

## Codebase Analysis

### chat-bot touchpoints

| File | Current state | What changes |
|------|--------------|-------------|
| `ingest/loaders.py` | Single `load_documents()` dispatcher, PDF = `PyPDFLoader` | Add ODL branch in dispatcher |
| `ingest/policies.py:_build_chunks()` | One universal `RecursiveCharacterTextSplitter` for all formats | Branch for ODL PDFs → semantic chunker |
| `ingest/policies.py:_run_ingest()` | Orchestrator, calls `_build_chunks` | Add preflight call + parser metadata |
| `ingest/policies.py:_persist_ingest_status()` | Stores 8 fields in Redis | Extend with parser diagnostics |
| `graph/nodes/retrieve_context.py:_to_source()` | Maps `page_number`, `source_file`, `score`, `snippet` | Map 4 new metadata fields |
| `graph/nodes/retrieve_context.py:_select_documents()` | Dispatches `mmr` / `hybrid` strategies | Add `hierarchical` strategy |
| `schemas/responses.py:Source` | 5 fields: label, doc_id, score, page, snippet | Add 4 optional fields |
| `config.py:Settings` | No PDF parser settings | Add `ODL_*` env vars |
| `controllers/v1/ingest.py` | URL + upload endpoints, fixed pipeline | Add optional parser override fields |
| `docker-compose.yml` | API + Redis + Chroma | Add `odl-hybrid` sidecar service |

### opendataloader-pdf key facts

- **Entry point**: `opendataloader_pdf.convert(input_path, output_dir, format, ...)` — returns
  `None`, writes files to `output_dir`
- **Output filename convention**: `{output_dir}/{Path(input_path).stem}.json` / `.md`
- **JSON field naming**: space-separated keys — `"page number"`, `"bounding box"`,
  `"heading level"`, `"number of pages"` — all require explicit mapping
- **Element types**: `heading`, `paragraph`, `table`, `list`, `image`, `caption`,
  `header`, `footer`, `formula` (hybrid), `picture` (hybrid)
- **Table structure**: nested `rows → cells → kids`; multi-page tables linked via
  `"previous table id"` / `"next table id"`
- **Lists**: nested `list items → kids`; content never at top level of list/table element
- **Hybrid mode**: separate FastAPI sidecar (`opendataloader-pdf-hybrid`), triage
  (`auto`) or full-page (`full`) routing to Docling/EasyOCR backend
- **Enrichment**: `--enrich-formula` (LaTeX) and `--enrich-picture-description` (SmolVLM)
  produce `formula` and `picture` element types in JSON
- **Java requirement**: Java 11+; `java -version` must exit 0; version should be validated

---

## Constraints

- Must not break existing TXT / MD / DOCX / HTML ingest paths
- Must not break existing non-PDF chunk metadata consumers in Chroma or Redis
- PyPDF path must remain as emergency fallback (Java absent or ODL failure)
- All new `Source` fields must be optional — old API clients must not error on `null`
- Frontend must compile and pass typecheck after citation schema changes
- Hybrid server is optional; local-only ODL (no hybrid) must work independently
- Java absence must produce a clear, user-readable ingest failure reason
- Temp directories from ODL conversion must always be cleaned up, including on failure
- ODL output scoped to system temp only, never to `INGEST_INCOMING_DIR`

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As an operator, PDF chunks preserve table and heading structure so the LLM can answer structured questions correctly |
| US2 | As an operator, ODL is the default parser when Java is present, without requiring explicit config changes |
| US3 | As a user, citations include section title, element type, and page range so I can navigate the source document |
| US4 | As an operator, retrieval favours table chunks for table-like queries and section chunks for overview queries |
| US5 | As an operator, context expansion retrieves full sections when paragraph-level matches are insufficient |
| US6 | As an operator, scanned PDFs are ingested via OCR when hybrid mode is configured |
| US7 | As an operator, per-request parser override forces hybrid mode for known-scanned documents |
| US8 | As a developer, ingest status shows parser used, element count, page count, and fallback decision |

---

## Out of Scope

- Image content extraction or storage in vector store
- Tagged PDF / accessibility output (`format="tagged-pdf"`)
- PII sanitization via ODL's `sanitize` parameter
- Non-PDF format improvements (TXT, MD, DOCX, HTML unchanged)
- Reranking model integration
- Multi-tenant chunk isolation
- Full chat UI redesign (citation card fields only)
- Async streaming of ODL conversion progress
- ODL use outside the ingest pipeline (e.g., chat-time PDF parsing)
- Hancom AI hybrid backend (Docling only for initial hybrid support)
