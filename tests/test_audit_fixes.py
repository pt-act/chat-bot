"""Regression tests for issues found during the code-quality audit.

Each test maps to a finding in audit_report.md and fails against the
pre-fix code, guarding against reintroduction.
"""

from unittest.mock import MagicMock, patch

import responses as resp

from graph.nodes.retrieve_context import _to_source
from ingest.policies import process_policy
from utils.llm_adapter import get_llm


def _source_label(doc):
    """Label resolution used to be `_source_of`; now derived from the structured source."""
    return _to_source(doc)["label"]


# ── Finding: get_llm() ignored generation params / raised TypeError ──────────────
# graph nodes call get_llm(temperature=..., max_tokens=...) but the function
# took no arguments, so the real (unmocked) chat path raised TypeError.
class TestGetLlmAcceptsGenerationParams:
    def setup_method(self):
        get_llm.cache_clear()

    @patch("utils.llm_adapter.get_settings")
    def test_openai_forwards_temperature_and_max_tokens(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openai", llm_model="gpt-4o-mini", llm_base_url="", openai_api_key=""
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            get_llm(temperature=0.3, max_tokens=512)
            mock_cls.assert_called_once_with(model="gpt-4o-mini", temperature=0.3, max_tokens=512)

    @patch("utils.llm_adapter.get_settings")
    def test_google_missing_key_raises_valueerror_not_importerror(self, mock_settings):
        # Key validation must happen *before* importing the optional package.
        mock_settings.return_value = MagicMock(
            llm_provider="google", llm_model="gemini-1.5-flash", llm_base_url="", google_api_key=""
        )
        import pytest

        with pytest.raises(ValueError, match="GOOGLE_API_KEY is required"):
            get_llm()


# ── Finding: retrieve_context reported "unknown" sources for ingested docs ───────
# Ingest writes the filename under metadata["source_file"]; retrieval read
# metadata["source"], so every real policy chunk surfaced as "unknown".
class TestSourceResolution:
    def test_prefers_source_file_key(self):
        doc = MagicMock()
        doc.metadata = {"source_file": "return_policy.pdf"}
        assert _source_label(doc) == "return_policy.pdf"

    def test_falls_back_to_source_key_for_synthesized_docs(self):
        doc = MagicMock()
        doc.metadata = {"source": "synthesized:abc123"}
        assert _source_label(doc) == "synthesized:abc123"

    def test_unknown_when_no_source_metadata(self):
        doc = MagicMock()
        doc.metadata = {}
        assert _source_label(doc) == "unknown"


# ── doc_id derivation ────────────────────────────────────────────────────────────
# `file_name` is validated dot-free (schemas.ingest.clean_file_name) and used as the
# doc_id verbatim; the document format is inferred from the URL extension, separately.
class TestDocId:
    @resp.activate
    def test_doc_id_is_file_name_verbatim(self, pdf_v1_bytes, ingest_env):
        url = "https://test-bucket.s3.amazonaws.com/app.pdf"
        resp.add(resp.GET, url, body=pdf_v1_bytes, status=200)
        result = process_policy("app", url)
        assert result["doc_id"] == "app"


# ── Finding: SSRF allowlist bypass via HTTP redirect ─────────────────────────────
# An allowed public URL could 30x-redirect to a private/metadata address.
# The download must not follow redirects.
class TestDownloadDoesNotFollowRedirects:
    @resp.activate
    def test_redirect_to_private_host_is_not_followed(self, ingest_env):
        import pytest

        public = "https://test-bucket.s3.amazonaws.com/return_policy.pdf"
        internal = "http://169.254.169.254/latest/meta-data/"
        resp.add(resp.GET, public, status=302, headers={"Location": internal})

        # With allow_redirects=False the 30x body is empty, so ingestion fails
        # loudly instead of silently fetching the internal target.
        with pytest.raises(Exception):
            process_policy("return_policy", public)

        # The internal/metadata target must never have been requested.
        requested = [c.request.url for c in resp.calls]
        assert all("169.254.169.254" not in u for u in requested)
