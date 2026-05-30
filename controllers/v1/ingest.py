"""v1 ingest controller — typed envelopes (IngestResult / DocsListResponse / DeleteResponse)."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from db.redis_client import get_redis
from db.vector import delete_chunks_by_ids, get_chunks_by_doc_id, get_vectorstore
from ingest.keys import ALL_DOCS_KEY, CONTENT_HASHES_KEY, doc_chunks_key, ingest_status_key
from middlewares.auth import require_api_key
from schemas.ingest import IngestRequest
from schemas.responses import DeleteResponse, DocsListResponse, IngestResult
from services.ingest_service import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])


@router.post(
    "/ingest",
    response_model=IngestResult,
    response_model_exclude_none=True,
    status_code=202,
    dependencies=[Depends(require_api_key)],
    summary="Queue a policy PDF for ingestion",
    description=(
        "Accepts the document and processes it in the background. Returns 202 with "
        "`status=queued`; poll `GET /ingest/status/{doc_id}` for progress."
    ),
)
def ingest(request: IngestRequest, background: BackgroundTasks, response: Response) -> IngestResult:
    # file_name is validated to contain no dots, so it equals the doc_id used by the
    # ingest pipeline (process_policy does file_name.removesuffix(".pdf")).
    doc_id = request.file_name
    redis = get_redis()
    redis.hset(ingest_status_key(doc_id), mapping={"doc_id": doc_id, "status": "queued", "file_name": doc_id})
    redis.sadd(ALL_DOCS_KEY, doc_id)

    background.add_task(ingest_file, request.file_name, str(request.s3_url))
    response.headers["Location"] = f"/api/v1/ingest/status/{doc_id}"
    logger.info("Queued ingest for %s", doc_id)
    return IngestResult(doc_id=doc_id, status="queued")


@router.get(
    "/ingest/status/{doc_id}",
    response_model=IngestResult,
    response_model_exclude_none=True,
    summary="Get ingest status",
)
def ingest_status(doc_id: str) -> IngestResult:
    redis = get_redis()
    status = redis.hgetall(ingest_status_key(doc_id))
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")
    extra = {k: v for k, v in status.items() if k in IngestResult.model_fields and k != "doc_id"}
    return IngestResult(doc_id=doc_id, **extra)


@router.get(
    "/ingest/docs",
    response_model=DocsListResponse,
    dependencies=[Depends(require_api_key)],
    summary="List ingested documents",
)
def list_docs(
    limit: int = Query(50, ge=1, le=200, description="Max docs to return."),
    cursor: int = Query(0, ge=0, description="Offset cursor from a previous page's next_cursor."),
) -> DocsListResponse:
    redis = get_redis()
    all_ids = sorted(redis.smembers(ALL_DOCS_KEY))  # stable order for deterministic paging
    page = all_ids[cursor : cursor + limit]
    docs = [redis.hgetall(ingest_status_key(doc_id)) for doc_id in page]
    next_cursor = str(cursor + limit) if cursor + limit < len(all_ids) else None
    return DocsListResponse(total=len(all_ids), docs=docs, next_cursor=next_cursor)


@router.delete(
    "/ingest/{doc_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(require_api_key)],
    summary="Delete an ingested document",
)
def delete_doc(doc_id: str) -> DeleteResponse:
    redis = get_redis()
    status = redis.hgetall(ingest_status_key(doc_id))
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")

    vs = get_vectorstore()
    results = get_chunks_by_doc_id(vs, doc_id)
    if results["ids"]:
        delete_chunks_by_ids(vs, results["ids"])
        logger.info("Deleted %d chunks from ChromaDB for %s", len(results["ids"]), doc_id)

    file_hash = status.get("file_hash")
    if file_hash:
        redis.hdel(CONTENT_HASHES_KEY, file_hash)

    redis.delete(ingest_status_key(doc_id))
    redis.delete(doc_chunks_key(doc_id))
    redis.srem(ALL_DOCS_KEY, doc_id)

    logger.info("Deleted document %s", doc_id)
    return DeleteResponse(status="deleted", doc_id=doc_id)
