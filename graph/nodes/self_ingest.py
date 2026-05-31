import logging

from langchain_core.documents import Document

from config import LEARNING_MODES, get_settings
from db.vector import get_synthesized_vectorstore
from services.review_service import enqueue, make_entry_id

logger = logging.getLogger(__name__)


def self_ingest(state):
    chat_mode = state.get("chat_mode", "strict")
    if chat_mode not in LEARNING_MODES:
        return {"self_ingested": False}

    settings = get_settings()
    best_score = state.get("best_score", 0.0)
    threshold = settings.retrieval_score_threshold
    answer = state.get("last_answer", "")
    question = state["question"]
    min_length = settings.self_ingest_min_length

    # Only ingest when no documents matched (filling knowledge gaps)
    # AND the answer is substantive enough to be worth storing
    if best_score >= threshold:
        logger.info("Self-ingest skipped: docs were found (score=%.3f)", best_score)
        return {"self_ingested": False}

    if len(answer.strip()) < min_length:
        logger.info("Self-ingest skipped: answer too short (%d chars)", len(answer.strip()))
        return {"self_ingested": False}

    # `learning_review` is two-phase: queue for human review instead of embedding, so
    # unverified synthesized content never enters the vector store until a moderator
    # approves it (see services.review_service).
    if chat_mode == "learning_review":
        entry_id = enqueue(question, answer.strip(), best_score)
        logger.info("Self-ingest queued '%s' for review (score=%.3f)", entry_id, best_score)
        return {"self_ingested": True, "pending_review": True, "review_entry_id": entry_id}

    # `learning`: embed immediately into the SEPARATE synthesized collection.
    doc_id = make_entry_id(question, answer.strip())
    doc = Document(
        page_content=answer.strip(),
        metadata={
            "source": doc_id,
            "source_type": "synthesized",
            "source_question": question,
            "best_score": best_score,
        },
    )
    get_synthesized_vectorstore().add_documents([doc])
    logger.info(
        "Self-ingested synthesized answer as '%s' (score=%.3f, %d chars)", doc_id, best_score, len(answer.strip())
    )
    return {"self_ingested": True, "pending_review": False}
