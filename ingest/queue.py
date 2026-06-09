"""Durable, retryable ingestion queue (#4).

When ``INGEST_MODE=queue``, controllers enqueue a JSON job onto a Redis list instead of
running ingestion in-process via FastAPI ``BackgroundTasks``. A separate worker
(``python -m ingest.worker``) consumes jobs, so an API restart mid-ingest no longer loses
work — the job stays on the queue until a worker completes it.

Guarantees:
- **Crash-safety** — jobs live in Redis, not the web process.
- **Retries** — transient failures (download/network) re-enqueue with ``attempts+1`` up to
  ``ingest_max_attempts``, then the doc is marked ``failed``.
- **Idempotency** — a per-``doc_id`` lock prevents double-processing, on top of the
  existing content-hash dedup in the ingest pipeline (re-running converges, never dupes).

The ``inline`` default keeps the original ``BackgroundTasks`` behavior so small deployments
and existing tests are unchanged.
"""

import json
import logging
import os

from config import get_settings
from db.redis_client import get_redis
from ingest.policies import _mark_failed, _run_ingest, process_policy
from utils.resilience import is_transient

logger = logging.getLogger(__name__)

INGEST_QUEUE_KEY = "ingest:queue"
_LOCK_TTL = 600  # seconds — generous upper bound for a single ingest run


def _lock_key(doc_id: str) -> str:
    return f"ingest:lock:{doc_id}"


def enqueue(job: dict) -> None:
    """Push an ingest job onto the durable queue.

    ``job`` = ``{kind: "url"|"upload", file_name, ext, s3_url?|file_path?, attempts?}``.
    """
    job.setdefault("attempts", 0)
    get_redis().rpush(INGEST_QUEUE_KEY, json.dumps(job))
    logger.info("Enqueued ingest job for %s (kind=%s)", job.get("file_name"), job.get("kind"))


def _ingest_transient(exc: Exception) -> bool:
    """Worth retrying? Network/timeout errors and URL-download RuntimeErrors are; an SSRF
    block, an unsupported format (ValueError), or a size-limit error are not."""
    if is_transient(exc):
        return True
    return isinstance(exc, RuntimeError) and "download" in str(exc).lower()


def _cleanup_upload(job: dict) -> None:
    """Remove a staged upload file (uploads stage to a shared dir; URLs self-clean)."""
    if job.get("kind") == "upload":
        path = job.get("file_path")
        if path and os.path.exists(path):
            os.remove(path)


def _run_job(redis, job: dict) -> dict:
    doc_id = job["file_name"]
    parser = job.get("parser")
    hybrid_mode = job.get("hybrid_mode")
    pages = job.get("pages")
    if job["kind"] == "url":
        # process_policy re-downloads each attempt and handles its own temp cleanup + SSRF.
        return process_policy(
            doc_id,
            job["s3_url"],
            parser_override=parser,
            hybrid_mode_override=hybrid_mode,
            pages_override=pages,
        )
    # Upload: run the shared core directly so the staged file survives transient retries
    # (process_uploaded would delete it). The queue layer owns the file's lifecycle.
    return _run_ingest(
        redis,
        doc_id,
        doc_id,
        job["file_path"],
        job["ext"],
        parser_override=parser,
        hybrid_mode_override=hybrid_mode,
        pages_override=pages,
    )


def process_one(redis=None, block_timeout: int = 5) -> dict | None:
    """Claim and process a single job. Returns a result dict, or None if the queue is idle.

    Hermetic-testable: pass a fakeredis client and call directly (no daemon needed).
    """
    redis = redis or get_redis()
    if block_timeout and block_timeout > 0:
        item = redis.blpop(INGEST_QUEUE_KEY, timeout=block_timeout)
        if not item:
            return None
        _key, raw = item  # BLPOP returns (key, value)
    else:
        raw = redis.lpop(INGEST_QUEUE_KEY)  # non-blocking poll (block_timeout=0)
        if raw is None:
            return None
    job = json.loads(raw)
    doc_id = job["file_name"]
    settings = get_settings()

    # Idempotency: only one worker processes a given doc_id at a time.
    if not redis.set(_lock_key(doc_id), "1", nx=True, ex=_LOCK_TTL):
        logger.info("doc_id %s is locked; another worker owns it — skipping", doc_id)
        return {"doc_id": doc_id, "status": "skipped", "reason": "locked"}

    try:
        result = _run_job(redis, job)
        _cleanup_upload(job)
        logger.info("Ingest job done for %s (status=%s)", doc_id, result.get("status"))
        return result
    except Exception as e:
        attempts = job.get("attempts", 0) + 1
        if _ingest_transient(e) and attempts < settings.ingest_max_attempts:
            job["attempts"] = attempts
            redis.rpush(INGEST_QUEUE_KEY, json.dumps(job))
            logger.warning(
                "Re-enqueued %s after transient failure (attempt %d/%d): %s",
                doc_id,
                attempts,
                settings.ingest_max_attempts,
                e,
            )
            return {"doc_id": doc_id, "status": "retry", "attempts": attempts}
        _mark_failed(redis, doc_id, e)
        _cleanup_upload(job)
        logger.error("Ingest job for %s failed permanently after %d attempt(s): %s", doc_id, attempts, e)
        return {"doc_id": doc_id, "status": "failed", "reason": str(e)}
    finally:
        redis.delete(_lock_key(doc_id))
