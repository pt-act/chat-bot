import logging

from config import LEARNING_MODES, get_settings
from db.vector import get_synthesized_vectorstore, get_vectorstore

logger = logging.getLogger(__name__)

_SNIPPET_LEN = 200


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


def _snippet(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _SNIPPET_LEN:
        return text
    return text[:_SNIPPET_LEN].rsplit(" ", 1)[0] + "…"


def _label_of(meta: dict) -> str:
    # Ingested policy chunks store the filename under ``source_file``; synthesized
    # chunks use ``source``. Check both so sources are never silently "unknown".
    return meta.get("source_file") or meta.get("source") or "unknown"


def _to_source(doc, score: float | None = None) -> dict:
    """Build a structured citation from a retrieved chunk (see schemas.responses.Source)."""
    meta = doc.metadata or {}
    return {
        "label": _label_of(meta),
        "doc_id": meta.get("doc_id") or meta.get("source"),
        "score": round(float(score), 4) if score is not None else None,
        "page": meta.get("page_number"),
        "snippet": _snippet(doc.page_content),
    }


def _dedup(sources: list[dict]) -> list[dict]:
    """De-duplicate by (doc_id, label, page), keeping first occurrence (highest score)."""
    seen, out = set(), []
    for s in sources:
        key = (s.get("doc_id"), s.get("label"), s.get("page"))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _score_key(doc) -> str:
    """Stable key for matching a retrieved document back to its relevance score.

    Ingested chunks carry a unique ``chunk_hash``; fall back to page_content
    (e.g. synthesized docs) when absent.
    """
    meta = getattr(doc, "metadata", None) or {}
    return meta.get("chunk_hash") or getattr(doc, "page_content", str(doc))


def retrieve_context(state):
    # Search on the condensed, self-contained query when available (#1); fall back to the
    # raw question. Generation still uses state["question"], so display/citations are
    # unaffected by query rewriting.
    question = state.get("search_query") or state["question"]
    settings = get_settings()
    threshold = state.get("score_threshold")
    if threshold is None:
        threshold = settings.retrieval_score_threshold
    top_k = state.get("top_k") or 3
    # Candidate pool for the relevance gate and MMR's fetch_k (>= the documented 10).
    fetch_k = max(10, top_k * 4)
    chat_mode = state.get("chat_mode", "strict")
    vs = get_vectorstore()

    # Step 1 — relevance gate + per-chunk scores. Score the candidate pool once, then
    # reuse it to (a) decide the gate via the top score and (b) attach relevance scores
    # to whichever chunks MMR selects (so citations keep their scores).
    scored = vs.similarity_search_with_relevance_scores(question, k=fetch_k)
    best_score = scored[0][1] if scored else 0.0

    # Strict mode: block below threshold (no context → refusal prompt)
    if chat_mode == "strict" and best_score < threshold:
        logger.info("Best score %.3f below threshold %.2f; returning no docs", best_score, threshold)
        return {"docs": "", "sources": [], "best_score": best_score}

    # chunk -> relevance score, used to annotate whichever chunks we ultimately cite.
    score_map = {_score_key(doc): s for doc, s in scored}

    # Open/learning mode with low scores: provide best available matches (may be weak)
    if chat_mode != "strict" and best_score < threshold:
        docs = vs.similarity_search(question, k=top_k)
        # Learning modes additionally draw on previously synthesized answers, which
        # live in a separate collection. Strict/open never see synthesized content.
        if chat_mode in LEARNING_MODES:
            docs = docs + _search_synthesized(question, k=top_k)
        context = "\n\n".join(d.page_content for d in docs) if docs else ""
        sources = _dedup([_to_source(d, score_map.get(_score_key(d))) for d in docs])
        logger.info("Open/learning mode: providing %d low-score docs (best=%.3f)", len(docs), best_score)
        return {"docs": context, "sources": sources, "best_score": best_score}

    # Step 2 — above threshold: select diverse, non-redundant chunks. Default `mmr`
    # (unchanged). `hybrid`/`hybrid_rerank` fuse dense + BM25 lexical recall (Phase 4),
    # gated by retrieval_strategy. Per-citation scores come from the candidate pool above.
    results = _select_documents(vs, question, top_k, fetch_k, getattr(settings, "retrieval_strategy", "mmr"))
    context = "\n\n".join(d.page_content for d in results)
    sources = _dedup([_to_source(d, score_map.get(_score_key(d))) for d in results])
    logger.info("Retrieved %d chunks (best=%.3f, fetch_k=%d)", len(results), best_score, fetch_k)
    return {"docs": context, "sources": sources, "best_score": best_score}


def _select_documents(vs, question: str, top_k: int, fetch_k: int, strategy: str) -> list:
    """Dispatch to the configured retrieval strategy (default MMR — behavior-preserving)."""
    if strategy in ("hybrid", "hybrid_rerank"):
        from ingest.retrieval import hybrid_retrieve, rerank

        results = hybrid_retrieve(vs, question, k=top_k, fetch_k=fetch_k)
        if strategy == "hybrid_rerank":
            results = rerank(question, results, top_k)
        return results
    return vs.max_marginal_relevance_search(question, k=top_k, fetch_k=fetch_k)
