"""End-to-end graph integration test.

Unlike tests/test_graph_nodes.py — which mocks each node's `_get_chat` — this test
compiles the REAL LangGraph pipeline and drives it through the REAL
`utils.llm_adapter.get_llm(...)` path, only mocking the outermost boundaries
(the provider SDK `ChatOpenAI`, Redis, and the vector store).

This is the regression guard for finding C-1: the graph nodes call
`get_llm(temperature=..., max_tokens=...)`, and before the fix `get_llm()` took no
arguments, so every real request raised `TypeError`. Because the unit tests mocked
`_get_chat`, that crash carried 96% coverage. This test would have caught it.
"""

from unittest.mock import MagicMock, patch

import fakeredis

import graph.nodes.generate_answer as gen_mod
import graph.nodes.summarize as sum_mod
import utils.llm_adapter as llm_mod
from graph.builder import build_graph


def test_graph_runs_end_to_end_through_real_get_llm():
    # Clear caches so the patched ChatOpenAI is actually constructed via get_llm().
    llm_mod.get_llm.cache_clear()
    gen_mod._get_chat.cache_clear()
    sum_mod._get_chat.cache_clear()

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="integration answer")

    redis = fakeredis.FakeRedis(decode_responses=True)

    vs = MagicMock()
    # Strict mode + no matches → refusal-style path; generate_answer still runs.
    vs.similarity_search_with_relevance_scores.return_value = []

    with (
        patch("langchain_openai.ChatOpenAI", return_value=fake_llm) as mock_chat_cls,
        patch("graph.nodes.load_memory.get_redis", return_value=redis),
        patch("graph.nodes.store_memory.get_redis", return_value=redis),
        patch("graph.nodes.retrieve_context.get_vectorstore", return_value=vs),
    ):
        graph = build_graph()
        result = graph.invoke({"user_id": "itest", "question": "What is the return policy?", "chat_mode": "strict"})

    # The pipeline completed and produced the model's answer end-to-end.
    assert result["messages"][-1].content == "integration answer"

    # Proof the REAL get_llm path executed and forwarded generation params
    # (this is exactly what was broken in C-1).
    _, kwargs = mock_chat_cls.call_args
    assert kwargs["temperature"] == 0
    assert kwargs["max_tokens"] == 512

    # Memory was persisted under the namespaced key (M-4) via the real store_memory.
    assert redis.get("chat:memory:itest") is not None

    # Cleanup so the cached fake doesn't leak into other tests.
    llm_mod.get_llm.cache_clear()
    gen_mod._get_chat.cache_clear()
    sum_mod._get_chat.cache_clear()
