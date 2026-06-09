# OpenDataLoader Operator Guide

Troubleshooting and operational reference for the ODL PDF parser integration.
For setup and configuration see the main [README](../README.md#openDataLoader-pdf-parser-optional--requires-java-11).

---

## Diagnosing ingest status

Check the parser used for any document:

```bash
curl http://127.0.0.1:8000/api/v1/ingest/status/{doc_id}
```

Relevant fields in the response:

| Field | Values | Meaning |
|-------|--------|---------|
| `parser` | `opendataloader` / `pypdf` | Which parser was used |
| `fallback_used` | `true` / `false` | Whether ODL failed and PyPDF was used instead |
| `parser_mode` | `local` / `hybrid` | Local Java or hybrid OCR sidecar |
| `page_count` | integer string | Number of pages in the document |
| `element_count` | integer string | Number of structural elements (ODL) or chunks (PyPDF) |

---

## Problem: Java not found

**Symptom:** Ingest status shows `parser=pypdf` and `fallback_used=true`, or the preflight
check returns "Java is not installed (java command not found)".

**Cause:** `java` is not on the server's `$PATH`.

**Fix:**

1. Install Java 11 or later:
   ```bash
   # Debian/Ubuntu
   sudo apt-get install -y openjdk-17-jre-headless

   # RHEL/CentOS
   sudo yum install java-17-openjdk-headless

   # macOS (Homebrew)
   brew install openjdk@17
   ```

2. Verify:
   ```bash
   java -version
   # → openjdk version "17.x.x" ...
   ```

3. If `java` is installed but not on `$PATH`, set the environment variable:
   ```bash
   export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
   export PATH="$JAVA_HOME/bin:$PATH"
   ```

4. Restart the API service. The preflight check runs on the first PDF ingest.

**Fallback behavior:** When Java is absent and `PDF_PARSER_FALLBACK=true` (default),
ingest silently falls back to PyPDF. Set `PDF_PARSER_FALLBACK=false` to make Java absence
a hard error (useful in environments where ODL is mandatory).

---

## Problem: opendataloader_pdf not installed

**Symptom:** `fallback_used=true`; logs show "opendataloader_pdf package is not installed".

**Fix:**
```bash
pip install opendataloader-pdf
```

For hybrid mode (OCR/enrichment):
```bash
pip install "opendataloader-pdf[hybrid]"
```

Restart the API after installation.

---

## Problem: Hybrid server not starting

**Symptom:** `parser_mode=local` instead of `hybrid`; logs show "Hybrid server unreachable".

**Cause:** The `odl-hybrid` sidecar is not running, or `ODL_HYBRID_URL` is misconfigured.

**Fix:**

1. Start the sidecar with the `hybrid` profile:
   ```bash
   docker compose --profile hybrid up odl-hybrid
   ```

2. Verify the sidecar is healthy:
   ```bash
   curl http://localhost:5002/health
   # → 200 OK (when accessed from inside the Docker network: http://odl-hybrid:5002/health)
   ```

3. Ensure your `.env` has:
   ```env
   ODL_HYBRID=docling-fast
   ODL_HYBRID_URL=http://odl-hybrid:5002
   ```

4. Check the sidecar logs for startup errors:
   ```bash
   docker compose logs odl-hybrid
   ```

**Fallback behavior:** Set `ODL_HYBRID_FALLBACK=true` to fall back to local Java (no OCR)
when the sidecar is unreachable, rather than failing the ingest.

> **Security:** Never expose the `odl-hybrid` container port to external networks.
> The sidecar must be accessible only on the internal Docker network (`app-network`).
> Do not add a `ports:` mapping to the `odl-hybrid` service in `docker-compose.yml`.
> `ODL_HYBRID_URL` should always point to an internal, trusted hostname — never an
> external or user-controlled URL. The preflight check validates that `ODL_HYBRID_URL`
> uses `http://` or `https://` scheme and contains no credentials in the URL.

---

## Problem: Enrichment producing empty chunks

**Symptom:** Formula or picture L2 chunks have empty `page_content`.

**Causes and fixes:**

1. **`ODL_HYBRID_MODE=auto` with enrichment enabled**  
   Enrichment requires full-page routing, not triage mode.  
   Fix: Set `ODL_HYBRID_MODE=full` when using `ODL_ENRICH_FORMULA=true` or `ODL_ENRICH_PICTURES=true`.
   The config validator will raise at startup if this constraint is violated.

2. **Hybrid sidecar not started with enrichment flags**  
   The sidecar must be started with `--enrich-formula` / `--enrich-picture-description`.
   The `odl-hybrid` service in `docker-compose.yml` uses environment variables to pass
   these flags. Set `ODL_ENRICH_FORMULA=true` in `.env` and restart the sidecar.

3. **Formula element has no LaTeX content**  
   Some ODL-detected formula regions may have empty `content` fields if extraction failed.
   This is a limitation of the underlying AI backend.

---

## Problem: Falling back to PyPDF manually

To force PyPDF globally (disabling ODL even when Java is present):

```env
# .env
PDF_PARSER=pypdf
```

To force PyPDF for a single ingest request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_name": "doc", "s3_url": "https://host/doc.pdf", "parser": "pypdf"}'
```

Or for an upload:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest/upload" \
  -F "file=@doc.pdf" -F "parser=pypdf"
```

---

## Problem: Hierarchical retrieval not activating

**Symptom:** Queries about tables do not return table chunks first.

**Fix:** Set the retrieval strategy:

```env
RETRIEVAL_STRATEGY=hierarchical
```

Valid strategies: `mmr` (default), `hybrid`, `hybrid_rerank`, `hierarchical`.

The `hierarchical` strategy requires that the vector store contains ODL L1/L2 chunks
(i.e., documents were ingested with ODL active). It gracefully handles legacy non-ODL
chunks (heuristics are silently skipped for chunks without `element_type` metadata).

---

## Problem: Ingest status shows no ODL fields

**Symptom:** Status response has no `parser`, `parser_mode`, `element_count` fields.

**Cause:** The document is a non-PDF format (TXT, DOCX, HTML, MD). ODL diagnostics are
only emitted for PDF ingestion. This is expected behavior.

---

## Environment variable quick reference

| Variable | Default | Notes |
|----------|---------|-------|
| `PDF_PARSER` | _(auto)_ | `pypdf` or `opendataloader` to override |
| `PDF_PARSER_FALLBACK` | `true` | `false` makes ODL failures hard errors |
| `ODL_FORMAT` | `json,markdown` | Controls ODL output; `json` required for L1/L2 |
| `ODL_READING_ORDER` | `xycut` | Reading-order algorithm |
| `ODL_USE_STRUCT_TREE` | `false` | Use PDF structure tags when present |
| `ODL_INCLUDE_HEADER_FOOTER` | `false` | Include page header/footer elements |
| `ODL_HYBRID` | _(off)_ | e.g. `docling-fast`; enables sidecar |
| `ODL_HYBRID_MODE` | `auto` | `auto` (triage) or `full` (all pages) |
| `ODL_HYBRID_URL` | _(auto)_ | Default `http://odl-hybrid:5002` with docker-compose |
| `ODL_HYBRID_FALLBACK` | `false` | Fall back to local Java if sidecar unreachable |
| `ODL_ENRICH_FORMULA` | `false` | LaTeX extraction (requires `ODL_HYBRID_MODE=full`) |
| `ODL_ENRICH_PICTURES` | `false` | Image descriptions (requires `ODL_HYBRID_MODE=full`) |
| `RETRIEVAL_STRATEGY` | `mmr` | Set `hierarchical` for ODL-aware retrieval |
