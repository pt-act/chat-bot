"""Hybrid retrieval (dense + BM25) with Reciprocal Rank Fusion, plus a rerank hook.

Gated by ``RETRIEVAL_STRATEGY`` (default ``mmr`` — unchanged). ``hybrid`` recovers lexical
recall for acronyms / SKUs / exact phrases that dense embeddings miss, by fusing the dense
ranking with a BM25 ranking over the collection's chunk texts via RRF. ``hybrid_rerank``
additionally passes the fused candidates through :func:`rerank` (an integration point for a
local/LLM/API reranker — identity passthrough by default, so no extra dependency is pulled
unless you wire one in).

Adopt these only with evidence: the hermetic retrieval-regression test (#19) and the eval
harness exist precisely to prove a lift before turning the strategy on in production.
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
