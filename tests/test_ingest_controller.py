"""Tests for controllers/ingest_controller.py."""

from unittest.mock import MagicMock, patch

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from controllers.ingest_controller import router as ingest_router
from middlewares.auth import require_api_key


def _make_app(override_auth=True):
    app = FastAPI()
    app.include_router(ingest_router, prefix="/api")
    if override_auth:
        app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


class TestIngestStatus:
    def test_status_returns_404_when_not_found(self):
        with patch(
            "controllers.ingest_controller.get_redis",
            return_value=fakeredis.FakeRedis(decode_responses=True),
        ):
            client = _make_app()
            resp = client.get("/api/ingest/status/nonexistent")
            assert resp.status_code == 404

    def test_status_returns_data_when_found(self):
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
        fake_redis.hset(
            "ingest_status:doc123",
            mapping={
                "status": "done",
                "file_name": "test.pdf",
            },
        )
        with patch(
            "controllers.ingest_controller.get_redis",
            return_value=fake_redis,
        ):
            client = _make_app()
            resp = client.get("/api/ingest/status/doc123")
            assert resp.status_code == 200
            assert resp.json()["status"] == "done"


class TestListDocs:
    def test_list_returns_empty_when_no_docs(self):
        with patch(
            "controllers.ingest_controller.get_redis",
            return_value=fakeredis.FakeRedis(decode_responses=True),
        ):
            client = _make_app()
            resp = client.get("/api/ingest/docs")
            assert resp.status_code == 200
            assert resp.json()["total"] == 0
            assert resp.json()["docs"] == []

    def test_list_returns_docs(self):
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
        fake_redis.sadd("ingest:doc_ids", "doc1", "doc2")
        fake_redis.hset("ingest_status:doc1", mapping={"status": "done"})
        fake_redis.hset("ingest_status:doc2", mapping={"status": "done"})
        with patch(
            "controllers.ingest_controller.get_redis",
            return_value=fake_redis,
        ):
            client = _make_app()
            resp = client.get("/api/ingest/docs")
            assert resp.status_code == 200
            assert resp.json()["total"] == 2


class TestDeleteDoc:
    def test_delete_returns_404_when_not_found(self):
        with patch(
            "controllers.ingest_controller.get_redis",
            return_value=fakeredis.FakeRedis(decode_responses=True),
        ):
            client = _make_app()
            resp = client.delete("/api/ingest/nonexistent")
            assert resp.status_code == 404

    def test_delete_success(self):
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
        fake_redis.hset(
            "ingest_status:doc123",
            mapping={
                "status": "done",
                "file_hash": "abc123",
            },
        )
        fake_redis.sadd("ingest:doc_ids", "doc123")

        mock_vs = MagicMock()
        mock_results = MagicMock()
        mock_results.__getitem__ = lambda self, key: ["chunk1", "chunk2"] if key == "ids" else []

        with (
            patch(
                "controllers.ingest_controller.get_redis",
                return_value=fake_redis,
            ),
            patch(
                "controllers.ingest_controller.get_vectorstore",
                return_value=mock_vs,
            ),
            patch(
                "controllers.ingest_controller.get_chunks_by_doc_id",
                return_value={"ids": ["chunk1", "chunk2"]},
            ),
            patch(
                "controllers.ingest_controller.delete_chunks_by_ids",
            ),
        ):
            client = _make_app()
            resp = client.delete("/api/ingest/doc123")
            assert resp.status_code == 200
            assert resp.json()["status"] == "deleted"
            assert resp.json()["doc_id"] == "doc123"
