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
from graph.nodes.self_ingest import self_ingest
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
    def test_below_threshold_returns_empty_strict(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.3)]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test", "chat_mode": "strict"})
        assert result == {"docs": "", "sources": [], "best_score": 0.3}

    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_above_threshold_uses_mmr_with_scores(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        doc1 = MagicMock(
            page_content="chunk one",
            metadata={"doc_id": "policy", "source_file": "policy.pdf", "page_number": 1, "chunk_hash": "h1"},
        )
        doc2 = MagicMock(
            page_content="chunk two",
            metadata={"doc_id": "policy", "source_file": "policy.pdf", "page_number": 2, "chunk_hash": "h2"},
        )
        # Scored candidate pool supplies the gate score + per-citation scores...
        vs.similarity_search_with_relevance_scores.return_value = [(doc1, 0.8), (doc2, 0.7)]
        # ...and MMR selects the diverse chunks that are actually used (feature restored).
        vs.max_marginal_relevance_search.return_value = [doc1, doc2]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test", "chat_mode": "strict"})

        # MMR must be the selector (not raw top-k).
        vs.max_marginal_relevance_search.assert_called_once()
        assert result["docs"] == "chunk one\n\nchunk two"
        assert result["best_score"] == 0.8
        # Citations keep their relevance scores (joined from the scored pool by chunk_hash).
        assert result["sources"][0] == {
            "label": "policy.pdf",
            "doc_id": "policy",
            "score": 0.8,
            "page": 1,
            "snippet": "chunk one",
        }
        assert result["sources"][1]["score"] == 0.7

    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_no_results_returns_empty(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = []
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test", "chat_mode": "strict"})
        assert result == {"docs": "", "sources": [], "best_score": 0.0}

    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_open_mode_returns_low_score_docs(self, mock_settings, mock_get_vs):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.2)]
        doc1 = MagicMock()
        doc1.page_content = "weak match"
        doc1.metadata = {"source": "doc.pdf"}
        vs.similarity_search.return_value = [doc1]
        mock_get_vs.return_value = vs

        result = retrieve_context({"question": "test", "chat_mode": "open"})
        assert result["docs"] == "weak match"
        assert result["sources"][0]["label"] == "doc.pdf"
        assert result["sources"][0]["score"] is None  # weak path has no per-doc score
        assert result["best_score"] == 0.2

    @patch("graph.nodes.retrieve_context.get_synthesized_vectorstore")
    @patch("graph.nodes.retrieve_context.get_vectorstore")
    @patch("graph.nodes.retrieve_context.get_settings")
    def test_learning_mode_returns_low_score_docs(self, mock_settings, mock_get_vs, mock_get_synth):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5)
        vs = MagicMock()
        vs.similarity_search_with_relevance_scores.return_value = [("doc", 0.15)]
        doc1 = MagicMock()
        doc1.page_content = "partial match"
        doc1.metadata = {"source": "doc.pdf"}
        vs.similarity_search.return_value = [doc1]
        mock_get_vs.return_value = vs
        # No previously synthesized answers for this question.
        synth = MagicMock()
        synth.similarity_search.return_value = []
        mock_get_synth.return_value = synth

        result = retrieve_context({"question": "test", "chat_mode": "learning"})
        assert result["docs"] == "partial match"
        assert result["best_score"] == 0.15


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
                "chat_mode": "strict",
            }
        )

        assert len(result["messages"]) == 2
        assert isinstance(result["messages"][0], HumanMessage)
        assert result["messages"][0].content == "What is the return policy?"
        assert isinstance(result["messages"][1], AIMessage)
        assert result["messages"][1].content == "English answer"
        assert result["last_answer"] == "English answer"
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
                "chat_mode": "strict",
            }
        )

        assert result["messages"][1].content == "إجابة عربية"
        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "Arabic" in prompt_arg

    @patch("graph.nodes.generate_answer._get_chat")
    def test_generates_answer_in_portuguese_when_detected(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Resposta em português")
        mock_get_chat.return_value = mock_llm

        result = generate_answer(
            {
                "user_id": "u1",
                "question": "Qual é a política de devoluções?",
                "messages": [],
                "docs": "",
                "summary": "",
                "chat_mode": "strict",
            }
        )

        assert result["messages"][1].content == "Resposta em português"
        assert result["lang"] == "European Portuguese"
        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "European Portuguese" in prompt_arg

    @patch("graph.nodes.generate_answer._get_chat")
    def test_lang_override_forces_portuguese(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Resposta")
        mock_get_chat.return_value = mock_llm

        result = generate_answer(
            {
                "user_id": "u1",
                "question": "What is the return policy?",
                "messages": [],
                "docs": "",
                "summary": "",
                "chat_mode": "strict",
                "lang": "pt",
            }
        )

        assert result["lang"] == "European Portuguese"

    @patch("graph.nodes.generate_answer._get_chat")
    def test_open_mode_prompt_contains_general_knowledge_rule(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Open answer")
        mock_get_chat.return_value = mock_llm

        generate_answer(
            {
                "user_id": "u1",
                "question": "What is AI?",
                "messages": [],
                "docs": "",
                "summary": "",
                "chat_mode": "open",
            }
        )

        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "general knowledge" in prompt_arg

    @patch("graph.nodes.generate_answer._get_chat")
    def test_learning_mode_prompt_contains_synthesize_rule(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Learning answer")
        mock_get_chat.return_value = mock_llm

        generate_answer(
            {
                "user_id": "u1",
                "question": "What is AI?",
                "messages": [],
                "docs": "",
                "summary": "",
                "chat_mode": "learning",
            }
        )

        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "synthesize" in prompt_arg

    @patch("graph.nodes.generate_answer._get_chat")
    def test_strict_mode_prompt_contains_refusal_rule(self, mock_get_chat):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Strict answer")
        mock_get_chat.return_value = mock_llm

        generate_answer(
            {
                "user_id": "u1",
                "question": "What is the weather?",
                "messages": [],
                "docs": "",
                "summary": "",
                "chat_mode": "strict",
            }
        )

        prompt_arg = mock_llm.invoke.call_args[0][0]
        assert "I don't have information" in prompt_arg


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


class TestSelfIngest:
    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    def test_strict_mode_skips_ingest(self, mock_get_vs, mock_settings):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        result = self_ingest({"chat_mode": "strict", "best_score": 0.1, "last_answer": "Short", "question": "test"})
        assert result == {"self_ingested": False}

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    def test_open_mode_skips_ingest(self, mock_get_vs, mock_settings):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        result = self_ingest({"chat_mode": "open", "best_score": 0.1, "last_answer": "Short", "question": "test"})
        assert result == {"self_ingested": False}

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    def test_learning_mode_skips_when_docs_found(self, mock_get_vs, mock_settings):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        result = self_ingest(
            {"chat_mode": "learning", "best_score": 0.8, "last_answer": "Answer from docs", "question": "test"}
        )
        assert result == {"self_ingested": False}

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    def test_learning_mode_skips_short_answers(self, mock_get_vs, mock_settings):
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        result = self_ingest(
            {"chat_mode": "learning", "best_score": 0.1, "last_answer": "Too short", "question": "test"}
        )
        assert result == {"self_ingested": False}
        mock_get_vs.assert_not_called()

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    def test_learning_mode_embeds_directly(self, mock_get_vs, mock_settings):
        # `learning` embeds the synthesized answer immediately.
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        mock_vs = MagicMock()
        mock_get_vs.return_value = mock_vs

        result = self_ingest(
            {
                "chat_mode": "learning",
                "best_score": 0.1,
                "last_answer": "AI is the simulation of human intelligence by machines.",
                "question": "What is AI?",
            }
        )
        assert result == {"self_ingested": True, "pending_review": False}
        mock_vs.add_documents.assert_called_once()
        added_doc = mock_vs.add_documents.call_args[0][0][0]
        assert added_doc.metadata["source_type"] == "synthesized"
        assert added_doc.metadata["source_question"] == "What is AI?"
        assert added_doc.metadata["best_score"] == 0.1

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.get_synthesized_vectorstore")
    @patch("graph.nodes.self_ingest.enqueue")
    def test_learning_review_mode_queues_for_review(self, mock_enqueue, mock_get_vs, mock_settings):
        # `learning_review` queues for human review, does NOT embed.
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        mock_enqueue.return_value = "synthesized:deadbeef0000"

        result = self_ingest(
            {
                "chat_mode": "learning_review",
                "best_score": 0.1,
                "last_answer": "AI is the simulation of human intelligence by machines.",
                "question": "What is AI?",
            }
        )
        assert result["self_ingested"] is True
        assert result["pending_review"] is True
        assert result["review_entry_id"] == "synthesized:deadbeef0000"
        mock_enqueue.assert_called_once()
        mock_get_vs.return_value.add_documents.assert_not_called()

    @patch("graph.nodes.self_ingest.get_settings")
    @patch("graph.nodes.self_ingest.enqueue")
    def test_learning_review_mode_skips_when_docs_found(self, mock_enqueue, mock_settings):
        # The gap-filling gate applies to learning_review too: docs found → no queue.
        mock_settings.return_value = MagicMock(retrieval_score_threshold=0.5, self_ingest_min_length=50)
        result = self_ingest(
            {"chat_mode": "learning_review", "best_score": 0.9, "last_answer": "x" * 80, "question": "q"}
        )
        assert result == {"self_ingested": False}
        mock_enqueue.assert_not_called()
