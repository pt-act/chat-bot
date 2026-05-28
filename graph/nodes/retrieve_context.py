import logging

from config import get_settings
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve_context(state):
    question = state["question"]
    threshold = get_settings().retrieval_score_threshold
    vs = get_vectorstore()

    top = vs.similarity_search_with_relevance_scores(question, k=1)
    if not top or top[0][1] < threshold:
        logger.info(
            "Best score %.3f is below threshold %.2f — returning no context",
            top[0][1] if top else 0.0,
            threshold,
        )
        return {"docs": "", "sources": []}

    docs = vs.max_marginal_relevance_search(
        question,
        k=3,
        fetch_k=10,
    )

    context = "\n\n".join(d.page_content for d in docs)
    sources = list({d.metadata.get("source_file", "unknown") for d in docs})

    logger.info(
        "Retrieved %d chunks via MMR from %s (best score: %.3f)",
        len(docs),
        sources,
        top[0][1],
    )
    return {"docs": context, "sources": sources}
