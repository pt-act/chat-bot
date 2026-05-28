import logging

from fastapi import APIRouter, Depends, HTTPException

from db.redis_client import get_redis
from db.vector import delete_chunks_by_ids, get_chunks_by_doc_id, get_vectorstore
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
        logger.error("Ingest runtime error for %s: %s", request.file_name, e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception:
        logger.exception("Ingest failed for %s", request.file_name)
        raise HTTPException(status_code=500, detail="Failed to ingest file")


@router.get("/ingest/status/{doc_id}")
def ingest_status(doc_id: str):
    redis = get_redis()
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")
    return status


@router.get("/ingest/docs", dependencies=[Depends(require_api_key)])
def list_docs():
    redis = get_redis()
    doc_ids = redis.smembers(_ALL_DOCS_KEY)
    docs = [redis.hgetall(f"ingest_status:{doc_id}") for doc_id in doc_ids]
    return {"total": len(docs), "docs": docs}


@router.delete("/ingest/{doc_id}", dependencies=[Depends(require_api_key)])
def delete_doc(doc_id: str):
    redis = get_redis()
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")

    vs = get_vectorstore()
    results = get_chunks_by_doc_id(vs, doc_id)
    if results["ids"]:
        delete_chunks_by_ids(vs, results["ids"])
        logger.info("Deleted %d chunks from ChromaDB for %s", len(results["ids"]), doc_id)

    file_hash = status.get("file_hash")
    if file_hash:
        redis.hdel(_CONTENT_HASHES_KEY, file_hash)

    redis.delete(f"ingest_status:{doc_id}")
    redis.delete(f"doc_chunks:{doc_id}")
    redis.srem(_ALL_DOCS_KEY, doc_id)

    logger.info("Deleted document %s", doc_id)
    return {"status": "deleted", "doc_id": doc_id}


_ALL_DOCS_KEY = "ingest:doc_ids"
_CONTENT_HASHES_KEY = "ingest:content_hashes"
