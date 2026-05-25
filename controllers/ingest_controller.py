import logging

from fastapi import APIRouter, HTTPException

from db.redis_client import redis
from db.vector import get_vectorstore
from schemas.ingest import IngestRequest
from services.ingest_service import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest")
def ingest_controller(request: IngestRequest):
    try:
        result = ingest_file(request.file_name, str(request.s3_url))
        return {"status": "success", "data": result}
    except Exception:
        logger.exception("Ingest failed for %s", request.file_name)
        raise HTTPException(status_code=500, detail="Failed to ingest file")


@router.get("/ingest/status/{doc_id}")
def ingest_status(doc_id: str):
    """Check the ingest status of a specific document."""
    # Each document's ingest status is stored in a Redis hash with key "ingest_status:{doc_id}". The hash contains fields like "status", "file_name", "error_message", etc.
    # redis.hgetall returns a dictionary of all fields in the hash. If the hash doesn't exist, it returns an empty dictionary.
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")
    return status


@router.get("/ingest/docs")
def list_docs():
    """List all ingested documents and their current status."""
    # We keep track of all ingested document IDs in a Redis set called "ingest:doc_ids". To list all documents, we fetch all doc IDs from that set, then retrieve the status hash for each doc ID.
    # redis.smembers("ingest:doc_ids") returns a set of all document IDs. We then use a list comprehension to call redis.hgetall for each doc ID, which gives us a list of status dictionaries for all documents.
    doc_ids = redis.smembers("ingest:doc_ids")
    docs = [redis.hgetall(f"ingest_status:{doc_id}") for doc_id in doc_ids]
    return {"total": len(docs), "docs": docs}


@router.delete("/ingest/{doc_id}")
def delete_doc(doc_id: str):
    """Delete a document from ChromaDB and all its Redis tracking keys."""
    # Check the document actually exists before attempting cleanup
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"No record found for '{doc_id}'")

    # 1. Remove all chunks for this doc from ChromaDB
    vs = get_vectorstore()
    results = vs._collection.get(where={"doc_id": doc_id})
    if results["ids"]:
        vs._collection.delete(ids=results["ids"])
        logger.info("Deleted %d chunks from ChromaDB for %s", len(results["ids"]), doc_id)

    # 2. Remove file hash from global content-hash registry so the same
    #    PDF can be re-ingested under a new name later without being blocked
    file_hash = status.get("file_hash")
    if file_hash:
        redis.hdel("ingest:content_hashes", file_hash)

    # 3. Clean up all per-document Redis keys
    redis.delete(f"ingest_status:{doc_id}")
    redis.delete(f"doc_chunks:{doc_id}")
    redis.srem("ingest:doc_ids", doc_id)

    logger.info("Deleted document %s", doc_id)
    return {"status": "deleted", "doc_id": doc_id}
