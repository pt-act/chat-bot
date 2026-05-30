"""Tests for main.py lifespan and exception handlers."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import main as main_module


class TestLifespan:
    @patch("main.get_redis")
    @patch("main.get_vectorstore")
    def test_lifespan_sets_flags_on_success(self, mock_get_vs, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_get_redis.return_value = mock_redis

        mock_vs = MagicMock()
        mock_vs.similarity_search.return_value = []
        mock_get_vs.return_value = mock_vs

        # Reset flags before test
        main_module._redis_ok = False
        main_module._chroma_ok = False

        # Trigger lifespan by making a request
        with TestClient(main_module.app):
            pass

        assert main_module._redis_ok is True
        assert main_module._chroma_ok is True

    @patch("main.get_redis")
    @patch("main.get_vectorstore")
    def test_lifespan_sets_flags_on_failure(self, mock_get_vs, mock_get_redis):
        mock_get_redis.side_effect = Exception("Redis down")
        mock_get_vs.side_effect = Exception("ChromaDB down")

        # Reset flags before test
        main_module._redis_ok = True
        main_module._chroma_ok = True

        # Trigger lifespan by making a request
        with TestClient(main_module.app):
            pass

        assert main_module._redis_ok is False
        assert main_module._chroma_ok is False


class TestExceptionHandlers:
    """The unified RFC 9457 (problem+json) error model — see middlewares/errors.py."""

    def _app_with_handlers(self):
        from fastapi import FastAPI

        from middlewares.errors import register_error_handlers

        app = FastAPI()
        register_error_handlers(app)
        return app

    def test_value_error_returns_problem_400(self):
        app = self._app_with_handlers()

        @app.get("/error")
        def boom():
            raise ValueError("bad input")

        resp = TestClient(app, raise_server_exceptions=False).get("/error")
        assert resp.status_code == 400
        body = resp.json()
        assert body["title"] == "Bad request"
        assert body["status"] == 400
        assert "bad input" in body["detail"]

    def test_runtime_error_returns_generic_problem_500(self):
        app = self._app_with_handlers()

        @app.get("/error")
        def boom():
            raise RuntimeError("system failure")

        resp = TestClient(app, raise_server_exceptions=False).get("/error")
        assert resp.status_code == 500
        # The internal exception message must NOT be echoed to the client (M-3).
        body = resp.json()
        assert "system failure" not in str(body)
        assert body["title"] == "Internal server error"
        assert "detail" not in body
