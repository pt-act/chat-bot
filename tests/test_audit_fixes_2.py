"""Regression tests for the second hardening batch (M-3, M-4, I-1/I-2)."""

import json
from unittest.mock import MagicMock, patch

import fakeredis
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

import main as main_module
from db.redis_client import memory_key
from graph.nodes.load_memory import load_memory
from graph.nodes.store_memory import store_memory


def _client():
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


# ── M-4: X-User-Id validation ────────────────────────────────────────────────
class TestUserIdValidation:
    @patch("controllers.chat_controller.conversation")
    def test_valid_user_id_passes_through(self, mock_conv):
        mock_conv.return_value = {"answer": "hi", "sources": []}
        resp = _client().post("/api/chat", json={"q": "hello"}, headers={"x-user-id": "user.name-1@x"})
        assert resp.status_code == 200
        mock_conv.assert_called_once_with(user_id="user.name-1@x", q="hello")

    def test_invalid_user_id_rejected(self):
        # spaces / control chars / namespace separators are not allowed
        for bad in ["bad id", "ingest:doc_ids", "a/b", "x" * 129]:
            resp = _client().post("/api/chat", json={"q": "hello"}, headers={"x-user-id": bad})
            assert resp.status_code == 400, bad

    @patch("controllers.chat_controller.conversation")
    def test_blank_user_id_defaults_to_anonymous(self, mock_conv):
        mock_conv.return_value = {"answer": "hi", "sources": []}
        resp = _client().post("/api/chat", json={"q": "hello"}, headers={"x-user-id": "   "})
        assert resp.status_code == 200
        mock_conv.assert_called_once_with(user_id="anonymous", q="hello")


# ── M-4: memory keys are namespaced ──────────────────────────────────────────
class TestMemoryKeyNamespacing:
    def test_memory_key_is_prefixed(self):
        assert memory_key("u1") == "chat:memory:u1"
        # A crafted id cannot collide with operational keys.
        assert memory_key("ingest:doc_ids") == "chat:memory:ingest:doc_ids"

    @patch("graph.nodes.store_memory.get_settings")
    @patch("graph.nodes.store_memory.get_redis")
    def test_store_memory_writes_namespaced_key(self, mock_get_redis, mock_settings):
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_settings.return_value = MagicMock(redis_ttl_seconds=3600)
        store_memory({"user_id": "u1", "messages": [HumanMessage(content="hi")], "summary": ""})
        assert mock_redis.set.call_args[0][0] == "chat:memory:u1"

    @patch("graph.nodes.load_memory.get_redis")
    def test_load_memory_reads_namespaced_key(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"summary": "s", "messages": []})
        mock_get_redis.return_value = mock_redis
        load_memory({"user_id": "u1"})
        mock_redis.get.assert_called_once_with("chat:memory:u1")

    def test_store_then_load_roundtrip_with_fakeredis(self):
        r = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("graph.nodes.store_memory.get_redis", return_value=r),
            patch("graph.nodes.load_memory.get_redis", return_value=r),
            patch("graph.nodes.store_memory.get_settings", return_value=MagicMock(redis_ttl_seconds=3600)),
        ):
            store_memory(
                {"user_id": "u9", "messages": [HumanMessage(content="hi"), AIMessage(content="yo")], "summary": "s"}
            )
            out = load_memory({"user_id": "u9"})
        assert out["summary"] == "s"
        assert [m.content for m in out["messages"]] == ["hi", "yo"]


# ── M-3: generic 5xx bodies (no internal text leak) ──────────────────────────
class TestNoErrorLeak:
    @patch("controllers.chat_controller.conversation")
    def test_chat_runtime_error_is_generic(self, mock_conv):
        mock_conv.side_effect = RuntimeError("boom: secret/path/leaked.txt")
        resp = _client().post("/api/chat", json={"q": "hello"})
        assert resp.status_code == 500
        assert "secret/path" not in resp.text
        assert resp.json()["detail"] == "Failed to generate a response"


# ── I-1: dead code removed ───────────────────────────────────────────────────
def test_chroma_alias_removed():
    import db.vector as v

    assert not hasattr(v, "chroma")
