import logging

from fastapi import APIRouter, Depends, HTTPException

from db.redis_client import get_redis
from db.vector import delete_chunks_by_ids, get_chunks_by_doc_id, get_vectorstore
from ingest.keys import ALL_DOCS_KEY, CONTENT_HASHES_KEY, doc_chunks_key, ingest_status_key
from middlewares.auth import require_api_key
from schemas.ingest import IngestRequest
from services.ingest_service import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest", dependencies=[Depends(require_api_key)])
def ingest_controller(request: IngestRequest):
    try:
        result = ingest_file(request.file_name, str(request.s3_url))
        return {"status": "success", "data": result}
    except ValueError as e:
        logger.warning("Ingest validation failed for %s: %s", request.file_name, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        # Log detail server-side; return a generic message (no internal text leak).
        logger.error("Ingest runtime error for %s: %s", request.file_name, e)
        raise HTTPException(status_code=500, detail="Failed to ingest file") from e
    except Exception:
        logger.exception("Ingest failed for %s", request.file_name)
        raise HTTPException(status_code=500, detail="Failed to ingest file")


@router.get("/ingest/status/{doc_id}")
def ingest_status(doc_id: str):
    redis = get_redis()
    status = redis.hgetall(ingest_status_key(doc_id))
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")
    return status


@router.get("/ingest/docs", dependencies=[Depends(require_api_key)])
def list_docs():
    redis = get_redis()
    doc_ids = redis.smembers(ALL_DOCS_KEY)
    docs = [redis.hgetall(ingest_status_key(doc_id)) for doc_id in doc_ids]
    return {"total": len(docs), "docs": docs}


@router.delete("/ingest/{doc_id}", dependencies=[Depends(require_api_key)])
def delete_doc(doc_id: str):
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
    return {"status": "deleted", "doc_id": doc_id}
