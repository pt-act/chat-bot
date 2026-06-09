import hashlib
import logging
import os
import re
import tempfile
from datetime import datetime, timezone

import requests
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import get_settings
from db.redis_client import get_redis
from db.vector import VectorStoreRepository, get_vectorstore
from ingest.keys import ALL_DOCS_KEY, CONTENT_HASHES_KEY, doc_chunks_key, ingest_status_key
from ingest.loaders import detect_extension, load_documents
from ingest.pdf_opendataloader import build_hierarchical_chunks, load_pdf_odl
from utils.security import SSRFError, validate_download_url

logger = logging.getLogger(__name__)


def _validate_ingest_path(file_path: str) -> str:
    """Guard the file path before it is opened for hashing/loading (defense-in-depth
    against path-traversal / file-inclusion).

    Ingest paths are always **server-created** temp/staged files (URL downloads land in the
    system temp dir; uploads land there or in ``INGEST_INCOMING_DIR``). This resolves
    symlinks and rejects anything that is not a regular file inside one of those allowed
    base directories — notably a crafted ``file_path`` arriving on the durable ingest queue.
    Returns the resolved real path. Raises ``ValueError`` (→ the job is marked ``failed``).
    """
    real = os.path.realpath(file_path)
    if not os.path.isfile(real):
        raise ValueError(f"ingest path is not a regular file: {file_path!r}")
    allowed = (
        os.path.realpath(tempfile.gettempdir()),
        os.path.realpath(get_settings().ingest_incoming_dir),
    )
    if not any(real == base or real.startswith(base + os.sep) for base in allowed):
        raise ValueError(f"ingest path is outside the allowed directories: {file_path!r}")
    return real


def _file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _chunk_hash(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _download_file(s3_url: str, ext: str) -> str:
    setting = get_settings()
    max_bytes = setting.max_file_size_mb * 1024 * 1024

    # SSRF guard: validate URL before fetching
    validate_download_url(s3_url, setting.allowed_hosts)

    try:
        response = requests.get(
            s3_url,
            timeout=setting.download_timeout_seconds,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0"},
            # SSRF hardening: do not follow redirects — an allowed host could
            # otherwise 30x-redirect to a private/metadata address, bypassing
            # the validate_download_url() check that ran on the original URL.
            allow_redirects=False,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download {s3_url}: {e}") from e

    tmp = tempfile.NamedTemporaryFile(suffix=ext or ".bin", delete=False)
    size = 0
    with tmp:
        for chunk in response.iter_content(chunk_size=8192):
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError(f"File exceeds {setting.max_file_size_mb}MB limit")
            tmp.write(chunk)

    return tmp.name


def _check_duplicate_content(redis_client, new_file_hash: str, doc_id: str) -> dict | None:
    existing_doc_id = redis_client.hget(CONTENT_HASHES_KEY, new_file_hash)
    if existing_doc_id and existing_doc_id != doc_id:
        return {
            "doc_id": doc_id,
            "status": "skipped",
            "reason": f"duplicate content already ingested as '{existing_doc_id}'",
        }
    return None


# ODL-specific metadata fields to carry through the standard chunk-processing loop
# (so L1/L2 hierarchy and citation metadata survive into the vector store).
_ODL_PASSTHROUGH_KEYS = frozenset(
    {
        "chunk_level",
        "section_title",
        "element_type",
        "parent_chunk_id",
        "heading_level",
        "bbox",
        "page_end",
    }
)


def _build_chunks(
    file_path: str,
    doc_id: str,
    file_name: str,
    new_file_hash: str,
    version: str,
    ext: str,
    parser_override: str | None = None,
    hybrid_mode_override: str | None = None,
    pages_override: str | None = None,
) -> tuple[list[Document], set[str], dict]:
    """Chunk a local file into LangChain Documents ready for vector storage.

    Returns (chunks, chunk_hashes, diagnostics).  diagnostics contains FR8 ingest-status
    fields (parser, fallback_used, page_count, element_count, parser_mode) for PDF files;
    it is empty for non-PDF formats.

    parser_override / hybrid_mode_override / pages_override carry per-request values that
    take precedence over the deployment-level Settings defaults (FR9).
    """
    settings = get_settings()
    diagnostics: dict = {}

    # Decide whether to use ODL for PDF files.
    # Per-request parser_override beats the deployment-level setting.
    use_odl = False
    if ext == ".pdf":
        effective_parser = parser_override or settings.pdf_parser
        if effective_parser == "opendataloader":
            use_odl = True
        elif effective_parser is None:
            from ingest.pdf_preflight import preflight_check  # noqa: PLC0415

            use_odl, _ = preflight_check()

    if use_odl:
        raw_chunks, odl_elements, diagnostics = load_pdf_odl(
            file_path,
            settings,
            pages=pages_override,
            hybrid_mode_override=hybrid_mode_override,
        )
        if odl_elements:
            l1_chunks, l2_chunks = build_hierarchical_chunks(odl_elements)
            raw_chunks = l1_chunks + l2_chunks
    else:
        # For PDFs, pass "pypdf" explicitly to bypass a redundant preflight call inside
        # load_documents() now that we have already decided above.
        pdf_override = "pypdf" if ext == ".pdf" else None
        pages = load_documents(file_path, ext, parser=pdf_override)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, chunk_overlap=100, separators=["\n\n", "\n", ".", " ", ""]
        )
        raw_chunks = splitter.split_documents(pages)
        if ext == ".pdf":
            diagnostics = {
                "parser": "pypdf",
                "fallback_used": "false",
                "page_count": str(len(pages)),
                "element_count": str(len(raw_chunks)),
                "parser_mode": "local",
            }

    new_chunks = []
    new_hashes = set()

    for i, raw in enumerate(raw_chunks):
        text = _clean_text(raw.page_content)
        if not text:
            continue

        ch = _chunk_hash(text)
        new_hashes.add(ch)
        meta: dict = {
            "doc_id": doc_id,
            "source_file": file_name,
            "file_hash": new_file_hash,
            "chunk_hash": ch,
            "chunk_index": i,
            "page_number": raw.metadata.get("page", 0),
            "version": version,
        }
        # Pass through ODL-specific metadata (L1/L2 hierarchy, citation fields).
        # Non-ODL chunks have none of these keys so the loop is a no-op for them.
        for key in _ODL_PASSTHROUGH_KEYS:
            val = raw.metadata.get(key)
            if val is not None:
                meta[key] = val
        new_chunks.append(Document(page_content=text, metadata=meta))

    return new_chunks, new_hashes, diagnostics


def _sync_vectorstore(
    repo: VectorStoreRepository,
    redis_client,
    doc_id: str,
    new_chunks: list[Document],
    new_hashes: set[str],
    old_hashes: set[str],
) -> tuple[int, int]:
    stale = old_hashes - new_hashes
    fresh = new_hashes - old_hashes

    removed = 0
    if stale:
        results = repo.get_by_doc_id(doc_id)
        stale_ids = [
            results["ids"][i] for i, meta in enumerate(results["metadatas"]) if meta.get("chunk_hash") in stale
        ]
        if stale_ids:
            repo.delete_by_ids(stale_ids)
            removed = len(stale_ids)
        logger.info("Removed %d stale chunks for %s", removed, doc_id)

    to_add = [c for c in new_chunks if c.metadata["chunk_hash"] in fresh]
    added = 0
    if to_add:
        repo.add_documents(to_add)
        added = len(to_add)
        logger.info("Added %d new chunks for %s", added, doc_id)

    return added, removed


def _persist_ingest_status(
    redis_client,
    doc_id: str,
    new_file_hash: str,
    stored_file_hash: str | None,
    new_hashes: set[str],
    added: int,
    removed: int,
    total: int,
    version: str,
    file_name: str,
    diagnostics: dict | None = None,
):
    redis_client.delete(doc_chunks_key(doc_id))
    if new_hashes:
        redis_client.sadd(doc_chunks_key(doc_id), *new_hashes)

    redis_client.sadd(ALL_DOCS_KEY, doc_id)

    if stored_file_hash:
        redis_client.hdel(CONTENT_HASHES_KEY, stored_file_hash)
    redis_client.hset(CONTENT_HASHES_KEY, new_file_hash, doc_id)

    mapping: dict = {
        "file_hash": new_file_hash,
        "file_name": file_name,
        "version": version,
        "status": "done",
        "total_chunks": str(total),
        "added": str(added),
        "removed": str(removed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # FR8: write parser diagnostics when available (PDF ingest only).
    if diagnostics:
        for key in ("parser", "fallback_used", "page_count", "element_count", "parser_mode"):
            if key in diagnostics:
                mapping[key] = diagnostics[key]

    redis_client.hset(ingest_status_key(doc_id), mapping=mapping)


def _run_ingest(
    redis_client,
    doc_id: str,
    file_name: str,
    file_path: str,
    ext: str,
    parser_override: str | None = None,
    hybrid_mode_override: str | None = None,
    pages_override: str | None = None,
) -> dict:
    """Hash → dedup → chunk → sync → persist for an already-local file path.

    Shared by both the URL (`process_policy`) and upload (`process_uploaded`) paths.
    ``ext`` selects the document loader (see ingest.loaders).
    """
    # Sanitize the path before any file read (hash + loader). Both downstream open() calls
    # operate only on a validated, server-owned temp/staged file.
    file_path = _validate_ingest_path(file_path)
    new_file_hash = _file_hash(file_path)
    stored_file_hash = redis_client.hget(ingest_status_key(doc_id), "file_hash")

    if stored_file_hash == new_file_hash:
        logger.info("Skipping %s — file unchanged", doc_id)
        return {"doc_id": doc_id, "status": "skipped", "reason": "file unchanged"}

    dup_result = _check_duplicate_content(redis_client, new_file_hash, doc_id)
    if dup_result:
        logger.info("Skipping %s — duplicate content", doc_id)
        return dup_result

    version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_chunks, new_hashes, diagnostics = _build_chunks(
        file_path,
        doc_id,
        file_name,
        new_file_hash,
        version,
        ext,
        parser_override=parser_override,
        hybrid_mode_override=hybrid_mode_override,
        pages_override=pages_override,
    )

    repo = VectorStoreRepository(get_vectorstore())
    old_hashes = redis_client.smembers(doc_chunks_key(doc_id))

    added, removed = _sync_vectorstore(repo, redis_client, doc_id, new_chunks, new_hashes, old_hashes)

    _persist_ingest_status(
        redis_client,
        doc_id,
        new_file_hash,
        stored_file_hash,
        new_hashes,
        added,
        removed,
        len(new_chunks),
        version,
        file_name,
        diagnostics,
    )

    logger.info("Ingested %s — added=%d removed=%d total=%d", doc_id, added, removed, len(new_chunks))

    return {
        "doc_id": doc_id,
        "status": "done",
        "version": version,
        "added": added,
        "removed": removed,
        "total": len(new_chunks),
    }


def _mark_failed(redis_client, doc_id: str, error: Exception) -> None:
    redis_client.hset(
        ingest_status_key(doc_id),
        mapping={
            "status": "failed",
            "error": str(error),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def process_policy(
    file_name: str,
    s3_url: str,
    parser_override: str | None = None,
    hybrid_mode_override: str | None = None,
    pages_override: str | None = None,
) -> dict:
    """Ingest a document fetched from a remote URL (SSRF-guarded).

    The format is inferred from the URL's extension (see ingest.loaders).
    """
    doc_id = file_name
    redis_client = get_redis()
    ext = detect_extension(s3_url)
    file_path = None

    try:
        logger.info("Downloading %s (%s)", file_name, ext or "unknown format")
        file_path = _download_file(s3_url, ext)
        return _run_ingest(
            redis_client,
            doc_id,
            file_name,
            file_path,
            ext,
            parser_override=parser_override,
            hybrid_mode_override=hybrid_mode_override,
            pages_override=pages_override,
        )
    except SSRFError as e:
        logger.warning("SSRF blocked for %s: %s", doc_id, e)
        raise
    except Exception as e:
        _mark_failed(redis_client, doc_id, e)
        logger.exception("Ingest failed for %s", doc_id)
        raise
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


def process_uploaded(
    file_name: str,
    file_path: str,
    ext: str,
    parser_override: str | None = None,
    hybrid_mode_override: str | None = None,
    pages_override: str | None = None,
) -> dict:
    """Ingest a document already saved locally (e.g. an uploaded file).

    No download/SSRF step — the bytes are local. ``ext`` selects the loader. The caller
    owns creating ``file_path``; this function removes it when done (success or failure).
    """
    doc_id = file_name
    redis_client = get_redis()
    try:
        logger.info("Processing uploaded document %s (%s)", file_name, ext)
        return _run_ingest(
            redis_client,
            doc_id,
            file_name,
            file_path,
            ext,
            parser_override=parser_override,
            hybrid_mode_override=hybrid_mode_override,
            pages_override=pages_override,
        )
    except Exception as e:
        _mark_failed(redis_client, doc_id, e)
        logger.exception("Ingest failed for uploaded %s", doc_id)
        raise
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
