"""Single source of truth for ingest-related Redis keys.

Previously these constants were duplicated in ingest/policies.py and
controllers/ingest_controller.py, which risked the two drifting apart.
"""

ALL_DOCS_KEY = "ingest:doc_ids"
CONTENT_HASHES_KEY = "ingest:content_hashes"


def ingest_status_key(doc_id: str) -> str:
    return f"ingest_status:{doc_id}"


def doc_chunks_key(doc_id: str) -> str:
    return f"doc_chunks:{doc_id}"
