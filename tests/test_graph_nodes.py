"""
Unit tests for graph pipeline nodes.
Each node is tested in isolation with mocked dependencies.
"""

import json
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from graph.nodes.generate_answer import generate_answer
from graph.nodes.load_memory import load_memory
from graph.nodes.retrieve_context import retrieve_context
from graph.nodes.store_memory import store_memory
from graph.nodes.summarize import summarize

# ── load_memory ────────────────────────────────────────────────────────────────


class TestLoadMemory:
    @patch("graph.nodes.load_memory.get_redis")
    def test_no_memory_returns_empty(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = load_memory({"user_id": "u1"})
        assert result == {"messages": [], "summary": ""}

    @patch("graph.nodes.load_memory.get_redis")
    def test_existing_memory_deserializes(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(
            {
                "summary": "User likes refunds",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "ai", "content": "hi there"},
                ],
            }
        )
        mock_get_redis.return_value = mock_redis

        result = load_memory({"user_id": "u1"})
        assert result["summary"] == "User likes refunds"
        assert len(result["messages"]) == 2
        assert isinstance(result["messages"][0], HumanMessage)
        assert result["messages"][0].content == "hello"
        assert isinstance(result["messages"][1], AIMessage)
        assert result["messages"][1].content == "hi there"


# ── retrieve_context ─────────────────────────────────────────────────────────


class TestRetrieveContext:
    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_below_threshold_returns_empty(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.3)]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test"})
        assert result == {"docs": "", "sources": []}

    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_above_threshold_returns_context(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.8)]
        doc1 = MagicMock()
        doc1.page_content = "chunk one"
        doc1.metadata = {"source_file": "policy.pdf"}
        doc2 = MagicMock()
        doc2.page_content = "chunk two"
        doc2.metadata = {"source_file": "policy.pdf"}
        vs.max_marginal_relevance_search.return_value = [doc1, doc2]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test"})
        assert result["docs"] == "chunk one\n\nchunk two"
        assert result["sources"] == ["policy.pdf"]

    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_no_results_returns_empty(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = []
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test"})
        assert result == {"docs": "", "sources": []}


# ── generate_answer ──────────────────────────────────────────────────────────


class TestGenerateAnswer:
    @patch("graph.nodes.generate_answer._get_chat")
    def test_generates_answer_in_english(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="English answer")
        mock_get_chat.return_value = mock_llm

        result = generate_answer(
            {
                "user_id": "u1",
                "question": "What is the return policy?",
                "messages": [],
                "docs": "Return within 30 days.",
                "summary": "",
            }
        )

        assert len(result["messages"]) == 2
        assert isinstance(result["messages"][0], HumanMessage)
        assert result["messages"][0].content == "What is the return policy?"
        assert isinstance(result["messages"][1], AIMessage)
        assert result["messages"][1].content == "English answer"
        mock_llm.invoke.assert_called_once()

    @patch("graph.nodes.generate_answer._get_chat")
    def test_generates_answer_in_arabic(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="إجابة عربية")
        mock_get_chat.return_value = mock_llm

        result = generate_answer(
            {
                "user_id": "u1",
                "question": "ما هي سياسة الإرجاع؟",
                "messages": [],
                "docs": "",
                "summary": "",
            }
        )

        assert result["messages"][1].content == "إجابة عربية"
        # verify the prompt included Arabic language instruction
        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "Arabic" in prompt_arg


# ── store_memory ───────────────────────────────────────────────────────────────


class TestStoreMemory:
    @patch("graph.nodes.store_memory.get_settings")
    @patch("graph.nodes.store_memory.get_redis")
    def test_stores_serialized_messages_with_ttl(self, mock_get_redis, mock_settings):
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_settings.return_value = MagicMock(redis_ttl_seconds=3600)

        state = {
            "user_id": "u1",
            "messages": [
                HumanMessage(content="hello"),
                AIMessage(content="hi"),
            ],
            "summary": "A summary",
        }

        result = store_memory(state)

        assert result["user_id"] == "u1"
        saved_data = json.loads(mock_redis.set.call_args[0][1])
        assert saved_data["summary"] == "A summary"
        assert saved_data["messages"] == [
            {"role": "user", "content": "hello"},
            {"role": "ai", "content": "hi"},
        ]
        assert mock_redis.set.call_args[1]["ex"] == 3600


# ── summarize ──────────────────────────────────────────────────────────────────


class TestSummarize:
    @patch("graph.nodes.summarize._get_chat")
    def test_less_than_four_messages_returns_state_unchanged(self, mock_get_chat):
        state = {
            "messages": [
                HumanMessage(content="a"),
                AIMessage(content="b"),
                HumanMessage(content="c"),
            ],
            "summary": "",
        }

        result = summarize(state)
        assert result is state  # same object
        mock_get_chat.assert_not_called()

    @patch("graph.nodes.summarize._get_chat")
    def test_summarizes_and_truncates_messages(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Short summary")
        mock_get_chat.return_value = mock_llm

        state = {
            "messages": [
                HumanMessage(content="m1"),
                AIMessage(content="m2"),
                HumanMessage(content="m3"),
                AIMessage(content="m4"),
                HumanMessage(content="m5"),
                HumanMessage(content="m6"),
                HumanMessage(content="m7"),
            ],
            "summary": "",
        }

        result = summarize(state)
        assert result["summary"] == "Short summary"
        assert len(result["messages"]) == 6  # last 6 kept
        mock_llm.invoke.assert_called_once()

    @patch("graph.nodes.summarize._get_chat")
    def test_uses_arabic_when_user_messages_contain_arabic(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="ملخص")
        mock_get_chat.return_value = mock_llm

        state = {
            "messages": [
                HumanMessage(content="مرحبا"),
                AIMessage(content="hello"),
                HumanMessage(content="كيف حالك"),
                AIMessage(content="fine"),
            ],
            "summary": "",
        }

        summarize(state)
        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "Arabic" in prompt_arg
