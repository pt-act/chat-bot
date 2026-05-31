"""Regression tests for M-5: self-ingested (synthesized) content isolation.

Synthesized answers must live in a SEPARATE Chroma collection and must only
influence retrieval in learning mode — never in strict/open.
"""

from unittest.mock import MagicMock, patch

from graph.nodes.retrieve_context import retrieve_context


class TestSeparateCollection:
    @patch("db.vector.get_embeddings")
    @patch("db.vector.Chroma")
    @patch("db.vector.get_settings")
    def test_authoritative_and_synthesized_use_different_collections(self, mock_settings, mock_chroma, _embed):
        from db.vector import get_synthesized_vectorstore, get_vectorstore

        mock_settings.return_value = MagicMock(
            chroma_collection="policies",
            synthesized_collection="synthesized_answers",
            chroma_persist_dir="./chroma_db",
        )

        get_vectorstore()
        assert mock_chroma.call_args.kwargs["collection_name"] == "policies"

        get_synthesized_vectorstore()
        assert mock_chroma.call_args.kwargs["collection_name"] == "synthesized_answers"


class TestRetrievalIsolation:
    def _vs_below_threshold(self, weak_doc):
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.1)]
        vs.similarity_search.return_value = [weak_doc]
        return vs

    @patch("graph.nodes.retrieve_context.get_synthesized_vectorstore")
    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_learning_mode_includes_synthesized(self, mock_settings, mock_get_vs, mock_get_synth):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        weak = MagicMock(page_content="weak authoritative", metadata={"source_file": "policy.pdf"})
        mock_get_vs.return_value = self._vs_below_threshold(weak)

        synth_doc = MagicMock(page_content="previously synthesized", metadata={"source": "synthesized:abc"})
        synth = MagicMock()
        synth.similarity_search.return_value = [synth_doc]
        mock_get_synth.return_value = synth

        result = retrieve_context({"question": "q", "chat_mode": "learning"})
        assert "previously synthesized" in result["docs"]
        assert any(s["doc_id"] == "synthesized:abc" for s in result["sources"])
        synth.similarity_search.assert_called_once()

    @patch("graph.nodes.retrieve_context.get_synthesized_vectorstore")
    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_open_mode_never_touches_synthesized(self, mock_settings, mock_get_vs, mock_get_synth):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        weak = MagicMock(page_content="weak authoritative", metadata={"source_file": "policy.pdf"})
        mock_get_vs.return_value = self._vs_below_threshold(weak)

        result = retrieve_context({"question": "q", "chat_mode": "open"})
        assert result["docs"] == "weak authoritative"
        # Open mode must not consult the synthesized store at all.
        mock_get_synth.assert_not_called()

    @patch("graph.nodes.retrieve_context.get_synthesized_vectorstore")
    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_strict_mode_never_touches_synthesized(self, mock_settings, mock_get_vs, mock_get_synth):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.1)]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "q", "chat_mode": "strict"})
        assert result == {"docs": "", "sources": [], "best_score": 0.1}
        mock_get_synth.assert_not_called()
