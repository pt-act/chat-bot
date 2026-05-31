"""v1 review controller — moderate learning-mode synthesized answers (two-phase ingest).

Pending entries are produced by the learning-mode `self_ingest` node and held in Redis
without being embedded. A moderator lists them, then approves (embed into the
synthesized store) or rejects (discard). Writes are gated by `require_api_key`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from middlewares.auth import require_api_key
from schemas.review import PendingListResponse, ReviewDecision
from services import review_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["review"])


@router.get(
    "/review/pending",
    response_model=PendingListResponse,
    dependencies=[Depends(require_api_key)],
    summary="List synthesized answers awaiting review",
)
def list_pending(
    limit: int = Query(50, ge=1, le=200, description="Max entries to return."),
    cursor: int = Query(0, ge=0, description="Offset cursor from a previous page's next_cursor."),
) -> PendingListResponse:
    total, entries, next_cursor = review_service.list_pending(limit=limit, cursor=cursor)
    return PendingListResponse(total=total, pending=entries, next_cursor=next_cursor)


@router.post(
    "/review/{entry_id}/approve",
    response_model=ReviewDecision,
    dependencies=[Depends(require_api_key)],
    summary="Approve a pending entry (embed it into the synthesized store)",
)
def approve(entry_id: str) -> ReviewDecision:
    try:
        review_service.approve(entry_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"No pending entry '{entry_id}'") from e
    logger.info("Approved pending review entry %s", entry_id)
    return ReviewDecision(entry_id=entry_id, status="approved", embedded=True)


@router.post(
    "/review/{entry_id}/reject",
    response_model=ReviewDecision,
    dependencies=[Depends(require_api_key)],
    summary="Reject a pending entry (discard without embedding)",
)
def reject(entry_id: str) -> ReviewDecision:
    try:
        review_service.reject(entry_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"No pending entry '{entry_id}'") from e
    logger.info("Rejected pending review entry %s", entry_id)
    return ReviewDecision(entry_id=entry_id, status="rejected", embedded=False)
