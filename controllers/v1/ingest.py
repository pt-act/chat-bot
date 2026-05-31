"""v1 ingest controller — typed envelopes (IngestResult / DocsListResponse / DeleteResponse)."""

import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile

from config import get_settings
from db.redis_client import get_redis
from db.vector import delete_chunks_by_ids, get_chunks_by_doc_id, get_vectorstore
from ingest.keys import ALL_DOCS_KEY, CONTENT_HASHES_KEY, doc_chunks_key, ingest_status_key
from ingest.loaders import SUPPORTED_EXTENSIONS, detect_extension
from middlewares.auth import require_api_key
from schemas.ingest import IngestRequest, clean_file_name, sanitize_doc_id
from schemas.responses import DeleteResponse, DocsListResponse, IngestResult
from services.ingest_service import ingest_file, ingest_local_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])

_PDF_MAGIC = b"%PDF-"
_UPLOAD_READ_CHUNK = 1024 * 1024  # 1 MiB


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


def _save_upload_to_temp(file: UploadFile, ext: str, max_bytes: int) -> str:
    """Stream an upload to a temp file, enforcing the size cap (and a PDF magic check).

    Returns the temp path (caller/background task owns removal). Raises HTTPException
    (413 too large / 415 empty or not a PDF) and cleans up the temp file on rejection.
    Reads the upload's underlying sync file object so this runs in Starlette's threadpool
    (blocking disk I/O stays off the event loop). The PDF magic-byte check only applies to
    ``.pdf``; other formats are validated by extension and will surface loader errors as a
    `failed` ingest status if the content is malformed.
    """
    src = file.file  # underlying SpooledTemporaryFile
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    size = 0
    first = True
    try:
        with tmp:
            while chunk := src.read(_UPLOAD_READ_CHUNK):
                if first:
                    if ext == ".pdf" and not chunk.startswith(_PDF_MAGIC):
                        raise HTTPException(status_code=415, detail="File does not look like a valid PDF")
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds {max_bytes // (1024 * 1024)}MB limit")
                tmp.write(chunk)
        if first:  # no bytes read at all
            raise HTTPException(status_code=415, detail="Uploaded file is empty")
    except HTTPException:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
        raise
    finally:
        file.file.close()
    return tmp.name


@router.post(
    "/ingest/upload",
    response_model=IngestResult,
    response_model_exclude_none=True,
    status_code=202,
    dependencies=[Depends(require_api_key)],
    summary="Upload a local document for ingestion",
    description=(
        "Accepts a document uploaded directly from the client (multipart/form-data) — no "
        "URL required, so documents never leave the user's environment. Supported formats: "
        "PDF, TXT, Markdown, DOCX, HTML. Processes in the background; returns 202 with "
        "`status=queued`. Poll `GET /ingest/status/{doc_id}`."
    ),
)
def ingest_upload(
    background: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="The document to ingest (PDF, TXT, MD, DOCX, or HTML)."),
    file_name: str | None = Form(
        default=None, description="Optional doc id. Defaults to a sanitized form of the uploaded filename."
    ),
) -> IngestResult:
    ext = detect_extension(file.filename or "")
    if ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=415, detail=f"Unsupported format '{ext or file.filename}'. Supported: {allowed}"
        )

    # An explicit file_name is validated strictly (same contract as URL ingest); a name
    # derived from the upload filename is sanitized leniently so real filenames work.
    if file_name:
        try:
            doc_id = clean_file_name(file_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        doc_id = sanitize_doc_id(file.filename or "")

    settings = get_settings()
    file_path = _save_upload_to_temp(file, ext, settings.max_file_size_mb * 1024 * 1024)

    redis = get_redis()
    redis.hset(ingest_status_key(doc_id), mapping={"doc_id": doc_id, "status": "queued", "file_name": doc_id})
    redis.sadd(ALL_DOCS_KEY, doc_id)

    background.add_task(ingest_local_file, doc_id, file_path, ext)
    response.headers["Location"] = f"/api/v1/ingest/status/{doc_id}"
    logger.info("Queued uploaded ingest for %s (%s)", doc_id, ext)
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
