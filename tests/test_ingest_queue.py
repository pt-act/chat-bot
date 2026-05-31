"""Tests for the durable, retryable ingestion queue (#4).

Hermetic: drives ``process_one`` directly with a fakeredis client and mocked processing
functions — no worker daemon, no network.
"""

import json
import tempfile
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from ingest.queue import INGEST_QUEUE_KEY, _lock_key, enqueue, process_one


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


def _url_job(doc_id="terms"):
    return {"kind": "url", "file_name": doc_id, "s3_url": "https://h/terms.pdf", "ext": ".pdf"}


class TestEnqueue:
    def test_enqueue_pushes_job_with_attempts(self, redis):
        with patch("ingest.queue.get_redis", return_value=redis):
            enqueue(_url_job())
        raw = redis.lrange(INGEST_QUEUE_KEY, 0, -1)
        assert len(raw) == 1
        assert json.loads(raw[0])["attempts"] == 0


class TestProcessOne:
    def test_idle_queue_returns_none(self, redis):
        assert process_one(redis, block_timeout=0) is None

    def test_url_job_processed_done(self, redis):
        with patch("ingest.queue.get_redis", return_value=redis):
            enqueue(_url_job())
        with patch("ingest.queue.process_policy", return_value={"doc_id": "terms", "status": "done"}) as mock_proc:
            result = process_one(redis, block_timeout=0)
        assert result["status"] == "done"
        mock_proc.assert_called_once()
        # Lock released after processing.
        assert redis.get(_lock_key("terms")) is None

    def test_transient_failure_retries_then_fails(self, redis):
        with patch("ingest.queue.get_redis", return_value=redis):
            enqueue(_url_job())

        settings = MagicMock(ingest_max_attempts=2)
        with (
            patch("ingest.queue.get_settings", return_value=settings),
            patch("ingest.queue.process_policy", side_effect=TimeoutError("flaky download")),
        ):
            # First attempt → transient → re-enqueued with attempts=1.
            first = process_one(redis, block_timeout=0)
            assert first["status"] == "retry"
            assert first["attempts"] == 1
            assert redis.llen(INGEST_QUEUE_KEY) == 1

            # Second attempt → attempts hits the cap → permanently failed.
            second = process_one(redis, block_timeout=0)
            assert second["status"] == "failed"
            assert redis.llen(INGEST_QUEUE_KEY) == 0

        # Status was recorded as failed for the doc.
        assert redis.hget("ingest_status:terms", "status") == "failed"

    def test_lock_prevents_double_processing(self, redis):
        with patch("ingest.queue.get_redis", return_value=redis):
            enqueue(_url_job())
        # Simulate another worker already holding the lock.
        redis.set(_lock_key("terms"), "1")
        with patch("ingest.queue.process_policy") as mock_proc:
            result = process_one(redis, block_timeout=0)
        assert result["status"] == "skipped"
        assert result["reason"] == "locked"
        mock_proc.assert_not_called()

    def test_upload_job_cleans_staged_file_on_success(self, redis):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"hello")
        tmp.close()
        job = {"kind": "upload", "file_name": "doc", "file_path": tmp.name, "ext": ".txt"}
        with patch("ingest.queue.get_redis", return_value=redis):
            enqueue(job)
        with patch("ingest.queue._run_ingest", return_value={"doc_id": "doc", "status": "done"}) as mock_run:
            result = process_one(redis, block_timeout=0)
        assert result["status"] == "done"
        mock_run.assert_called_once()
        import os

        assert not os.path.exists(tmp.name)  # staged upload removed after success


def test_non_transient_error_fails_immediately(redis):
    with patch("ingest.queue.get_redis", return_value=redis):
        enqueue(_url_job())
    # A ValueError (e.g. unsupported format) is not transient → no retry.
    with patch("ingest.queue.process_policy", side_effect=ValueError("unsupported format")):
        result = process_one(redis, block_timeout=0)
    assert result["status"] == "failed"
    assert redis.llen(INGEST_QUEUE_KEY) == 0
