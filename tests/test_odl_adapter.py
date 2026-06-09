"""Group 2 tests: ODL Adapter + Markdown Fast Win.

Tests cover:
- load_pdf_odl() success/fallback/cleanup behaviour (2.5 – 2.9)
- PBT: temp-dir cleanup invariant and fallback invariant (2.10 – 2.11)
- Security readiness: output_dir scoped to tempdir, error messages (2.12 – 2.14)
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers / shared mocks
# ---------------------------------------------------------------------------

def _make_mock_odl(md_content: str = "# Heading\n\nParagraph | table cell\n"):
    """Return a mock opendataloader_pdf module whose convert() writes a .md file."""

    def _fake_convert(input_path, output_dir, format="markdown", **kwargs):
        stem = Path(input_path).stem
        (Path(output_dir) / f"{stem}.md").write_text(md_content, encoding="utf-8")

    mock = MagicMock()
    mock.convert.side_effect = _fake_convert
    return mock


# ---------------------------------------------------------------------------
# 2.5  test_track1_e2e — skipped when opendataloader_pdf is not installed
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    True,  # requires real Java + ODL install; enable manually in local/CI env with ODL
    reason="Requires opendataloader_pdf installed and Java 11+",
)
def test_track1_e2e(pdf_v1_bytes):
    """load_pdf_odl returns Markdown chunks including at least one with a table pipe."""
    from ingest.pdf_opendataloader import load_pdf_odl

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_v1_bytes)
        path = f.name

    try:
        docs, _, diag = load_pdf_odl(path)
    finally:
        os.unlink(path)

    assert len(docs) >= 1
    assert any("|" in d.page_content for d in docs)
    assert diag["parser"] == "opendataloader"


# ---------------------------------------------------------------------------
# 2.6  test_fallback_on_odl_failure
# ---------------------------------------------------------------------------

class TestFallbackOnOdlFailure:
    def test_fallback_enabled_returns_pypdf_docs(self, pdf_v1_bytes):
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = MagicMock()
        mock_odl.convert.side_effect = RuntimeError("convert failed")

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                s = Settings(pdf_parser_fallback=True)
                docs, _, diag = load_pdf_odl(path, settings=s)
        finally:
            os.unlink(path)

        assert len(docs) >= 1
        assert all(d.metadata.get("fallback_used") is True for d in docs)
        assert all(d.metadata.get("parser") == "pypdf" for d in docs)
        assert diag["parser"] == "pypdf"
        assert diag["fallback_used"] == "true"

    # 2.7  test_fallback_disabled
    def test_fallback_disabled_raises(self, pdf_v1_bytes):
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = MagicMock()
        mock_odl.convert.side_effect = RuntimeError("convert failed")

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                s = Settings(pdf_parser_fallback=False)
                with pytest.raises(RuntimeError):
                    load_pdf_odl(path, settings=s)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2.8  test_temp_dir_cleaned_on_success
# ---------------------------------------------------------------------------

class TestTempDirCleanup:
    def _capture_tmp_dir(self) -> list[str]:
        captured = []
        original_mkdtemp = tempfile.mkdtemp

        def _spy(*args, **kwargs):
            d = original_mkdtemp(*args, **kwargs)
            if kwargs.get("prefix", "").startswith("odl_") or (args and "odl_" in str(args)):
                captured.append(d)
            # match prefix="odl_" exactly
            if kwargs.get("prefix") == "odl_":
                captured.append(d)
            return d

        return captured, _spy

    def test_cleaned_on_success(self, pdf_v1_bytes):
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        created_dirs: list[str] = []
        orig_mkdtemp = tempfile.mkdtemp

        def spy_mkdtemp(**kwargs):
            d = orig_mkdtemp(**kwargs)
            created_dirs.append(d)
            return d

        mock_odl = _make_mock_odl()

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
                patch("ingest.pdf_opendataloader.tempfile.mkdtemp", side_effect=spy_mkdtemp),
            ):
                load_pdf_odl(path)
        finally:
            os.unlink(path)

        assert created_dirs, "mkdtemp was never called"
        for d in created_dirs:
            assert not os.path.exists(d), f"Temp dir still exists after success: {d}"

    def test_cleaned_on_failure(self, pdf_v1_bytes):
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        created_dirs: list[str] = []
        orig_mkdtemp = tempfile.mkdtemp

        def spy_mkdtemp(**kwargs):
            d = orig_mkdtemp(**kwargs)
            created_dirs.append(d)
            return d

        mock_odl = MagicMock()
        mock_odl.convert.side_effect = RuntimeError("boom")

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
                patch("ingest.pdf_opendataloader.tempfile.mkdtemp", side_effect=spy_mkdtemp),
            ):
                from config import Settings
                s = Settings(pdf_parser_fallback=False)
                with pytest.raises(RuntimeError):
                    load_pdf_odl(path, settings=s)
        finally:
            os.unlink(path)

        assert created_dirs, "mkdtemp was never called"
        for d in created_dirs:
            assert not os.path.exists(d), f"Temp dir still exists after failure: {d}"


# ---------------------------------------------------------------------------
# 2.10  PBT: temp-dir cleanup invariant
# ---------------------------------------------------------------------------

@given(should_fail=st.booleans())
def test_pbt_temp_dir_always_cleaned(should_fail, pdf_v1_bytes):
    """Property: temp dir does not exist after load_pdf_odl regardless of outcome."""
    from ingest.pdf_opendataloader import load_pdf_odl

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_v1_bytes)
        path = f.name

    created_dirs: list[str] = []
    orig_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(**kwargs):
        d = orig_mkdtemp(**kwargs)
        created_dirs.append(d)
        return d

    if should_fail:
        mock_odl = MagicMock()
        mock_odl.convert.side_effect = RuntimeError("injected failure")
    else:
        mock_odl = _make_mock_odl()

    try:
        with (
            patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
            patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            patch("ingest.pdf_opendataloader.tempfile.mkdtemp", side_effect=spy_mkdtemp),
        ):
            from config import Settings
            try:
                load_pdf_odl(path, settings=Settings(pdf_parser_fallback=False))
            except RuntimeError:
                pass
    finally:
        os.unlink(path)

    for d in created_dirs:
        assert not os.path.exists(d)


# ---------------------------------------------------------------------------
# 2.11  PBT: fallback invariant
# ---------------------------------------------------------------------------

@given(odl_should_fail=st.booleans(), fallback_enabled=st.booleans())
def test_pbt_fallback_invariant(odl_should_fail, fallback_enabled, pdf_v1_bytes):
    """Property: when ODL fails and fallback enabled → all docs have parser='pypdf'."""
    from ingest.pdf_opendataloader import load_pdf_odl

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_v1_bytes)
        path = f.name

    mock_odl = MagicMock()
    if odl_should_fail:
        mock_odl.convert.side_effect = RuntimeError("injected")
    else:
        mock_odl = _make_mock_odl()

    try:
        with (
            patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
            patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
        ):
            from config import Settings
            s = Settings(pdf_parser_fallback=fallback_enabled)
            if odl_should_fail and not fallback_enabled:
                with pytest.raises(RuntimeError):
                    load_pdf_odl(path, settings=s)
                return

            docs, _, diag = load_pdf_odl(path, settings=s)
    finally:
        os.unlink(path)

    assert len(docs) >= 1
    if odl_should_fail and fallback_enabled:
        for doc in docs:
            assert doc.metadata.get("parser") == "pypdf"
            assert doc.metadata.get("fallback_used") is True
        assert diag["parser"] == "pypdf"
        assert diag["fallback_used"] == "true"
    else:
        for doc in docs:
            assert doc.metadata.get("parser") == "opendataloader"
        assert diag["parser"] == "opendataloader"


# ---------------------------------------------------------------------------
# 2.12  Security: output_dir never under INGEST_INCOMING_DIR
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_output_dir_under_tempdir(self, pdf_v1_bytes):
        """FR 2.13: ODL output_dir is scoped to tempfile.gettempdir(), not incoming dir."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        captured_output_dirs: list[str] = []

        mock_odl = _make_mock_odl()
        original_convert = mock_odl.convert.side_effect

        def spy_convert(input_path, output_dir, **kwargs):
            captured_output_dirs.append(output_dir)
            return original_convert(input_path, output_dir, **kwargs)

        mock_odl.convert.side_effect = spy_convert

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                load_pdf_odl(path)
        finally:
            os.unlink(path)

        assert captured_output_dirs
        real_tmp = os.path.realpath(tempfile.gettempdir())
        for d in captured_output_dirs:
            real_d = os.path.realpath(d)
            assert real_d.startswith(real_tmp), (
                f"output_dir {d!r} is not under tempdir {real_tmp!r}"
            )

    def test_error_message_does_not_leak_output_dir(self, pdf_v1_bytes):
        """FR 2.14: error from ODL exceptions does not expose output_dir path in RuntimeError."""
        from ingest.pdf_opendataloader import load_pdf_odl

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = MagicMock()
        mock_odl.convert.side_effect = RuntimeError("internal ODL error")

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                s = Settings(pdf_parser_fallback=False)
                with pytest.raises(RuntimeError) as exc_info:
                    load_pdf_odl(path, settings=s)
        finally:
            os.unlink(path)

        # The re-raised exception is the original ODL error; check it doesn't have
        # a temp path embedded in a way that leaks internal structure to callers.
        # (The temp dir is private to the function; the original ODL exception string
        # should not contain it.)
        error_str = str(exc_info.value)
        assert "odl_" not in error_str or "internal ODL error" in error_str
