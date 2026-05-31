"""Persistent feedback store + quality-loop exporter (#3).

Captures 👍/👎 (+optional reason and a Q/A snapshot) from real usage, stores it in Redis
(mirroring the `review` feature's shape), and lets operators list thumbs-down items and
export them into the RAGAS golden set — turning one-shot eval into a continuous loop.

Open submission is rate-limited at the HTTP layer; listing is API-key gated in the
controller. Stored reasons are run through the output guardrail so user text cannot
smuggle PII into the operator view.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db.redis_client import get_redis
from feedback.keys import FEEDBACK_IDS_KEY, feedback_key
from guardrails import sanitize_output
from schemas.feedback import FeedbackEntry

logger = logging.getLogger(__name__)

# Fields persisted per entry. Optional ones are stored as "" and re-nulled on read.
_OPTIONAL_FIELDS = ("reason", "correlation_id", "question", "answer")


def record(
    rating: str,
    reason: str | None = None,
    correlation_id: str | None = None,
    question: str | None = None,
    answer: str | None = None,
) -> str:
    """Persist a feedback entry and return its id."""
    feedback_id = uuid.uuid4().hex[:12]
    # Guardrail the free-text reason before it is stored/surfaced to operators.
    clean_reason = sanitize_output(reason)[0] if reason else ""

    mapping = {
        "feedback_id": feedback_id,
        "rating": rating,
        "reason": clean_reason,
        "correlation_id": correlation_id or "",
        "question": question or "",
        "answer": answer or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    redis = get_redis()
    redis.hset(feedback_key(feedback_id), mapping=mapping)
    redis.sadd(FEEDBACK_IDS_KEY, feedback_id)
    logger.info("Recorded feedback %s (rating=%s)", feedback_id, rating)
    return feedback_id


def _to_entry(raw: dict) -> FeedbackEntry:
    return FeedbackEntry(
        feedback_id=raw.get("feedback_id", ""),
        rating=raw.get("rating", ""),
        **{f: (raw.get(f) or None) for f in _OPTIONAL_FIELDS},
        created_at=raw.get("created_at") or None,
    )


def _all_entries() -> list[FeedbackEntry]:
    redis = get_redis()
    ids = sorted(redis.smembers(FEEDBACK_IDS_KEY))
    return [_to_entry(redis.hgetall(feedback_key(fid))) for fid in ids]


def list_feedback(
    rating: str | None = None, limit: int = 50, cursor: int = 0
) -> tuple[int, list[FeedbackEntry], str | None]:
    """List feedback, optionally filtered by rating, paginated by offset cursor."""
    entries = _all_entries()
    if rating:
        entries = [e for e in entries if e.rating == rating]
    page = entries[cursor : cursor + limit]
    next_cursor = str(cursor + limit) if cursor + limit < len(entries) else None
    return len(entries), page, next_cursor


def export_downvoted_to_golden(path: str | Path) -> int:
    """Append thumbs-down questions to the RAGAS golden set; returns the count appended.

    Each line is ``{"question": ..., "ground_truth": <answer or "">}``. Entries without a
    question are skipped (nothing to evaluate against).
    """
    path = Path(path)
    appended = 0
    with path.open("a", encoding="utf-8") as fh:
        for e in _all_entries():
            if e.rating != "down" or not e.question:
                continue
            fh.write(json.dumps({"question": e.question, "ground_truth": e.answer or ""}, ensure_ascii=False) + "\n")
            appended += 1
    logger.info("Exported %d downvoted questions to %s", appended, path)
    return appended
