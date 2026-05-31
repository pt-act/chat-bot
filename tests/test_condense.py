"""Tests for graph.nodes.condense_query — context-aware query rewriting (#1)."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from graph.nodes.condense_query import condense_query


def _settings(enabled=True):
    return MagicMock(query_rewrite_enabled=enabled)


class TestCondenseQuery:
    @patch("graph.nodes.condense_query.get_settings")
    @patch("graph.nodes.condense_query._get_condenser")
    def test_first_turn_passthrough_no_llm(self, mock_condenser, mock_settings):
        mock_settings.return_value = _settings(True)
        result = condense_query({"question": "what is the return policy?"})
        assert result == {"search_query": "what is the return policy?"}
        mock_condenser.assert_not_called()  # no prior context → no LLM call

    @patch("graph.nodes.condense_query.get_settings")
    @patch("graph.nodes.condense_query._get_condenser")
    def test_flag_off_passthrough(self, mock_condenser, mock_settings):
        mock_settings.return_value = _settings(False)
        state = {
            "question": "and damaged ones?",
            "messages": [HumanMessage(content="return policy?"), AIMessage(content="30 days")],
            "summary": "discussing returns",
        }
        assert condense_query(state) == {"search_query": "and damaged ones?"}
        mock_condenser.assert_not_called()

    @patch("graph.nodes.condense_query.get_settings")
    @patch("graph.nodes.condense_query._get_condenser")
    def test_with_history_uses_rewritten_query(self, mock_condenser, mock_settings):
        mock_settings.return_value = _settings(True)
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="return policy for damaged items")
        mock_condenser.return_value = llm

        state = {
            "question": "and what about damaged ones?",
            "messages": [HumanMessage(content="what is the return policy?"), AIMessage(content="30 days")],
            "summary": "",
        }
        result = condense_query(state)
        assert result == {"search_query": "return policy for damaged items"}
        llm.invoke.assert_called_once()

    @patch("graph.nodes.condense_query.get_settings")
    @patch("graph.nodes.condense_query._get_condenser")
    def test_empty_rewrite_falls_back_to_question(self, mock_condenser, mock_settings):
        mock_settings.return_value = _settings(True)
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="   ")
        mock_condenser.return_value = llm

        state = {
            "question": "original question",
            "messages": [HumanMessage(content="a"), AIMessage(content="b")],
            "summary": "",
        }
        assert condense_query(state) == {"search_query": "original question"}

    @patch("graph.nodes.condense_query.get_settings")
    @patch("graph.nodes.condense_query._get_condenser")
    def test_summary_only_context_triggers_rewrite(self, mock_condenser, mock_settings):
        mock_settings.return_value = _settings(True)
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="rewritten")
        mock_condenser.return_value = llm
        # No messages but a rolling summary still counts as prior context.
        result = condense_query({"question": "and then?", "messages": [], "summary": "prior context"})
        assert result == {"search_query": "rewritten"}
        llm.invoke.assert_called_once()
