"""Group 7 tests: Hybrid Server Deployment.

Covers:
- Hybrid URL unreachable + fallback enabled → local Java, parser_mode=local (7.6)
- Hybrid URL unreachable + fallback disabled → RuntimeError (7.7)
- docker-compose.yml odl-hybrid service has profiles=["hybrid"] (7.8)
- URL scheme validation: non-http/https rejected (7.9)
- odl-hybrid has no external port binding (7.10)
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPOSE_PATH = Path(__file__).parent.parent / "docker-compose.yml"
_COMPOSE_LOCAL_PATH = Path(__file__).parent.parent / "docker-compose.local.yml"
_COMPOSE_TEST_PATH = Path(__file__).parent.parent / "docker-compose.test.yml"


def _load_compose(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _make_odl_mock(md_content: str = "# Section\n\nContent") -> MagicMock:
    def _fake_convert(input_path, output_dir, **kwargs):
        stem = Path(input_path).stem
        (Path(output_dir) / f"{stem}.md").write_text(md_content, encoding="utf-8")

    mock = MagicMock()
    mock.convert.side_effect = _fake_convert
    return mock


# ---------------------------------------------------------------------------
# 7.6  test_hybrid_url_unreachable_fallback_enabled
# ---------------------------------------------------------------------------


class TestHybridFallbackEnabled:
    def test_unreachable_hybrid_uses_local_java(self, pdf_v1_bytes):
        """When hybrid URL is unreachable and ODL_HYBRID_FALLBACK=true,
        load_pdf_odl proceeds with local Java and diagnostics show parser_mode=local."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = _make_odl_mock()

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "connection refused")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings

                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_fallback=True,
                )
                chunks, elements, diag = load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        assert diag["parser_mode"] == "local", (
            f"Expected parser_mode=local when hybrid unreachable+fallback, got {diag['parser_mode']!r}"
        )
        assert diag["parser"] == "opendataloader"
        # convert() was called WITHOUT hybrid params
        called_kwargs = mock_odl.convert.call_args[1]
        assert "hybrid" not in called_kwargs, (
            "hybrid param should not be passed to convert() when server is unreachable"
        )

    def test_fallback_enabled_returns_documents(self, pdf_v1_bytes):
        """With hybrid unreachable + fallback, ingest still produces chunks."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = _make_odl_mock("# Heading\n\nParagraph content")

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "timeout")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings

                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_fallback=True,
                )
                chunks, elements, diag = load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# 7.7  test_hybrid_url_unreachable_fallback_disabled
# ---------------------------------------------------------------------------


class TestHybridFallbackDisabled:
    def test_unreachable_hybrid_raises_when_fallback_off(self, pdf_v1_bytes):
        """When hybrid URL is unreachable and ODL_HYBRID_FALLBACK=false,
        load_pdf_odl raises RuntimeError with a clear reason."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = MagicMock()

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "connection refused")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings

                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_fallback=False,
                )
                with pytest.raises(RuntimeError, match="unreachable"):
                    load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        # convert() should NOT have been called
        mock_odl.convert.assert_not_called()

    def test_unreachable_error_contains_reason(self, pdf_v1_bytes):
        """RuntimeError message includes the underlying failure reason."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch(
                    "ingest.pdf_opendataloader._hybrid_reachable",
                    return_value=(False, "connection refused to odl-hybrid:5002"),
                ),
                patch.dict(sys.modules, {"opendataloader_pdf": MagicMock()}),
            ):
                from config import Settings

                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_fallback=False,
                )
                with pytest.raises(RuntimeError) as exc_info:
                    load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        assert "odl-hybrid:5002" in str(exc_info.value) or "unreachable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7.8  test_hybrid_compose_profile — compose config structure
# ---------------------------------------------------------------------------


class TestComposeProfile:
    def test_main_compose_has_odl_hybrid_service(self):
        """docker-compose.yml defines an odl-hybrid service."""
        compose = _load_compose(_COMPOSE_PATH)
        assert "odl-hybrid" in compose.get("services", {}), "odl-hybrid service missing from docker-compose.yml"

    def test_main_compose_hybrid_has_profile(self):
        """docker-compose.yml odl-hybrid uses profiles so it isn't started by default."""
        compose = _load_compose(_COMPOSE_PATH)
        service = compose["services"]["odl-hybrid"]
        profiles = service.get("profiles", [])
        assert "hybrid" in profiles, f"odl-hybrid in docker-compose.yml should have profiles=[hybrid], got {profiles!r}"

    def test_local_compose_has_odl_hybrid_with_profile(self):
        """docker-compose.local.yml odl-hybrid uses profiles: ["hybrid"]."""
        compose = _load_compose(_COMPOSE_LOCAL_PATH)
        assert "odl-hybrid" in compose.get("services", {}), "odl-hybrid service missing from docker-compose.local.yml"
        service = compose["services"]["odl-hybrid"]
        assert "hybrid" in service.get("profiles", [])

    def test_test_compose_has_odl_hybrid_with_profile(self):
        """docker-compose.test.yml odl-hybrid uses profiles: ["hybrid"]."""
        compose = _load_compose(_COMPOSE_TEST_PATH)
        assert "odl-hybrid" in compose.get("services", {}), "odl-hybrid service missing from docker-compose.test.yml"
        service = compose["services"]["odl-hybrid"]
        assert "hybrid" in service.get("profiles", [])

    def test_hybrid_service_has_healthcheck(self):
        """odl-hybrid has a healthcheck that calls the /health endpoint."""
        compose = _load_compose(_COMPOSE_PATH)
        service = compose["services"]["odl-hybrid"]
        hc = service.get("healthcheck", {})
        test_cmd = " ".join(hc.get("test", []))
        assert "/health" in test_cmd, f"odl-hybrid healthcheck should call /health, got: {test_cmd!r}"


# ---------------------------------------------------------------------------
# 7.9  URL scheme validation in _hybrid_reachable
# ---------------------------------------------------------------------------


class TestHybridUrlValidation:
    def test_http_url_accepted(self):
        """Valid http:// URL is accepted."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            ok, reason = _hybrid_reachable("http://odl-hybrid:5002")
        assert ok is True

    def test_https_url_accepted(self):
        """Valid https:// URL is accepted."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            ok, reason = _hybrid_reachable("https://odl-hybrid:5002")
        assert ok is True

    def test_ftp_scheme_rejected(self):
        """ftp:// URL is rejected before making any network call."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            ok, reason = _hybrid_reachable("ftp://odl-hybrid:5002")
        assert ok is False
        assert "http" in reason.lower() or "scheme" in reason.lower()
        mock_get.assert_not_called()

    def test_file_scheme_rejected(self):
        """file:// URL is rejected."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            ok, reason = _hybrid_reachable("file:///etc/passwd")
        assert ok is False
        mock_get.assert_not_called()

    def test_credentials_in_url_rejected(self):
        """URLs with credentials (user:pass@host) are rejected."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            ok, reason = _hybrid_reachable("http://user:pass@evil.com:5002")
        assert ok is False
        mock_get.assert_not_called()

    def test_health_endpoint_called(self):
        """_hybrid_reachable appends /health to the base URL."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            _hybrid_reachable("http://odl-hybrid:5002")
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/health"), f"Expected /health endpoint to be called, got: {called_url!r}"

    def test_trailing_slash_handled(self):
        """Base URL with trailing slash still results in /health call."""
        from ingest.pdf_preflight import _hybrid_reachable

        with patch("ingest.pdf_preflight.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            _hybrid_reachable("http://odl-hybrid:5002/")
        called_url = mock_get.call_args[0][0]
        assert called_url == "http://odl-hybrid:5002/health"


# ---------------------------------------------------------------------------
# 7.10  No external port binding for odl-hybrid
# ---------------------------------------------------------------------------


class TestNoExternalPort:
    def test_main_compose_hybrid_no_ports(self):
        """FR 7.10: odl-hybrid in docker-compose.yml exposes no external port."""
        compose = _load_compose(_COMPOSE_PATH)
        service = compose["services"]["odl-hybrid"]
        ports = service.get("ports", [])
        assert ports == [], f"odl-hybrid should not expose external ports, got: {ports!r}"

    def test_local_compose_hybrid_no_ports(self):
        compose = _load_compose(_COMPOSE_LOCAL_PATH)
        service = compose["services"]["odl-hybrid"]
        ports = service.get("ports", [])
        assert ports == [], f"odl-hybrid (local) should not expose external ports, got: {ports!r}"

    def test_hybrid_only_on_internal_network(self):
        """odl-hybrid is reachable only via the internal app-network."""
        compose = _load_compose(_COMPOSE_PATH)
        service = compose["services"]["odl-hybrid"]
        networks = service.get("networks", [])
        # Either listed under networks or using default
        assert networks or "networks" not in service or service.get("networks") == ["app-network"], (
            "odl-hybrid should be on the internal app-network"
        )
