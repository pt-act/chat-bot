import hashlib
import logging
import os
import re
import tempfile
from datetime import datetime, timezone

import requests
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import get_settings
from db.redis_client import get_redis
from db.vector import VectorStoreRepository, get_vectorstore
from ingest.keys import ALL_DOCS_KEY, CONTENT_HASHES_KEY, doc_chunks_key, ingest_status_key
from utils.security import SSRFError, validate_download_url

logger = logging.getLogger(__name__)


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


def _download_file(s3_url: str, file_name: str) -> str:
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

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
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


def _build_chunks(
    file_path: str, doc_id: str, file_name: str, new_file_hash: str, version: str
) -> tuple[list[Document], set[str]]:
    pages = PyPDFLoader(file_path).load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100, separators=["\n\n", "\n", ".", " ", ""]
    )
    raw_chunks = splitter.split_documents(pages)

    new_chunks = []
    new_hashes = set()

    for i, raw in enumerate(raw_chunks):
        text = _clean_text(raw.page_content)
        if not text:
            continue

        ch = _chunk_hash(text)
        new_hashes.add(ch)
        new_chunks.append(
            Document(
                page_content=text,
                metadata={
                    "doc_id": doc_id,
                    "source_file": file_name,
                    "file_hash": new_file_hash,
                    "chunk_hash": ch,
                    "chunk_index": i,
                    "page_number": raw.metadata.get("page", 0),
                    "version": version,
                },
            )
        )

    return new_chunks, new_hashes


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
):
    redis_client.delete(doc_chunks_key(doc_id))
    if new_hashes:
        redis_client.sadd(doc_chunks_key(doc_id), *new_hashes)

    redis_client.sadd(ALL_DOCS_KEY, doc_id)

    if stored_file_hash:
        redis_client.hdel(CONTENT_HASHES_KEY, stored_file_hash)
    redis_client.hset(CONTENT_HASHES_KEY, new_file_hash, doc_id)

    redis_client.hset(
        ingest_status_key(doc_id),
        mapping={
            "file_hash": new_file_hash,
            "file_name": file_name,
            "version": version,
            "status": "done",
            "total_chunks": str(total),
            "added": str(added),
            "removed": str(removed),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def process_policy(file_name: str, s3_url: str) -> dict:
    # NOTE: use removesuffix, NOT rstrip — str.rstrip(".pdf") strips any trailing
    # combination of the characters {'.', 'p', 'd', 'f'}, so "app.pdf" -> "a".
    doc_id = file_name.removesuffix(".pdf")
    redis_client = get_redis()
    file_path = None

    try:
        logger.info("Downloading %s", file_name)
        file_path = _download_file(s3_url, file_name)

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
        new_chunks, new_hashes = _build_chunks(file_path, doc_id, file_name, new_file_hash, version)

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

    except SSRFError as e:
        logger.warning("SSRF blocked for %s: %s", doc_id, e)
        raise
    except Exception as e:
        redis_client.hset(
            ingest_status_key(doc_id),
            mapping={
                "status": "failed",
                "error": str(e),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.exception("Ingest failed for %s", doc_id)
        raise

    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
