"""v1 feedback controller — capture 👍/👎 on answers and let operators review them (#3).

Submission (`POST /feedback`) is **open** to end users (protected only by the global
per-IP rate limiter) so the web client can wire inline feedback. Listing
(`GET /feedback`) is gated by the same `require_api_key` dependency as review/ingest.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query

from middlewares.auth import require_api_key
from middlewares.observability import correlation_id_var
from schemas.feedback import FeedbackListResponse, FeedbackRequest, FeedbackResponse
from services import feedback_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="Submit feedback on an answer",
    description=(
        "Record a thumbs-up/down (with an optional reason and Q/A snapshot). Open to end "
        "users; the turn's correlation id is captured automatically when not supplied."
    ),
)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    correlation_id = request.correlation_id or correlation_id_var.get() or None
    feedback_id = feedback_service.record(
        rating=request.rating,
        reason=request.reason,
        correlation_id=correlation_id,
        question=request.question,
        answer=request.answer,
    )
    return FeedbackResponse(feedback_id=feedback_id, rating=request.rating)


@router.get(
    "/feedback",
    response_model=FeedbackListResponse,
    dependencies=[Depends(require_api_key)],
    summary="List submitted feedback (operators)",
)
def list_feedback(
    rating: Literal["up", "down"] | None = Query(default=None, description="Filter by rating."),
    limit: int = Query(50, ge=1, le=200, description="Max entries to return."),
    cursor: int = Query(0, ge=0, description="Offset cursor from a previous page's next_cursor."),
) -> FeedbackListResponse:
    total, entries, next_cursor = feedback_service.list_feedback(rating=rating, limit=limit, cursor=cursor)
    return FeedbackListResponse(total=total, feedback=entries, next_cursor=next_cursor)
