"""v1 ingest controller — typed envelopes (IngestResult / DocsListResponse / DeleteResponse)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

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
    dependencies=[Depends(require_api_key)],
    summary="Ingest a policy PDF",
)
def ingest(request: IngestRequest) -> IngestResult:
    try:
        result = ingest_file(request.file_name, str(request.s3_url))
    except ValueError as e:
        logger.warning("Ingest validation failed for %s: %s", request.file_name, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        logger.error("Ingest runtime error for %s: %s", request.file_name, e)
        raise HTTPException(status_code=500, detail="Failed to ingest file") from e
    return IngestResult(**result)


@router.get("/ingest/status/{doc_id}", response_model=IngestResult, summary="Get ingest status")
def ingest_status(doc_id: str) -> IngestResult:
    redis = get_redis()
    status = redis.hgetall(ingest_status_key(doc_id))
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")
    return IngestResult(doc_id=doc_id, **{k: v for k, v in status.items() if k in IngestResult.model_fields})


@router.get(
    "/ingest/docs",
    response_model=DocsListResponse,
    dependencies=[Depends(require_api_key)],
    summary="List ingested documents",
)
def list_docs() -> DocsListResponse:
    redis = get_redis()
    doc_ids = redis.smembers(ALL_DOCS_KEY)
    docs = [redis.hgetall(ingest_status_key(doc_id)) for doc_id in doc_ids]
    return DocsListResponse(total=len(docs), docs=docs, next_cursor=None)


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
