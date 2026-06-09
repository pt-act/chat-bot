"""Retrieval strategies: hybrid (dense + BM25/RRF) and hierarchical (L1/L2-aware).

``hybrid`` recovers lexical recall for acronyms / SKUs / exact phrases that dense
embeddings miss, by fusing the dense ranking with a BM25 ranking over the collection
via RRF.  ``hybrid_rerank`` additionally passes the fused candidates through
:func:`rerank` (identity passthrough by default — swap in a real reranker once #19
shows the precision lift justifies it).

``hierarchical`` is element-type-aware: it boosts table chunks for table-like queries,
prefers L1 section chunks for overview queries, and expands L2 results to their L1
parent inline when the result set has room.

Adopt non-default strategies only with evidence: the hermetic retrieval-regression test
(#19) and the eval harness exist precisely to prove a lift before turning a strategy on
in production.
"""

import logging

from langchain_core.documents import Document

from db.vector import VectorStoreRepository

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(result_lists: list[list[str]], k: int = 60) -> list[str]:
    """Fuse several ranked id lists into one. RRF score = Σ 1/(k + rank). Deterministic."""
    scores: dict[str, float] = {}
    for ranked in result_lists:
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return [item for item, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


def _doc_key(doc: Document) -> str:
    meta = getattr(doc, "metadata", None) or {}
    return meta.get("chunk_hash") or getattr(doc, "page_content", str(doc))


def _bm25_rank(query: str, ids: list[str], texts: list[str], metas: list[dict], top_n: int) -> list[Document]:
    """Rank the collection's chunks lexically with BM25; return the top_n as Documents."""
    if not texts:
        return []
    from rank_bm25 import BM25Okapi

    tokenized = [(t or "").lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores((query or "").lower().split())
    order = sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)[:top_n]
    out = []
    for i in order:
        meta = dict(metas[i]) if i < len(metas) and metas[i] else {}
        meta.setdefault("chunk_hash", ids[i] if i < len(ids) else None)
        out.append(Document(page_content=texts[i], metadata=meta))
    return out


def hybrid_retrieve(vs, query: str, k: int = 3, fetch_k: int = 10) -> list[Document]:
    """Dense + BM25 candidates fused with RRF; returns the top_k fused Documents."""
    dense_docs = vs.similarity_search(query, k=fetch_k)

    repo = VectorStoreRepository(vs)
    data = repo.all_chunks()
    lexical_docs = _bm25_rank(
        query,
        data.get("ids", []) or [],
        data.get("documents", []) or [],
        data.get("metadatas", []) or [],
        top_n=fetch_k,
    )

    docmap: dict[str, Document] = {}
    for d in [*dense_docs, *lexical_docs]:
        docmap.setdefault(_doc_key(d), d)

    fused_ids = reciprocal_rank_fusion([[_doc_key(d) for d in dense_docs], [_doc_key(d) for d in lexical_docs]])
    fused = [docmap[i] for i in fused_ids if i in docmap]
    logger.info("Hybrid retrieve: %d dense + %d lexical → %d fused", len(dense_docs), len(lexical_docs), len(fused))
    return fused[:k]


def rerank(query: str, docs: list[Document], top_k: int) -> list[Document]:
    """Rerank hook for ``hybrid_rerank`` (config-selectable reranker integration point).

    Default: identity passthrough trimmed to ``top_k`` — no external dependency. Replace
    with a FastEmbed/LLM/API reranker once #19 shows the precision lift justifies it.
    """
    return docs[:top_k]


# ---------------------------------------------------------------------------
# Hierarchical retrieval (Group 5)
# ---------------------------------------------------------------------------

# Keyword sets for element-type heuristics.  Case-insensitive substring matching
# only — no regex, no user-supplied patterns (no ReDoS surface).
TABLE_QUERY_TERMS: frozenset[str] = frozenset(
    {
        "table",
        "row",
        "column",
        "compare",
        "vs",
        "versus",
        "list of",
    }
)
OVERVIEW_QUERY_TERMS: frozenset[str] = frozenset(
    {
        "overview",
        "summary",
        "introduction",
        "what is",
        "about",
    }
)


def hierarchical_retrieve(vs, query: str, k: int = 3, fetch_k: int = 10) -> list[Document]:
    """Element-type-aware retrieval over an L1/L2 hierarchical chunk store.

    Algorithm
    ---------
    1. Fetch ``fetch_k`` candidates from Chroma (returns both L1 and L2 chunks).
    2. Re-order candidates using keyword heuristics:
       - Table-like queries → table-typed L2 chunks move to the front.
       - Overview queries → L1 section chunks move to the front.
       - No match → original similarity order.
    3. Build result list from the re-ordered candidates, adding each doc once.
       When an L2 doc is added and its L1 parent is in the candidate pool but not
       yet in the result set *and* there is still room (``len < k``), the parent is
       appended immediately (inline context expansion).
    4. Return at most ``k`` documents.

    Chunks without ODL metadata (legacy) are tolerated: heuristics are silently
    skipped for them (no KeyError).
    """
    candidates: list[Document] = vs.similarity_search(query, k=fetch_k)

    q_lower = query.lower()
    is_table_query = any(term in q_lower for term in TABLE_QUERY_TERMS)
    is_overview_query = any(term in q_lower for term in OVERVIEW_QUERY_TERMS)

    # Build hash → doc lookup for context expansion (covers all fetch_k candidates).
    by_hash: dict[str, Document] = {}
    for doc in candidates:
        ch = doc.metadata.get("chunk_hash")
        if ch:
            by_hash[ch] = doc

    # Re-order by element-type heuristic (keyword-based, reversible, no regex).
    if is_table_query:
        boosted = [d for d in candidates if d.metadata.get("element_type") == "table"]
        rest = [d for d in candidates if d.metadata.get("element_type") != "table"]
        ordered = boosted + rest
    elif is_overview_query:
        boosted = [d for d in candidates if d.metadata.get("chunk_level") == 1]
        rest = [d for d in candidates if d.metadata.get("chunk_level") != 1]
        ordered = boosted + rest
    else:
        ordered = candidates

    # Build result list with inline L2 → L1 context expansion.
    seen: set = set()
    results: list[Document] = []

    for doc in ordered:
        if len(results) >= k:
            break

        doc_key = doc.metadata.get("chunk_hash") or id(doc)
        if doc_key in seen:
            continue
        results.append(doc)
        seen.add(doc_key)

        # Context expansion: when this is an L2 chunk whose parent is in the
        # candidate pool and hasn't been added yet, append it while room remains.
        parent_id = doc.metadata.get("parent_chunk_id")
        if doc.metadata.get("chunk_level") == 2 and parent_id and parent_id not in seen and len(results) < k:
            parent = by_hash.get(parent_id)
            if parent:
                results.append(parent)
                seen.add(parent_id)

    logger.info(
        "Hierarchical retrieve: %d candidates → %d results (k=%d, table=%s, overview=%s)",
        len(candidates),
        len(results),
        k,
        is_table_query,
        is_overview_query,
    )
    return results[:k]
