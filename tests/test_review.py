"""Tests for the two-phase learning-review workflow (service + v1 API)."""

from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

import main as main_module
from services import review_service


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


class TestReviewService:
    def test_enqueue_does_not_embed_and_is_idempotent(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            id1 = review_service.enqueue("What is the warranty?", "Based on my knowledge, 12 months.", 0.1)
            id2 = review_service.enqueue("What is the warranty?", "Based on my knowledge, 12 months.", 0.1)
        assert id1 == id2  # same (question, answer) → same id
        total, pending, _ = _list(redis)
        assert total == 1
        assert pending[0].entry_id == id1
        assert pending[0].status == "pending"

    def test_list_pagination(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            for i in range(3):
                review_service.enqueue(f"q{i}", f"answer number {i} with enough text", 0.1)
            total, page1, next_cursor = review_service.list_pending(limit=2, cursor=0)
        assert total == 3
        assert len(page1) == 2
        assert next_cursor == "2"

    def test_approve_embeds_then_discards(self, redis):
        vs = MagicMock()
        with (
            patch("services.review_service.get_redis", return_value=redis),
            patch("services.review_service.get_synthesized_vectorstore", return_value=vs),
        ):
            entry_id = review_service.enqueue("What is AI?", "Based on my knowledge, AI simulates intelligence.", 0.1)
            assert review_service.approve(entry_id) is True
            # Embedded exactly once with the right metadata...
            vs.add_documents.assert_called_once()
            doc = vs.add_documents.call_args[0][0][0]
            assert doc.metadata["reviewed"] is True
            assert doc.metadata["source"] == entry_id
            # ...and removed from the queue.
            total, _, _ = review_service.list_pending()
        assert total == 0

    def test_reject_discards_without_embedding(self, redis):
        vs = MagicMock()
        with (
            patch("services.review_service.get_redis", return_value=redis),
            patch("services.review_service.get_synthesized_vectorstore", return_value=vs),
        ):
            entry_id = review_service.enqueue("q", "a substantive synthesized answer here", 0.1)
            assert review_service.reject(entry_id) is True
            vs.add_documents.assert_not_called()
            total, _, _ = review_service.list_pending()
        assert total == 0

    def test_approve_missing_raises_keyerror(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            with pytest.raises(KeyError):
                review_service.approve("synthesized:doesnotexist")

    def test_reject_missing_raises_keyerror(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            with pytest.raises(KeyError):
                review_service.reject("synthesized:doesnotexist")


def _list(redis):
    with patch("services.review_service.get_redis", return_value=redis):
        return review_service.list_pending()


def _client(redis):
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


class TestReviewAPI:
    def test_list_pending_endpoint(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            review_service.enqueue("What is AI?", "Based on my knowledge, AI simulates intelligence.", 0.1)
            resp = _client(redis).get("/api/v1/review/pending")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["pending"][0]["question"] == "What is AI?"

    def test_approve_endpoint(self, redis):
        vs = MagicMock()
        with (
            patch("services.review_service.get_redis", return_value=redis),
            patch("services.review_service.get_synthesized_vectorstore", return_value=vs),
        ):
            entry_id = review_service.enqueue("q", "a substantive synthesized answer here", 0.1)
            resp = _client(redis).post(f"/api/v1/review/{entry_id}/approve")
        assert resp.status_code == 200
        assert resp.json() == {"entry_id": entry_id, "status": "approved", "embedded": True}
        vs.add_documents.assert_called_once()

    def test_reject_endpoint(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            entry_id = review_service.enqueue("q", "a substantive synthesized answer here", 0.1)
            resp = _client(redis).post(f"/api/v1/review/{entry_id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approve_unknown_returns_404(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            resp = _client(redis).post("/api/v1/review/synthesized:missing/approve")
        assert resp.status_code == 404

    def test_reject_unknown_returns_404(self, redis):
        with patch("services.review_service.get_redis", return_value=redis):
            resp = _client(redis).post("/api/v1/review/synthesized:missing/reject")
        assert resp.status_code == 404
