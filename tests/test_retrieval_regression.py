"""Hermetic retrieval-regression test (#19).

Seeds a tiny labeled corpus into a real (temp) Chroma using the **real FastEmbed** model
CI already uses (``BAAI/bge-small-en-v1.5`` — deterministic, offline once cached) and
asserts that each query retrieves its expected chunk within ``top_k`` (recall@k) and that
the best relevance score clears a floor.

This catches silent retrieval regressions (a detuned ``top_k``/threshold/embedding model
or a broken ``retrieve_context``) that the otherwise-mocked suite cannot. Marked
``@pytest.mark.retrieval`` so it can be selected/deselected; it stays in the default run
because it is fast. Skips cleanly when the embedding model cannot be loaded (e.g. offline
on first run), so it never makes a hermetic, network-less environment fail.
"""

from unittest.mock import patch

import pytest
from langchain_core.documents import Document

pytestmark = pytest.mark.retrieval

# (doc_id, chunk text) — deliberately separable knowledge-base topics so recall@k is a
# stable signal (the goal is to catch regressions, not to benchmark a near-duplicate corpus).
_CORPUS = [
    ("returns", "Customers may return any item within 30 days of purchase for a full refund."),
    ("shipping", "Standard shipping takes 5 to 7 business days; express shipping delivers within 2 to 3 days."),
    ("privacy", "We never sell your personal data and you may request deletion of your data at any time."),
    ("warranty", "Products include a twelve month manufacturer warranty against defects."),
    ("payment", "We accept Visa, Mastercard, and PayPal, and all invoices are issued in US dollars."),
    ("support", "Contact our customer support team by email at help@example.com for assistance."),
]

# (query, expected doc_id) — paraphrased so this exercises semantic recall, not echo.
_QUERIES = [
    ("how many days do I have to return an item?", "returns"),
    ("how long does delivery of my order take?", "shipping"),
    ("do you sell my personal information to anyone?", "privacy"),
    ("is there a guarantee against defects?", "warranty"),
    ("which credit cards can I pay with?", "payment"),
    ("how do I reach customer support?", "support"),
]

_SCORE_FLOOR = 0.1
_TOP_K = 3


@pytest.fixture(scope="module")
def seeded_vectorstore(tmp_path_factory):
    """Build a temp Chroma seeded with the labeled corpus using the real embedding model."""
    try:
        from langchain_chroma import Chroma

        from utils.embedding_adapter import get_embeddings

        vs = Chroma(
            collection_name="regression",
            persist_directory=str(tmp_path_factory.mktemp("chroma_regression")),
            embedding_function=get_embeddings(),
            collection_metadata={"hnsw:space": "cosine"},
        )
        vs.add_documents(
            [
                Document(
                    page_content=text,
                    metadata={"doc_id": doc_id, "source_file": f"{doc_id}.pdf", "chunk_hash": doc_id},
                )
                for doc_id, text in _CORPUS
            ]
        )
        return vs
    except Exception as e:  # pragma: no cover - environment-dependent (offline model fetch)
        pytest.skip(f"FastEmbed model unavailable for retrieval regression test: {e}")


@pytest.mark.parametrize("query,expected_doc_id", _QUERIES)
def test_query_retrieves_expected_chunk(seeded_vectorstore, query, expected_doc_id):
    from graph.nodes.retrieve_context import retrieve_context

    with patch("graph.nodes.retrieve_context.get_vectorstore", return_value=seeded_vectorstore):
        # threshold 0 forces the MMR retrieval path (the real selector) for every query.
        result = retrieve_context({"question": query, "chat_mode": "strict", "top_k": _TOP_K, "score_threshold": 0.0})

    retrieved_ids = [s.get("doc_id") for s in result["sources"]]
    assert expected_doc_id in retrieved_ids, f"{expected_doc_id!r} not in top-{_TOP_K} for {query!r}: {retrieved_ids}"
    assert result["best_score"] >= _SCORE_FLOOR
