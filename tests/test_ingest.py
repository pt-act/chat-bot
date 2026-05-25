"""
Test suite for ingest/policies.py

Each test covers one specific behaviour of the ingest pipeline.
Run with:  pytest -v
"""

import pytest
import responses as resp

from ingest.policies import process_policy

# These are fake S3 URLs. The `responses` library intercepts requests.get()
# and returns our PDF bytes instead — no real network call is made.
URL_V1 = "https://test-bucket.s3.amazonaws.com/return_policy_v1.pdf"
URL_V2 = "https://test-bucket.s3.amazonaws.com/return_policy_v2.pdf"
FILE_NAME = "return_policy"


# ── 1. Fresh ingest ───────────────────────────────────────────────────────────

@resp.activate
def test_fresh_ingest_adds_all_chunks(pdf_v1_bytes, ingest_env):
    """
    First time a document is ingested — every chunk is new.
    Expected: status=done, added > 0, removed = 0.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    result = process_policy(FILE_NAME, URL_V1)

    assert result["status"] == "done"
    assert result["added"] > 0
    assert result["removed"] == 0
    # on a fresh ingest, everything added = everything total
    assert result["added"] == result["total"]


# ── 2. Unchanged file ─────────────────────────────────────────────────────────

@resp.activate
def test_same_file_is_skipped(pdf_v1_bytes, ingest_env):
    """
    Upload the exact same file twice.
    Second call should be skipped — file hash hasn't changed, no work needed.
    """
    # register the same URL twice (responses consumes one per call)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)          # first ingest
    result = process_policy(FILE_NAME, URL_V1)  # same file again

    assert result["status"] == "skipped"
    assert result["reason"] == "file unchanged"


# ── 3. Updated file — stale chunks removed ───────────────────────────────────

@resp.activate
def test_update_removes_stale_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """
    Upload v1, then upload v2 (two paragraphs changed).
    The chunks from v1 that no longer exist in v2 must be deleted from ChromaDB.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    assert result_v2["status"] == "done"
    assert result_v2["removed"] > 0   # stale chunks were deleted


# ── 4. Updated file — only new chunks added ───────────────────────────────────

@resp.activate
def test_update_adds_only_changed_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """
    Upload v1, then v2.
    added should be less than total — unchanged chunks are skipped (not re-embedded).
    This is the core cost-saving behaviour of the diff logic.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    # some chunks are identical between v1 and v2 — they are skipped
    assert result_v2["added"] < result_v2["total"]


# ── 5. Re-upload v2 after v2 — should skip ───────────────────────────────────

@resp.activate
def test_second_update_with_same_file_is_skipped(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """
    v1 → v2 → v2 again.
    Third call should be skipped — v2 hash is already stored.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    process_policy(FILE_NAME, URL_V2)
    result = process_policy(FILE_NAME, URL_V2)  # same as v2 again

    assert result["status"] == "skipped"


# ── 6. Redis — status is saved ────────────────────────────────────────────────

@resp.activate
def test_redis_saves_ingest_status(pdf_v1_bytes, ingest_env):
    """
    After ingest, Redis must hold the document's status.
    This powers the GET /ingest/status/{doc_id} endpoint.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")

    assert status["status"] == "done"
    assert "file_hash" in status
    assert "version" in status
    assert "total_chunks" in status


# ── 7. Redis — doc appears in global list ────────────────────────────────────

@resp.activate
def test_redis_adds_doc_to_global_list(pdf_v1_bytes, ingest_env):
    """
    After ingest, the doc_id must appear in the 'ingest:doc_ids' set.
    This powers the GET /ingest/docs endpoint.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    all_docs = fake_redis.smembers("ingest:doc_ids")
    assert FILE_NAME in all_docs


# ── 8. Redis — chunk hashes stored ───────────────────────────────────────────

@resp.activate
def test_redis_stores_chunk_hashes(pdf_v1_bytes, ingest_env):
    """
    Every chunk hash must be saved in Redis so the next ingest can diff against it.
    The number of stored hashes must equal the total chunks produced.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    result = process_policy(FILE_NAME, URL_V1)

    stored_hashes = fake_redis.smembers(f"doc_chunks:{FILE_NAME}")
    assert len(stored_hashes) == result["total"]


# ── 9. ChromaDB — chunk metadata is correct ──────────────────────────────────

@resp.activate
def test_chunks_have_correct_metadata(pdf_v1_bytes, ingest_env):
    """
    Every chunk stored in ChromaDB must carry metadata fields that let us:
    - find all chunks for a document  (doc_id)
    - diff individual chunks          (chunk_hash)
    - know when it was ingested       (version)
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    _, vectorstore = ingest_env

    process_policy(FILE_NAME, URL_V1)

    results = vectorstore._collection.get(where={"doc_id": FILE_NAME})
    assert len(results["ids"]) > 0

    for meta in results["metadatas"]:
        assert meta["doc_id"] == FILE_NAME
        assert meta["source_file"] == FILE_NAME
        assert "chunk_hash" in meta
        assert "version" in meta
        assert "page_number" in meta


# ── 10. ChromaDB — stale chunks are gone after update ────────────────────────

@resp.activate
def test_stale_chunks_removed_from_chromadb(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """
    After updating from v1 to v2, querying ChromaDB for the doc's chunks
    should return the v2 count, not v1 count.
    Old chunks must be physically deleted, not just ignored.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    _, vectorstore = ingest_env

    result_v1 = process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    # check actual ChromaDB state
    in_db = vectorstore._collection.get(where={"doc_id": FILE_NAME})
    chunks_in_db = len(in_db["ids"])

    # ChromaDB should hold exactly the v2 total — no leftover v1 chunks
    assert chunks_in_db == result_v2["total"]


# ── 11. Error — download failure ─────────────────────────────────────────────

@resp.activate
def test_download_failure_raises_runtime_error(ingest_env):
    """
    If the S3 URL returns a non-200 status, process_policy must raise RuntimeError.
    We use a 403 Forbidden to simulate a bad/expired pre-signed URL.
    """
    resp.add(resp.GET, URL_V1, status=403)

    with pytest.raises(RuntimeError, match="Failed to download"):
        process_policy(FILE_NAME, URL_V1)


# ── 12. Error — failed status saved to Redis ─────────────────────────────────

@resp.activate
def test_failed_ingest_status_saved_to_redis(ingest_env):
    """
    Even when ingest fails, the failure must be recorded in Redis.
    This lets operators query GET /ingest/status/{doc_id} and see what went wrong.
    """
    resp.add(resp.GET, URL_V1, status=500)
    fake_redis, _ = ingest_env

    with pytest.raises(RuntimeError):
        process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")
    assert status.get("status") == "failed"
    assert "error" in status


# ── 13. Error — file too large ────────────────────────────────────────────────

@resp.activate
def test_file_too_large_raises_error(pdf_v1_bytes, ingest_env):
    """
    If the downloaded file exceeds max_file_size_mb, raise RuntimeError.
    We patch get_settings() to set the limit to 0 MB so any file triggers it.
    """
    from unittest.mock import patch, MagicMock
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    # create a fake settings object with a 0 MB file size limit
    fake_settings = MagicMock()
    fake_settings.max_file_size_mb = 0
    fake_settings.download_timeout_seconds = 30

    with patch("ingest.policies.get_settings", return_value=fake_settings):
        with pytest.raises(RuntimeError, match="exceeds"):
            process_policy(FILE_NAME, URL_V1)


# ── 14. Global duplicate — same content, different file_name ─────────────────

@resp.activate
def test_duplicate_content_different_filename_is_skipped(pdf_v1_bytes, ingest_env):
    """
    Ingest "return_policy", then try to ingest "terms_copy" with the exact same PDF.
    The global content hash registry must catch this and return skipped,
    even though the file_name is different.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)                    # ingest as "return_policy"
    result = process_policy("terms_copy", URL_V1)        # same content, different name

    assert result["status"] == "skipped"
    assert FILE_NAME in result["reason"]                 # tells us which doc already has it


# ── 15. Global hash registered after ingest ───────────────────────────────────

@resp.activate
def test_global_content_hash_registered(pdf_v1_bytes, ingest_env):
    """
    After a successful ingest, the file hash must be stored in the global
    'ingest:content_hashes' registry so future duplicate checks work.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    # the global registry maps file_hash → doc_id
    registered_doc = fake_redis.hgetall("ingest:content_hashes")
    assert FILE_NAME in registered_doc.values()


# ── 16. Old global hash removed when doc content changes ─────────────────────

@resp.activate
def test_old_global_hash_removed_on_update(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """
    When a document is updated (v1 → v2), the old file hash must be removed
    from the global registry. Otherwise the old hash would block a new document
    with v1's content from ever being ingested.
    """
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)  # ingest v1

    # grab the v1 hash before updating
    v1_hash = fake_redis.hget(f"ingest_status:{FILE_NAME}", "file_hash")

    process_policy(FILE_NAME, URL_V2)  # update to v2

    # v1 hash must be gone from the global registry
    assert fake_redis.hget("ingest:content_hashes", v1_hash) is None

    # v2 hash must now be registered
    registered = fake_redis.hgetall("ingest:content_hashes")
    assert FILE_NAME in registered.values()
