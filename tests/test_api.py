from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import fakeredis
from fastapi.testclient import TestClient

import main as main_module


@contextmanager
def _make_app(redis_ok=True, chroma_ok=True):
    main_module._redis_ok = redis_ok
    main_module._chroma_ok = chroma_ok
    # Mock Redis for middlewares that depend on it
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        yield TestClient(main_module.app)


class TestHealthEndpoint:
    def test_health_all_deps_ok(self):
        with _make_app(redis_ok=True, chroma_ok=True) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["dependencies"]["redis"] == "ok"
            assert data["dependencies"]["chromadb"] == "ok"

    def test_health_redis_down(self):
        with _make_app(redis_ok=False, chroma_ok=True) as client:
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["dependencies"]["redis"] == "unavailable"

    def test_health_chroma_down(self):
        with _make_app(redis_ok=True, chroma_ok=False) as client:
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["dependencies"]["chromadb"] == "unavailable"

    def test_health_all_deps_down(self):
        with _make_app(redis_ok=False, chroma_ok=False) as client:
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "degraded"


class TestHomeEndpoint:
    def test_home_returns_message(self):
        with _make_app() as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert resp.json()["message"] == "Chatbot Running"


class TestChatEndpoint:
    @patch("controllers.chat_controller.conversation")
    def test_chat_success(self, mock_conversation):
        mock_conversation.return_value = {"answer": "Test answer", "sources": ["doc1"]}
        with _make_app() as client:
            resp = client.post("/api/chat", json={"q": "What is the return policy?"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["data"] == "Test answer"
            assert data["sources"] == ["doc1"]

    @patch("controllers.chat_controller.conversation")
    def test_chat_failure_returns_500(self, mock_conversation):
        mock_conversation.side_effect = Exception("LLM down")
        with _make_app() as client:
            resp = client.post("/api/chat", json={"q": "test question"})
            assert resp.status_code == 500

    def test_chat_empty_question_rejected(self):
        with _make_app() as client:
            resp = client.post("/api/chat", json={"q": ""})
            assert resp.status_code == 422

    def test_chat_missing_body_rejected(self):
        with _make_app() as client:
            resp = client.post("/api/chat")
            assert resp.status_code == 422

    def test_chat_custom_user_id_header(self):
        with patch("controllers.chat_controller.conversation") as mock_conv:
            mock_conv.return_value = {"answer": "hi", "sources": []}
            with _make_app() as client:
                resp = client.post(
                    "/api/chat",
                    json={"q": "hello"},
                    headers={"x-user-id": "user123"},
                )
                assert resp.status_code == 200
                mock_conv.assert_called_once_with(user_id="user123", q="hello")


class TestIngestEndpoint:
    @patch("controllers.ingest_controller.ingest_file")
    def test_ingest_success(self, mock_ingest):
        mock_ingest.return_value = {"doc_id": "test_policy", "status": "done"}
        with _make_app() as client:
            resp = client.post(
                "/api/ingest",
                json={"file_name": "test_policy", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    @patch("controllers.ingest_controller.ingest_file")
    def test_ingest_failure_returns_500(self, mock_ingest):
        mock_ingest.side_effect = Exception("download failed")
        with _make_app() as client:
            resp = client.post(
                "/api/ingest",
                json={"file_name": "test_policy", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
            )
            assert resp.status_code == 500

    def test_ingest_invalid_url_rejected(self):
        with _make_app() as client:
            resp = client.post(
                "/api/ingest",
                json={"file_name": "test", "s3_url": "not-a-url"},
            )
            assert resp.status_code == 422

    def test_ingest_non_pdf_url_rejected(self):
        with _make_app() as client:
            resp = client.post(
                "/api/ingest",
                json={"file_name": "test", "s3_url": "https://bucket.s3.amazonaws.com/test.txt"},
            )
            assert resp.status_code == 422

    def test_ingest_empty_file_name_rejected(self):
        with _make_app() as client:
            resp = client.post(
                "/api/ingest",
                json={"file_name": "", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
            )
            assert resp.status_code == 422


class TestReadinessEndpoint:
    @patch("main.get_redis")
    @patch("main.get_vectorstore")
    def test_ready_all_deps_ok(self, mock_vs, mock_redis):
        mock_vs.return_value.similarity_search.return_value = []
        mock_redis.return_value.ping.return_value = True
        with _make_app() as client:
            resp = client.get("/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["dependencies"]["redis"] == "ok"

    def test_ready_redis_down_returns_503(self):
        with patch("main.get_redis", side_effect=Exception("Redis down")):
            with _make_app() as client:
                resp = client.get("/ready")
                assert resp.status_code == 503
                data = resp.json()
                assert data["status"] == "not_ready"
                assert "unavailable" in data["dependencies"]["redis"]


class TestAuthMiddleware:
    def test_delete_requires_api_key(self):
        with _make_app() as client:
            resp = client.delete("/api/ingest/test_doc")
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid or missing API key"

    def test_delete_with_valid_api_key(self):
        mock_settings = MagicMock()
        mock_settings.api_key = "test-key-123"
        mock_settings.require_auth_for_ingest = True
        with (
            patch(
                "controllers.ingest_controller.get_redis",
                return_value=fakeredis.FakeRedis(decode_responses=True),
            ),
            patch("controllers.ingest_controller.get_vectorstore"),
            patch("middlewares.auth.get_settings", return_value=mock_settings),
        ):
            with _make_app() as client:
                resp = client.delete(
                    "/api/ingest/test_doc",
                    headers={"X-API-Key": "test-key-123"},
                )
                # 404 because the doc doesn't exist, but auth passed
                assert resp.status_code == 404


class TestValidationErrorHandler:
    def test_validation_error_returns_problem_json(self):
        with _make_app() as client:
            resp = client.post("/api/chat", json={"q": ""})
            assert resp.status_code == 422
            data = resp.json()
            # RFC 9457 problem+json shape (middlewares/errors.py)
            assert data["title"] == "Validation failed"
            assert data["status"] == 422
            assert any(e["field"] == "q" for e in data["errors"])
