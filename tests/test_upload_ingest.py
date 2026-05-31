"""Tests for local document upload ingestion (POST /api/v1/ingest/upload) and process_uploaded."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import fakeredis
from fastapi.testclient import TestClient

import main as main_module
from ingest.keys import ingest_status_key
from ingest.policies import process_uploaded


def _client():
    with patch("middlewares.rate_limiter.get_redis", return_value=fakeredis.FakeRedis(decode_responses=True)):
        return TestClient(main_module.app)


class TestUploadEndpoint:
    def test_valid_pdf_returns_202_and_schedules(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("Q3 Report.pdf", b"%PDF-1.4 minimal body", "application/pdf")},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        # filename sanitized into a safe doc id
        assert body["doc_id"] == "Q3_Report"
        assert resp.headers["Location"] == "/api/v1/ingest/status/Q3_Report"
        assert redis.hget(ingest_status_key("Q3_Report"), "status") == "queued"
        mock_ingest.assert_called_once()
        called_doc_id, called_path, called_ext = mock_ingest.call_args[0]
        assert called_doc_id == "Q3_Report"
        assert called_ext == ".pdf"
        # temp file was written; clean it up (the mocked background task won't)
        assert os.path.exists(called_path)
        os.remove(called_path)

    def test_explicit_file_name_used(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("whatever.pdf", b"%PDF-1.4 body", "application/pdf")},
                data={"file_name": "returns_policy"},
            )
        assert resp.status_code == 202
        assert resp.json()["doc_id"] == "returns_policy"
        os.remove(mock_ingest.call_args[0][1])

    def test_txt_upload_accepted(self):
        # Non-PDF formats are now supported — a .txt needs no magic-byte check.
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("notes.txt", b"just plain text", "text/plain")},
            )
        assert resp.status_code == 202
        assert resp.json()["doc_id"] == "notes"
        assert mock_ingest.call_args[0][2] == ".txt"
        os.remove(mock_ingest.call_args[0][1])

    def test_unsupported_format_rejected_415(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("malware.exe", b"MZ\x90\x00binary", "application/octet-stream")},
            )
        assert resp.status_code == 415
        mock_ingest.assert_not_called()

    def test_pdf_with_bad_magic_rejected_415(self):
        # A file claiming .pdf but lacking the %PDF header is still rejected.
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("fake.pdf", b"this is not really a pdf", "application/pdf")},
            )
        assert resp.status_code == 415
        mock_ingest.assert_not_called()

    def test_oversize_rejected_413(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
            patch("controllers.v1.ingest.get_settings", return_value=MagicMock(max_file_size_mb=0)),
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("big.pdf", b"%PDF-1.4 " + b"x" * 2048, "application/pdf")},
            )
        assert resp.status_code == 413
        mock_ingest.assert_not_called()

    def test_empty_file_rejected_415(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
        assert resp.status_code == 415
        mock_ingest.assert_not_called()

    def test_bad_explicit_file_name_rejected_400(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with (
            patch("controllers.v1.ingest.get_redis", return_value=redis),
            patch("controllers.v1.ingest.ingest_local_file") as mock_ingest,
        ):
            resp = _client().post(
                "/api/v1/ingest/upload",
                files={"file": ("x.pdf", b"%PDF-1.4 body", "application/pdf")},
                data={"file_name": "bad/name"},
            )
        assert resp.status_code == 400
        mock_ingest.assert_not_called()


class TestNameHelpers:
    def test_sanitize_doc_id_slugifies_and_strips(self):
        from schemas.ingest import sanitize_doc_id

        assert sanitize_doc_id("/tmp/Q3 Report.final.PDF") == "Q3_Report_final"
        assert sanitize_doc_id("report.pdf") == "report"
        assert sanitize_doc_id("notes.txt") == "notes"
        assert sanitize_doc_id("@@@.pdf") == "document"  # nothing usable → fallback

    def test_clean_file_name_rejects_unsafe(self):
        import pytest

        from schemas.ingest import clean_file_name

        assert clean_file_name("returns_policy") == "returns_policy"
        for bad in ["", "a/b", "a.b"]:
            with pytest.raises(ValueError):
                clean_file_name(bad)


class TestProcessUploaded:
    def test_ingests_local_pdf_end_to_end(self, pdf_v1_bytes, ingest_env):
        # ingest_env patches ingest.policies.get_redis + get_vectorstore (fakeredis + Chroma).
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(pdf_v1_bytes)
        tmp.close()

        result = process_uploaded("local_policy", tmp.name, ".pdf")

        assert result["status"] == "done"
        assert result["added"] > 0
        assert result["added"] == result["total"]
        # the helper removes its input file when finished
        assert not os.path.exists(tmp.name)

    def test_ingests_local_text_end_to_end(self, ingest_env):
        # Exercises the non-PDF (plain-text) loader path through the shared pipeline.
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"Refunds are issued within 5 business days. Contact support for help.\n" * 5)
        tmp.close()

        result = process_uploaded("notes", tmp.name, ".txt")

        assert result["status"] == "done"
        assert result["added"] > 0
        assert not os.path.exists(tmp.name)

    def test_failure_marks_status_and_cleans_up(self, ingest_env):
        fake_redis, _vs = ingest_env
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"not a real pdf")  # PyPDFLoader will fail
        tmp.close()

        import pytest

        with pytest.raises(Exception):
            process_uploaded("broken", tmp.name, ".pdf")

        assert fake_redis.hget(ingest_status_key("broken"), "status") == "failed"
        assert not os.path.exists(tmp.name)
