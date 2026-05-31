"""Tests for graph.nodes.verify_answer — groundedness / faithfulness verification (#2)."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from graph.nodes.verify_answer import verify_answer


def _settings(enabled=True, mode="heuristic", min_score=0.5, strict_refuse=True, escalation="Please contact support."):
    return MagicMock(
        groundedness_enabled=enabled,
        groundedness_mode=mode,
        groundedness_min_score=min_score,
        strict_refuse_on_ungrounded=strict_refuse,
        escalation_message=escalation,
    )


_DOCS = "Our return policy: returns are accepted within 30 days of purchase for a full refund."


class TestVerifyHeuristic:
    @patch("graph.nodes.verify_answer.get_settings")
    def test_faithful_answer_is_supported(self, mock_settings):
        mock_settings.return_value = _settings()
        state = {
            "chat_mode": "open",
            "docs": _DOCS,
            "last_answer": "Returns are accepted within 30 days of purchase.",
        }
        result = verify_answer(state)
        assert result["grounded"] == "supported"
        assert result["grounded_score"] >= 0.5
        assert "last_answer" not in result  # open mode never overrides

    @patch("graph.nodes.verify_answer.get_settings")
    def test_unrelated_answer_is_unsupported(self, mock_settings):
        mock_settings.return_value = _settings()
        state = {
            "chat_mode": "open",
            "docs": _DOCS,
            "last_answer": "The mitochondria is the powerhouse of the cell.",
        }
        result = verify_answer(state)
        assert result["grounded"] == "unsupported"
        assert result["grounded_score"] == 0.0

    @patch("graph.nodes.verify_answer.get_settings")
    def test_strict_unsupported_is_refused(self, mock_settings):
        mock_settings.return_value = _settings()
        state = {
            "chat_mode": "strict",
            "docs": _DOCS,
            "last_answer": "The mitochondria is the powerhouse of the cell.",
            "sources": [{"label": "x.pdf"}],
            "messages": [HumanMessage(content="q"), AIMessage(content="The mitochondria...")],
        }
        result = verify_answer(state)
        assert result["grounded"] == "unsupported"
        expected_refusal = "I don't have information about that in our knowledge base. Please contact support."
        assert result["last_answer"] == expected_refusal
        assert result["sources"] == []
        # Stored AI message rewritten to the refusal so memory never keeps the hallucination.
        assert result["messages"][-1].content == result["last_answer"]

    @patch("graph.nodes.verify_answer.get_settings")
    def test_strict_unsupported_not_refused_when_disabled(self, mock_settings):
        mock_settings.return_value = _settings(strict_refuse=False)
        state = {
            "chat_mode": "strict",
            "docs": _DOCS,
            "last_answer": "The mitochondria is the powerhouse of the cell.",
        }
        result = verify_answer(state)
        assert result["grounded"] == "unsupported"
        assert "last_answer" not in result

    @patch("graph.nodes.verify_answer.get_settings")
    def test_disabled_is_noop(self, mock_settings):
        mock_settings.return_value = _settings(enabled=False)
        assert verify_answer({"chat_mode": "strict", "docs": _DOCS, "last_answer": "x"}) == {}

    @patch("graph.nodes.verify_answer.get_settings")
    def test_no_docs_is_noop(self, mock_settings):
        mock_settings.return_value = _settings()
        assert verify_answer({"chat_mode": "strict", "docs": "", "last_answer": "x"}) == {}


class TestVerifyLLM:
    @patch("graph.nodes.verify_answer._get_judge")
    @patch("graph.nodes.verify_answer.get_settings")
    def test_llm_grounded_true_supported(self, mock_settings, mock_judge):
        mock_settings.return_value = _settings(mode="llm")
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content='{"grounded": true, "unsupported_claims": []}')
        mock_judge.return_value = llm

        result = verify_answer({"chat_mode": "open", "docs": _DOCS, "last_answer": "anything"})
        assert result["grounded"] == "supported"
        assert result["grounded_score"] == 1.0

    @patch("graph.nodes.verify_answer._get_judge")
    @patch("graph.nodes.verify_answer.get_settings")
    def test_llm_grounded_false_unsupported(self, mock_settings, mock_judge):
        mock_settings.return_value = _settings(mode="llm")
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content='Here: {"grounded": false, "unsupported_claims": ["c"]}')
        mock_judge.return_value = llm

        result = verify_answer({"chat_mode": "open", "docs": _DOCS, "last_answer": "anything"})
        assert result["grounded"] == "unsupported"
        assert result["grounded_score"] == 0.0
