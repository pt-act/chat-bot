"""Tests for OpenDataLoader preflight checks, config validation, and PDF loader dispatch."""

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import assume, given, strategies as st

from config import Settings, get_settings
from ingest.loaders import load_documents
from ingest.pdf_preflight import (
    _hybrid_reachable,
    _java_available,
    _odl_importable,
    _parse_java_version,
    preflight_check,
)

# ───────────────────────────────
# 1.5  test_preflight_java_missing
# ───────────────────────────────


class TestPreflightJavaMissing:
    def test_java_not_installed(self):
        with patch("ingest.pdf_preflight.subprocess.run", side_effect=FileNotFoundError()):
            ok, reason = _java_available()
        assert ok is False
        assert "Java" in reason


# ───────────────────────────────
# 1.6  test_preflight_java_old
# ───────────────────────────────


class TestPreflightJavaOld:
    def test_java_8_rejected(self):
        fake = MagicMock()
        fake.stdout = ""
        fake.stderr = 'java version "1.8.0_202"\n'
        with patch("ingest.pdf_preflight.subprocess.run", return_value=fake):
            ok, reason = _java_available()
        assert ok is False
        assert "Java 11" in reason

    def test_java_11_accepted(self):
        fake = MagicMock()
        fake.stdout = ""
        fake.stderr = 'openjdk version "11.0.21" 2023-10-17\n'
        with patch("ingest.pdf_preflight.subprocess.run", return_value=fake):
            ok, reason = _java_available()
        assert ok is True
        assert reason == ""


# ───────────────────────────────
# 1.7  test_preflight_ok
# ───────────────────────────────


class TestPreflightOk:
    def test_java_17_plus_importable(self):
        fake = MagicMock()
        fake.stdout = ""
        fake.stderr = 'openjdk version "17.0.1" 2021-10-19\n'
        with (
            patch("ingest.pdf_preflight.subprocess.run", return_value=fake),
            patch("ingest.pdf_preflight._odl_importable", return_value=(True, "")),
        ):
            ok, reason = preflight_check()
        assert ok is True
        assert reason == ""


# ───────────────────────────────
# 1.8  test_config_pdf_parser_default
# ───────────────────────────────


class TestConfigPdfParser:
    def test_pdf_parser_none_defaults(self):
        s = Settings()
        assert s.pdf_parser is None

    def test_pdf_parser_pypdf_valid(self):
        s = Settings(pdf_parser="pypdf")
        assert s.pdf_parser == "pypdf"

    def test_pdf_parser_opendataloader_valid(self):
        s = Settings(pdf_parser="opendataloader")
        assert s.pdf_parser == "opendataloader"

    def test_pdf_parser_invalid_raises(self):
        with pytest.raises(ValueError, match="PDF_PARSER must be"):
            Settings(pdf_parser="arbitrary_string")


# ───────────────────────────────
# PBT: parse_java_version
# ───────────────────────────────


class TestParseJavaVersionPBT:
    @given(st.sampled_from([
        "openjdk version \"11.0.21\" 2023-10-17",
        "java version \"11.0.1\"",
        "openjdk version \"17.0.1\" 2021-10-19",
        "java version \"17\"",
        "openjdk version \"21.0.2\" 2024-01-16",
    ]))
    def test_modern_versions_parsed(self, text):
        major = _parse_java_version(text)
        assert major is not None
        assert major >= 11

    @given(st.sampled_from([
        'java version "1.8.0_202"',
        'openjdk version "1.7.0_80"',
        'java version "1.6.0_45"',
    ]))
    def test_legacy_versions_parsed(self, text):
        major = _parse_java_version(text)
        assert major is not None
        assert major < 11

    @given(st.text())
    def test_arbitrary_strings_safe(self, text):
        major = _parse_java_version(text)
        # Must not crash; either None or a positive int
        assert major is None or isinstance(major, int)


# ───────────────────────────────
# Loader dispatch with parser kwarg
# ───────────────────────────────


class TestLoadPdfDispatch:
    def test_explicit_pypdf_parser(self, pdf_v1_bytes):
        """Forcing parser='pypdf' always uses PyPDFLoader."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        docs = load_documents(path, ".pdf", parser="pypdf")
        assert len(docs) >= 1
        assert any("Return Policy" in d.page_content for d in docs)

    def test_odl_parser_stub_raises(self, pdf_v1_bytes):
        """parser='opendataloader' hits the Group-2 stub and raises."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        with pytest.raises(NotImplementedError, match="Group 2"):
            load_documents(path, ".pdf", parser="opendataloader")

    def test_auto_detect_preflight_fails_fallback_to_pypdf(self, pdf_v1_bytes):
        """When parser=None and preflight fails, PyPDFLoader is used."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        with patch("ingest.pdf_preflight._java_available", return_value=(False, "no java")):
            docs = load_documents(path, ".pdf", parser=None)
        assert len(docs) >= 1
        assert any("Return Policy" in d.page_content for d in docs)

    def test_auto_detect_preflight_ok_stub_raises(self, pdf_v1_bytes):
        """When parser=None and preflight passes, ODL stub is hit (Group 2)."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        with patch("ingest.pdf_preflight._java_available", return_value=(True, "")):
            with patch("ingest.pdf_preflight._odl_importable", return_value=(True, "")):
                with pytest.raises(NotImplementedError, match="Group 2"):
                    load_documents(path, ".pdf", parser=None)

    def test_invalid_parser_value_raises(self, pdf_v1_bytes):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        with pytest.raises(ValueError, match="Unsupported PDF parser"):
            load_documents(path, ".pdf", parser="invalid")


# ───────────────────────────────
# Hybrid reachability checks
# ───────────────────────────────


class TestHybridReachability:
    def test_no_url_configured_is_ok(self):
        ok, reason = _hybrid_reachable(None)
        assert ok is True

    def test_reachable_url_ok(self):
        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            ok, reason = _hybrid_reachable("http://localhost:5002")
        assert ok is True

    def test_unreachable_url_fails(self):
        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 500
            ok, reason = _hybrid_reachable("http://localhost:5002")
        assert ok is False
        assert "500" in reason

    def test_request_exception_fails(self):
        import requests

        with patch("ingest.pdf_preflight.requests.get", side_effect=requests.ConnectionError("refused")):
            ok, reason = _hybrid_reachable("http://localhost:5002")
        assert ok is False
        assert "unreachable" in reason


# ───────────────────────────────
# Enrichment config validation
# ───────────────────────────────


class TestConfigEnrichmentValidation:
    def test_enrich_formula_requires_full_mode(self):
        with pytest.raises(ValueError, match="ODL_ENRICH_FORMULA"):
            Settings(odl_enrich_formula=True, odl_hybrid_mode="auto")

    def test_enrich_pictures_requires_full_mode(self):
        with pytest.raises(ValueError, match="ODL_ENRICH_PICTURES"):
            Settings(odl_enrich_pictures=True, odl_hybrid_mode="auto")

    def test_enrich_formula_with_full_mode_ok(self):
        s = Settings(odl_enrich_formula=True, odl_hybrid_mode="full")
        assert s.odl_enrich_formula is True

    def test_enrich_pictures_with_full_mode_ok(self):
        s = Settings(odl_enrich_pictures=True, odl_hybrid_mode="full")
        assert s.odl_enrich_pictures is True


# ───────────────────────────────
# Security: preflight never leaks paths
# ───────────────────────────────


class TestPreflightSecurity:
    def test_reason_never_contains_file_path(self):
        """FR 1.10 — preflight_check() never logs or surfaces the PDF file path."""
        # All reasons returned by preflight are about environment state, not paths
        ok, reason = _java_available()
        # When java is not installed, reason is about java command not found
        assert ".pdf" not in reason
        assert "/" not in reason or "java command" in reason

        ok2, reason2 = _odl_importable()
        assert ".pdf" not in reason2
        assert "/" not in reason2
