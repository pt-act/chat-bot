"""Tests for persistent feedback + quality-loop export (#3) — service + v1 API."""

import json
from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

import main as main_module
from services import feedback_service


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


class TestFeedbackService:
    def test_record_is_stored_and_retrievable(self, redis):
        with patch("services.feedback_service.get_redis", return_value=redis):
            fid = feedback_service.record(rating="down", reason="wrong policy", question="q?", answer="a")
            total, entries, _ = feedback_service.list_feedback()
        assert total == 1
        assert entries[0].feedback_id == fid
        assert entries[0].rating == "down"
        assert entries[0].reason == "wrong policy"
        assert entries[0].question == "q?"

    def test_list_filters_by_rating(self, redis):
        with patch("services.feedback_service.get_redis", return_value=redis):
            feedback_service.record(rating="down", question="bad")
            feedback_service.record(rating="up", question="good")
            total_down, down, _ = feedback_service.list_feedback(rating="down")
            total_up, up, _ = feedback_service.list_feedback(rating="up")
        assert total_down == 1 and down[0].question == "bad"
        assert total_up == 1 and up[0].question == "good"

    def test_list_paginates(self, redis):
        with patch("services.feedback_service.get_redis", return_value=redis):
            for i in range(3):
                feedback_service.record(rating="down", question=f"q{i}")
            total, page1, next_cursor = feedback_service.list_feedback(limit=2, cursor=0)
        assert total == 3
        assert len(page1) == 2
        assert next_cursor == "2"

    def test_export_downvoted_appends_to_golden(self, redis, tmp_path):
        golden = tmp_path / "golden.jsonl"
        golden.write_text("", encoding="utf-8")
        with patch("services.feedback_service.get_redis", return_value=redis):
            feedback_service.record(rating="down", question="why wrong?", answer="the right answer")
            feedback_service.record(rating="up", question="ignored upvote")
            feedback_service.record(rating="down", answer="no question — skipped")
            appended = feedback_service.export_downvoted_to_golden(golden)
        assert appended == 1
        lines = [json.loads(line) for line in golden.read_text().splitlines() if line.strip()]
        assert lines == [{"question": "why wrong?", "ground_truth": "the right answer"}]


def _client(redis):
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


class TestFeedbackAPI:
    def test_submit_feedback_endpoint(self, redis):
        with patch("services.feedback_service.get_redis", return_value=redis):
            resp = _client(redis).post("/api/v1/feedback", json={"rating": "down", "reason": "off-topic"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["rating"] == "down"
        assert body["status"] == "recorded"
        assert body["feedback_id"]

    def test_submit_rejects_invalid_rating(self, redis):
        resp = _client(redis).post("/api/v1/feedback", json={"rating": "meh"})
        assert resp.status_code == 422

    def test_list_feedback_endpoint(self, redis):
        with patch("services.feedback_service.get_redis", return_value=redis):
            feedback_service.record(rating="down", question="bad answer")
            resp = _client(redis).get("/api/v1/feedback?rating=down")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["feedback"][0]["question"] == "bad answer"

    def test_list_requires_api_key_when_configured(self, redis):
        settings = main_module.get_settings()
        with (
            patch("services.feedback_service.get_redis", return_value=redis),
            patch.object(settings, "require_auth_for_ingest", True),
            patch.object(settings, "api_key", "secret"),
        ):
            unauth = _client(redis).get("/api/v1/feedback")
            authed = _client(redis).get("/api/v1/feedback", headers={"X-API-Key": "secret"})
        assert unauth.status_code == 401
        assert authed.status_code == 200
