"""Tests for hybrid retrieval + RRF fusion (Phase 4)."""

from unittest.mock import MagicMock

from langchain_core.documents import Document

from ingest.retrieval import hybrid_retrieve, reciprocal_rank_fusion, rerank


class TestRRF:
    def test_fusion_is_deterministic(self):
        # a is top in both lists → highest; c appears in both → beats b (one list only).
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c"]])
        assert fused == ["a", "c", "b"]

    def test_empty_inputs(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[]]) == []


class TestHybridRetrieve:
    def test_keyword_only_query_recovered_by_bm25(self):
        # Dense retrieval misses the exact-code chunk; BM25 surfaces it; RRF keeps it.
        vs = MagicMock()
        vs.similarity_search.return_value = [
            Document(page_content="general information about our products", metadata={"chunk_hash": "a"}),
            Document(page_content="shipping and delivery details", metadata={"chunk_hash": "b"}),
        ]
        vs._collection.get.return_value = {
            "ids": ["a", "b", "c"],
            "documents": [
                "general information about our products",
                "shipping and delivery details",
                "Part XJ-9000 is compatible with model 5 only",
            ],
            "metadatas": [{"chunk_hash": "a"}, {"chunk_hash": "b"}, {"chunk_hash": "c"}],
        }

        results = hybrid_retrieve(vs, "XJ-9000", k=3, fetch_k=10)
        texts = [d.page_content for d in results]
        assert any("XJ-9000" in t for t in texts), texts
        # The dense-only result set did NOT contain it — hybrid is what recovered it.
        assert all("XJ-9000" not in d.page_content for d in vs.similarity_search.return_value)


class TestRerank:
    def test_identity_passthrough_trims_to_top_k(self):
        docs = [Document(page_content=str(i)) for i in range(5)]
        assert rerank("q", docs, 2) == docs[:2]
