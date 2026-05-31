"""Tests for async ingest (202 + poll) and docs pagination (spec A7)."""

from unittest.mock import patch

import fakeredis
from fastapi.testclient import TestClient

import main as main_module
from ingest.keys import ALL_DOCS_KEY, ingest_status_key


def _client(redis):
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


class TestAsyncIngest:
    def test_returns_202_queued_and_schedules_work(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_file") as mock_ingest,
        ):
            resp = _client(redis).post(
                "/api/v1/ingest",
                json={"file_name": "policy", "s3_url": "https://b.s3.amazonaws.com/p.pdf"},
            )
        assert resp.status_code == 202
        assert resp.json() == {"doc_id": "policy", "status": "queued"}
        assert resp.headers["Location"] == "/api/v1/ingest/status/policy"
        # initial status persisted + scheduled background work executed (TestClient runs it)
        assert redis.hget(ingest_status_key("policy"), "status") == "queued"
        mock_ingest.assert_called_once_with("policy", "https://b.s3.amazonaws.com/p.pdf")

    def test_status_pollable_after_queue(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        redis.hset(ingest_status_key("policy"), mapping={"doc_id": "policy", "status": "done", "added": "3"})
        with patch("controllers.v1.ingest.get_redis", return_value=redis):
            resp = _client(redis).get("/api/v1/ingest/status/policy")
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"
        assert resp.json()["added"] == 3


class TestPagination:
    def test_docs_paginate_with_cursor(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        for i in range(5):
            doc_id = f"doc{i}"
            redis.sadd(ALL_DOCS_KEY, doc_id)
            redis.hset(ingest_status_key(doc_id), mapping={"doc_id": doc_id, "status": "done"})

        with patch("controllers.v1.ingest.get_redis", return_value=redis):
            c = _client(redis)
            page1 = c.get("/api/v1/ingest/docs?limit=2&cursor=0").json()
            assert page1["total"] == 5
            assert len(page1["docs"]) == 2
            assert page1["next_cursor"] == "2"

            last = c.get("/api/v1/ingest/docs?limit=2&cursor=4").json()
            assert len(last["docs"]) == 1
            assert last["next_cursor"] is None
