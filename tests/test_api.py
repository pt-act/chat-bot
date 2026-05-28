from unittest.mock import patch

from fastapi.testclient import TestClient

import main as main_module


def _make_app(redis_ok=True, chroma_ok=True):
    main_module._redis_ok = redis_ok
    main_module._chroma_ok = chroma_ok
    return TestClient(main_module.app)


class TestHealthEndpoint:
    def test_health_all_deps_ok(self):
        client = _make_app(redis_ok=True, chroma_ok=True)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["dependencies"]["redis"] == "ok"
        assert data["dependencies"]["chromadb"] == "ok"

    def test_health_redis_down(self):
        client = _make_app(redis_ok=False, chroma_ok=True)
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["redis"] == "unavailable"

    def test_health_chroma_down(self):
        client = _make_app(redis_ok=True, chroma_ok=False)
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["chromadb"] == "unavailable"

    def test_health_all_deps_down(self):
        client = _make_app(redis_ok=False, chroma_ok=False)
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"


class TestHomeEndpoint:
    def test_home_returns_message(self):
        client = _make_app()
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Chatbot Running"


class TestChatEndpoint:
    @patch("controllers.chat_controller.conversation")
    def test_chat_success(self, mock_conversation):
        mock_conversation.return_value = {"answer": "Test answer", "sources": ["doc1"]}
        client = _make_app()
        resp = client.post("/api/chat", json={"q": "What is the return policy?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"] == "Test answer"
        assert data["sources"] == ["doc1"]

    @patch("controllers.chat_controller.conversation")
    def test_chat_failure_returns_500(self, mock_conversation):
        mock_conversation.side_effect = Exception("LLM down")
        client = _make_app()
        resp = client.post("/api/chat", json={"q": "test question"})
        assert resp.status_code == 500

    def test_chat_empty_question_rejected(self):
        client = _make_app()
        resp = client.post("/api/chat", json={"q": ""})
        assert resp.status_code == 422

    def test_chat_missing_body_rejected(self):
        client = _make_app()
        resp = client.post("/api/chat")
        assert resp.status_code == 422

    def test_chat_custom_user_id_header(self):
        with patch("controllers.chat_controller.conversation") as mock_conv:
            mock_conv.return_value = {"answer": "hi", "sources": []}
            client = _make_app()
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
        client = _make_app()
        resp = client.post(
            "/api/ingest",
            json={"file_name": "test_policy", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    @patch("controllers.ingest_controller.ingest_file")
    def test_ingest_failure_returns_500(self, mock_ingest):
        mock_ingest.side_effect = Exception("download failed")
        client = _make_app()
        resp = client.post(
            "/api/ingest",
            json={"file_name": "test_policy", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
        )
        assert resp.status_code == 500

    def test_ingest_invalid_url_rejected(self):
        client = _make_app()
        resp = client.post(
            "/api/ingest",
            json={"file_name": "test", "s3_url": "not-a-url"},
        )
        assert resp.status_code == 422

    def test_ingest_non_pdf_url_rejected(self):
        client = _make_app()
        resp = client.post(
            "/api/ingest",
            json={"file_name": "test", "s3_url": "https://bucket.s3.amazonaws.com/test.txt"},
        )
        assert resp.status_code == 422

    def test_ingest_empty_file_name_rejected(self):
        client = _make_app()
        resp = client.post(
            "/api/ingest",
            json={"file_name": "", "s3_url": "https://bucket.s3.amazonaws.com/test.pdf"},
        )
        assert resp.status_code == 422


class TestValidationErrorHandler:
    def test_validation_error_returns_structured_details(self):
        client = _make_app()
        resp = client.post("/api/chat", json={"q": ""})
        data = resp.json()
        assert "error" in data
        assert data["error"] == "Validation failed"
        assert "details" in data
