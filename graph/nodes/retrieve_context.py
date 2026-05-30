import logging

from config import get_settings
from db.vector import get_synthesized_vectorstore, get_vectorstore

logger = logging.getLogger(__name__)


def _search_synthesized(question: str, k: int = 3) -> list:
    """Best-effort lookup of previously self-ingested answers (learning mode only).

    Lives in a separate Chroma collection (see db.vector.get_synthesized_vectorstore).
    Returns [] on any error (e.g. the collection does not exist yet) so retrieval
    never fails because of the optional synthesized store.
    """
    try:
        return get_synthesized_vectorstore().similarity_search(question, k=k)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Synthesized-store lookup failed: %s", e)
        return []


def _source_of(doc) -> str:
    """Resolve a human-readable source label for a retrieved chunk.

    Ingested policy chunks store the filename under ``source_file`` (see
    ingest.policies._build_chunks), while self-ingested/synthesized chunks use
    ``source``. Check both so the API never silently reports ``unknown`` for
    real documents.
    """
    meta = doc.metadata or {}
    return meta.get("source_file") or meta.get("source") or "unknown"


def retrieve_context(state):
    question = state["question"]
    threshold = get_settings().retrieval_score_threshold
    chat_mode = state.get("chat_mode", "strict")
    vs = get_vectorstore()

    top = vs.similarity_search_with_relevance_scores(question, k=1)
    best_score = top[0][1] if top else 0.0

    # Strict mode: block below threshold (no context → refusal prompt)
    if chat_mode == "strict" and best_score < threshold:
        logger.info("Best score %.3f below threshold %.2f; returning no docs", best_score, threshold)
        return {"docs": "", "sources": [], "best_score": best_score}

    # Open/learning mode with low scores: provide best available matches (may be weak)
    if chat_mode != "strict" and best_score < threshold:
        docs = vs.similarity_search(question, k=3)
        # Learning mode additionally draws on previously synthesized answers, which
        # live in a separate collection. Strict/open never see synthesized content.
        if chat_mode == "learning":
            docs = docs + _search_synthesized(question, k=3)
        context = "\n\n".join(d.page_content for d in docs) if docs else ""
        sources = list({_source_of(d) for d in docs}) if docs else []
        logger.info("Open/learning mode: providing %d low-score docs (best=%.3f)", len(docs), best_score)
        return {"docs": context, "sources": sources, "best_score": best_score}

    # Above threshold: MMR for diverse, relevant results
    results = vs.max_marginal_relevance_search(question, k=3, fetch_k=10)
    context = "\n\n".join(d.page_content for d in results)
    sources = list({_source_of(d) for d in results})
    logger.info("Retrieved %d chunks via MMR (best score: %.3f)", len(results), best_score)
    return {"docs": context, "sources": sources, "best_score": best_score}
