"""Learning-mode review queue (two-phase ingest).

Phase 1 — `enqueue`: a learning-mode synthesized answer is written to Redis as a
*pending* entry. It is deliberately NOT embedded, so unverified model output never
enters the vector store and can never surface in retrieval.

Phase 2 — `approve` / `reject`: a human moderator promotes a pending entry into the
`synthesized_answers` collection (now retrievable in learning mode) or discards it.

All vector-store writes happen only on approval, keeping the authoritative and
synthesized collections free of unreviewed content.
"""

import hashlib
import logging
from datetime import datetime, timezone

from langchain_core.documents import Document

from db.redis_client import get_redis
from db.vector import get_synthesized_vectorstore
from review.keys import PENDING_IDS_KEY, pending_key
from schemas.review import PendingReview

logger = logging.getLogger(__name__)


def make_entry_id(question: str, answer: str) -> str:
    """Stable id for a (question, answer) pair — matches the legacy synthesized doc id."""
    return f"synthesized:{hashlib.sha256((question + answer).encode()).hexdigest()[:12]}"


def enqueue(question: str, answer: str, best_score: float) -> str:
    """Queue a synthesized answer for review. Idempotent on (question, answer)."""
    entry_id = make_entry_id(question, answer)
    redis = get_redis()
    redis.hset(
        pending_key(entry_id),
        mapping={
            "entry_id": entry_id,
            "question": question,
            "answer": answer,
            "best_score": str(best_score),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        },
    )
    redis.sadd(PENDING_IDS_KEY, entry_id)
    logger.info("Queued synthesized answer '%s' for review (%d chars)", entry_id, len(answer))
    return entry_id


def _to_model(raw: dict) -> PendingReview:
    best = raw.get("best_score")
    return PendingReview(
        entry_id=raw.get("entry_id", ""),
        question=raw.get("question", ""),
        answer=raw.get("answer", ""),
        best_score=float(best) if best not in (None, "") else None,
        created_at=raw.get("created_at"),
        status=raw.get("status", "pending"),
    )


def list_pending(limit: int = 50, cursor: int = 0) -> tuple[int, list[PendingReview], str | None]:
    redis = get_redis()
    all_ids = sorted(redis.smembers(PENDING_IDS_KEY))  # stable order for deterministic paging
    page = all_ids[cursor : cursor + limit]
    entries = [_to_model(redis.hgetall(pending_key(eid))) for eid in page]
    next_cursor = str(cursor + limit) if cursor + limit < len(all_ids) else None
    return len(all_ids), entries, next_cursor


def get_pending(entry_id: str) -> dict | None:
    raw = get_redis().hgetall(pending_key(entry_id))
    return raw or None


def _discard(entry_id: str) -> None:
    redis = get_redis()
    redis.delete(pending_key(entry_id))
    redis.srem(PENDING_IDS_KEY, entry_id)


def approve(entry_id: str) -> bool:
    """Embed a pending entry into the synthesized store and remove it from the queue.

    Returns True. Raises ``KeyError`` if the entry does not exist.
    """
    raw = get_pending(entry_id)
    if not raw:
        raise KeyError(entry_id)

    best = raw.get("best_score")
    doc = Document(
        page_content=raw["answer"].strip(),
        metadata={
            "source": entry_id,
            "source_type": "synthesized",
            "source_question": raw.get("question", ""),
            "best_score": float(best) if best not in (None, "") else None,
            "reviewed": True,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    get_synthesized_vectorstore().add_documents([doc])
    _discard(entry_id)
    logger.info("Approved and embedded synthesized answer '%s'", entry_id)
    return True


def reject(entry_id: str) -> bool:
    """Discard a pending entry without embedding. Raises ``KeyError`` if absent."""
    if not get_pending(entry_id):
        raise KeyError(entry_id)
    _discard(entry_id)
    logger.info("Rejected synthesized answer '%s'", entry_id)
    return True
