import hashlib
import logging

from langchain_core.documents import Document

from config import get_settings
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def self_ingest(state):
    chat_mode = state.get("chat_mode", "strict")
    if chat_mode != "learning":
        return {"self_ingested": False}

    best_score = state.get("best_score", 0.0)
    threshold = get_settings().retrieval_score_threshold
    answer = state.get("last_answer", "")
    question = state["question"]
    min_length = get_settings().self_ingest_min_length

    # Only ingest when no documents matched (filling knowledge gaps)
    # AND the answer is substantive enough to be worth storing
    if best_score >= threshold:
        logger.info("Self-ingest skipped: docs were found (score=%.3f)", best_score)
        return {"self_ingested": False}

    if len(answer.strip()) < min_length:
        logger.info("Self-ingest skipped: answer too short (%d chars)", len(answer.strip()))
        return {"self_ingested": False}

    # Create a document from the synthesized answer
    doc_id = f"synthesized:{hashlib.sha256((question + answer).encode()).hexdigest()[:12]}"
    doc = Document(
        page_content=answer.strip(),
        metadata={
            "source": doc_id,
            "source_type": "synthesized",
            "source_question": question,
            "best_score": best_score,
        },
    )

    vs = get_vectorstore()
    vs.add_documents([doc])

    logger.info(
        "Self-ingested synthesized answer as '%s' (score=%.3f, %d chars)", doc_id, best_score, len(answer.strip())
    )
    return {"self_ingested": True}
