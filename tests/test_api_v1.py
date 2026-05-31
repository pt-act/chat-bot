"""Tests for the v1 API contract: typed envelopes, problem+json, deprecation header."""

from unittest.mock import patch

import fakeredis
from fastapi.testclient import TestClient

import main as main_module


def _client():
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


class TestV1ChatEnvelope:
    @patch("controllers.v1.chat.conversation")
    def test_chat_returns_typed_envelope(self, mock_conv):
        mock_conv.return_value = {
            "answer": "Returns within 30 days.",
            "sources": ["return_policy.pdf"],
            "self_ingested": False,
        }
        resp = _client().post("/api/v1/chat", json={"q": "return policy?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Returns within 30 days."
        assert body["sources"][0]["label"] == "return_policy.pdf"
        assert body["meta"]["mode"] in {"strict", "open", "learning"}
        assert "self_ingested" in body["meta"]
        # No legacy fields leak into v1.
        assert "data" not in body and "status" not in body

    @patch("controllers.v1.chat.conversation")
    def test_invalid_user_id_problem_json(self, mock_conv):
        resp = _client().post("/api/v1/chat", json={"q": "hi"}, headers={"x-user-id": "bad id"})
        assert resp.status_code == 400
        assert resp.json()["title"] == "Request failed"


class TestLegacyDeprecation:
    @patch("controllers.chat_controller.conversation")
    def test_legacy_still_works_and_is_marked_deprecated(self, mock_conv):
        mock_conv.return_value = {"answer": "x", "sources": []}
        resp = _client().post("/api/chat", json={"q": "hi"})
        assert resp.status_code == 200
        # legacy envelope preserved
        assert resp.json()["status"] == "success"
        assert resp.json()["data"] == "x"
        # ...but flagged deprecated
        assert resp.headers.get("Deprecation") == "true"
        assert "successor-version" in resp.headers.get("Link", "")

    def test_v1_is_not_marked_deprecated(self):
        # health is unversioned/system; v1 chat path should not carry deprecation
        with patch(
            "controllers.v1.chat.conversation", return_value={"answer": "x", "sources": [], "self_ingested": False}
        ):
            resp = _client().post("/api/v1/chat", json={"q": "hi"})
        assert "Deprecation" not in resp.headers


class TestProblemJson:
    def test_validation_is_problem_json(self):
        resp = _client().post("/api/v1/chat", json={"q": ""})
        assert resp.status_code == 422
        body = resp.json()
        assert body["title"] == "Validation failed"
        assert body["status"] == 422
        assert any(e["field"] == "q" for e in body["errors"])


class TestPerRequestControls:
    @patch("controllers.v1.chat.conversation")
    def test_controls_passed_through(self, mock_conv):
        mock_conv.return_value = {"answer": "a", "sources": [], "self_ingested": False, "lang": "en"}
        resp = _client().post(
            "/api/v1/chat",
            json={"q": "hi", "mode": "open", "lang": "ar", "top_k": 5, "score_threshold": 0.4},
        )
        assert resp.status_code == 200
        mock_conv.assert_called_once_with(
            user_id="anonymous", q="hi", mode="open", lang="ar", top_k=5, score_threshold=0.4
        )
        assert resp.json()["meta"]["mode"] == "open"

    def test_invalid_mode_rejected(self):
        resp = _client().post("/api/v1/chat", json={"q": "hi", "mode": "bogus"})
        assert resp.status_code == 422

    @patch("controllers.v1.chat.conversation")
    def test_learning_review_mode_accepted(self, mock_conv):
        mock_conv.return_value = {"answer": "a", "sources": [], "self_ingested": True, "lang": "en"}
        resp = _client().post("/api/v1/chat", json={"q": "hi", "mode": "learning_review"})
        assert resp.status_code == 200
        assert resp.json()["meta"]["mode"] == "learning_review"

    def test_top_k_out_of_range_rejected(self):
        resp = _client().post("/api/v1/chat", json={"q": "hi", "top_k": 99})
        assert resp.status_code == 422

    @patch("controllers.v1.chat.conversation")
    def test_structured_citations_serialized(self, mock_conv):
        mock_conv.return_value = {
            "answer": "a",
            "sources": [{"label": "policy.pdf", "doc_id": "policy", "score": 0.82, "page": 3, "snippet": "..."}],
            "self_ingested": False,
            "lang": "en",
        }
        resp = _client().post("/api/v1/chat", json={"q": "hi"})
        src = resp.json()["sources"][0]
        assert src["doc_id"] == "policy" and src["score"] == 0.82 and src["page"] == 3


class TestOpenAPI:
    def test_v1_routes_documented(self):
        spec = _client().get("/openapi.json").json()
        assert "/api/v1/chat" in spec["paths"]
        assert "/api/v1/ingest" in spec["paths"]
        # ChatResponse model is referenced (typed envelope)
        assert "ChatResponse" in spec["components"]["schemas"]
