"""Tests for the SSE streaming chat endpoint (spec A3)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fakeredis
from fastapi.testclient import TestClient

import main as main_module


def _fake_stream_llm(*deltas):
    llm = MagicMock()
    llm.stream.return_value = [SimpleNamespace(content=d) for d in deltas]
    return llm


def _client():
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


def test_chat_stream_emits_tokens_sources_done():
    redis = fakeredis.FakeRedis(decode_responses=True)
    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = []  # strict, no docs

    with (
        patch("services.chat_service.get_llm", return_value=_fake_stream_llm("Hello", ", ", "world")),
        patch("graph.nodes.load_memory.get_redis", return_value=redis),
        patch("graph.nodes.store_memory.get_redis", return_value=redis),
        patch("graph.nodes.retrieve_context.get_vectorstore", return_value=vs),
    ):
        resp = _client().post("/api/v1/chat/stream", json={"q": "hi"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text

    # ≥2 token events, then sources, then done (in order).
    assert body.count("event: token") == 3
    assert '"delta": "Hello"' in body
    assert "event: sources" in body
    assert "event: done" in body
    assert body.index("event: token") < body.index("event: sources") < body.index("event: done")
    # memory persisted under the namespaced key despite streaming
    assert redis.get("chat:memory:anonymous") is not None


def test_chat_stream_emits_error_event_on_failure():
    with patch("services.chat_service.get_llm", side_effect=RuntimeError("boom")):
        resp = _client().post("/api/v1/chat/stream", json={"q": "hi"})
        assert resp.status_code == 200  # stream opened, error delivered in-band
        assert "event: error" in resp.text
        assert "boom" not in resp.text  # internal detail not leaked


def test_chat_stream_validates_body():
    resp = _client().post("/api/v1/chat/stream", json={"q": ""})
    assert resp.status_code == 422
