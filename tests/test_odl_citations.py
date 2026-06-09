"""Group 6 tests: Extended Citations + Per-Request API Override.

Covers:
- New Source fields present for ODL chunks (6.6)
- New Source fields absent/None for legacy chunks (6.7)
- parser override forces PyPDF (6.8)
- Invalid parser value → 422 (6.9)
- bbox validation: 4-element finite floats only (6.10)
- pages validation: pattern enforcement (6.11)
- IngestRequest schema accepts/rejects new fields
- _to_source() maps all four new metadata fields
"""

import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from ingest.pdf_opendataloader import _validate_bbox
from graph.nodes.retrieve_context import _to_source
from schemas.ingest import IngestRequest, _PAGES_PATTERN


# ---------------------------------------------------------------------------
# 6.6 / 6.7  _to_source — new fields present and absent
# ---------------------------------------------------------------------------

class TestToSourceNewFields:
    def test_odl_chunk_maps_all_four_fields(self):
        """ODL chunk with all metadata populated → all four new Source fields non-None."""
        doc = Document(
            page_content="| A | B | C |",
            metadata={
                "doc_id": "doc1",
                "source_file": "doc.pdf",
                "page_number": 3,
                "section_title": "Pricing Table",
                "element_type": "table",
                "page_end": 4,
                "bbox": [72.0, 680.0, 540.0, 740.0],
            },
        )
        source = _to_source(doc, score=0.9)
        assert source["section"] == "Pricing Table"
        assert source["element_type"] == "table"
        assert source["page_end"] == 4
        assert source["bbox"] == [72.0, 680.0, 540.0, 740.0]

    def test_legacy_chunk_new_fields_are_none(self):
        """Non-ODL chunk → all four new fields are None; no KeyError."""
        doc = Document(
            page_content="Regular text",
            metadata={"doc_id": "doc1", "source_file": "old.pdf", "page_number": 1},
        )
        source = _to_source(doc)
        assert source["section"] is None
        assert source["element_type"] is None
        assert source["page_end"] is None
        assert source["bbox"] is None

    def test_partial_metadata_does_not_raise(self):
        """Chunk with only some ODL fields present returns None for absent ones."""
        doc = Document(
            page_content="Section text",
            metadata={"section_title": "Intro", "element_type": "section"},
        )
        source = _to_source(doc)
        assert source["section"] == "Intro"
        assert source["element_type"] == "section"
        assert source["page_end"] is None
        assert source["bbox"] is None

    def test_standard_fields_still_present(self):
        """Existing standard fields are unaffected by new ODL fields."""
        doc = Document(
            page_content="Content",
            metadata={
                "doc_id": "x",
                "source_file": "x.pdf",
                "page_number": 2,
                "chunk_hash": "abc",
            },
        )
        source = _to_source(doc, score=0.75)
        assert source["label"] == "x.pdf"
        assert source["doc_id"] == "x"
        assert source["page"] == 2
        assert source["score"] == 0.75
        assert source["snippet"] == "Content"


# ---------------------------------------------------------------------------
# 6.8  parser override forces PyPDF
# ---------------------------------------------------------------------------

class TestParserOverride:
    def test_pypdf_override_in_build_chunks(self, ingest_env):
        """parser_override='pypdf' forces PyPDF regardless of ODL availability."""
        import os
        from ingest.policies import _build_chunks

        fake_redis, _ = ingest_env

        pdf_bytes = b"%PDF-1.4\n%test content"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            path = f.name

        try:
            with (
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch("ingest.policies.load_documents") as mock_load,
            ):
                mock_load.return_value = [
                    Document(page_content="PyPDF content", metadata={"page": 0})
                ]
                chunks, _, diag = _build_chunks(
                    path, "test-doc", "test.pdf", "abc", "v1", ".pdf",
                    parser_override="pypdf",
                )
        finally:
            os.unlink(path)

        # load_documents called with parser="pypdf"
        call_kwargs = mock_load.call_args
        assert call_kwargs[1].get("parser") == "pypdf" or (
            len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == "pypdf"
        ), f"Expected parser='pypdf', got call: {call_kwargs}"
        assert diag.get("parser") == "pypdf"


# ---------------------------------------------------------------------------
# 6.9  Invalid parser value → 422
# ---------------------------------------------------------------------------

class TestIngestRequestValidation:
    def test_valid_parser_pypdf_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            parser="pypdf",
        )
        assert req.parser == "pypdf"

    def test_valid_parser_opendataloader_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            parser="opendataloader",
        )
        assert req.parser == "opendataloader"

    def test_null_parser_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            parser=None,
        )
        assert req.parser is None

    def test_invalid_parser_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IngestRequest(
                file_name="testdoc",
                s3_url="https://example.com/doc.pdf",
                parser="unknown",
            )

    def test_valid_hybrid_mode_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            hybrid_mode="full",
        )
        assert req.hybrid_mode == "full"

    def test_invalid_hybrid_mode_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IngestRequest(
                file_name="testdoc",
                s3_url="https://example.com/doc.pdf",
                hybrid_mode="turbo",
            )

    def test_valid_pages_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            pages="1-10",
        )
        assert req.pages == "1-10"

    def test_valid_pages_multi_range_accepted(self):
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            pages="1-5,8,12-15",
        )
        assert req.pages == "1-5,8,12-15"

    def test_invalid_pages_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IngestRequest(
                file_name="testdoc",
                s3_url="https://example.com/doc.pdf",
                pages="../etc/passwd",
            )

    def test_backward_compatible_no_overrides(self):
        """Requests without the new fields work exactly as before."""
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
        )
        assert req.parser is None
        assert req.hybrid_mode is None
        assert req.pages is None


# ---------------------------------------------------------------------------
# 6.9  API endpoint rejects invalid parser (HTTP 422)
# ---------------------------------------------------------------------------

class TestApiParserValidation:
    def test_invalid_parser_returns_422(self):
        """POST /ingest with parser='badvalue' returns 422."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/ingest",
            json={
                "file_name": "testdoc",
                "s3_url": "https://example.com/doc.pdf",
                "parser": "badvalue",
            },
            headers={"X-API-Key": ""},
        )
        assert response.status_code == 422

    def test_valid_parser_passes_schema_validation(self):
        """parser='pypdf' passes Pydantic schema validation (no 422)."""
        from pydantic import ValidationError
        # If this doesn't raise, schema accepts the value → would not 422 at API level.
        req = IngestRequest(
            file_name="testdoc",
            s3_url="https://example.com/doc.pdf",
            parser="pypdf",
        )
        assert req.parser == "pypdf"


# ---------------------------------------------------------------------------
# 6.10  bbox validation
# ---------------------------------------------------------------------------

class TestBboxValidation:
    def test_valid_bbox_accepted(self):
        bbox = [72.0, 680.0, 540.0, 740.0]
        result = _validate_bbox(bbox)
        assert result == bbox

    def test_none_returns_none(self):
        assert _validate_bbox(None) is None

    def test_wrong_length_returns_none(self):
        assert _validate_bbox([1.0, 2.0, 3.0]) is None       # 3 elements
        assert _validate_bbox([1.0, 2.0, 3.0, 4.0, 5.0]) is None  # 5 elements

    def test_nan_returns_none(self):
        import math
        assert _validate_bbox([1.0, float("nan"), 3.0, 4.0]) is None

    def test_inf_returns_none(self):
        assert _validate_bbox([1.0, float("inf"), 3.0, 4.0]) is None
        assert _validate_bbox([1.0, 2.0, float("-inf"), 4.0]) is None

    def test_non_numeric_returns_none(self):
        assert _validate_bbox(["left", "bottom", "right", "top"]) is None
        assert _validate_bbox([None, None, None, None]) is None

    def test_integer_values_coerced_to_float(self):
        result = _validate_bbox([0, 100, 500, 200])
        assert result == [0.0, 100.0, 500.0, 200.0]
        assert all(isinstance(v, float) for v in result)

    def test_build_hierarchical_chunks_sanitises_bbox(self):
        """Bad bbox from ODL JSON is silently dropped to None in L2 metadata."""
        from ingest.pdf_opendataloader import OdlElement, build_hierarchical_chunks

        el_heading = OdlElement(id_=1, page_number=1, element_type="heading",
                                content="Section", heading_level=1)
        el_para = OdlElement(id_=2, page_number=1, element_type="paragraph",
                             content="Body text", section_title="Section",
                             bbox=[float("nan"), 0.0, 100.0, 20.0])

        _, l2 = build_hierarchical_chunks([el_heading, el_para])
        assert l2[0].metadata.get("bbox") is None

    def test_build_hierarchical_chunks_preserves_valid_bbox(self):
        from ingest.pdf_opendataloader import OdlElement, build_hierarchical_chunks

        el_heading = OdlElement(id_=1, page_number=1, element_type="heading",
                                content="Section", heading_level=1)
        valid_bbox = [10.0, 20.0, 300.0, 50.0]
        el_para = OdlElement(id_=2, page_number=1, element_type="paragraph",
                             content="Body", section_title="Section",
                             bbox=valid_bbox)

        _, l2 = build_hierarchical_chunks([el_heading, el_para])
        assert l2[0].metadata.get("bbox") == valid_bbox


# ---------------------------------------------------------------------------
# 6.11  pages validation
# ---------------------------------------------------------------------------

class TestPagesValidation:
    @pytest.mark.parametrize("valid", ["1", "1-10", "1-5,8", "1-5,8,12-15", "100"])
    def test_valid_pages_accepted(self, valid):
        assert _PAGES_PATTERN.match(valid), f"Expected {valid!r} to be valid"

    @pytest.mark.parametrize("invalid", [
        "../etc/passwd", "; rm -rf /", "$(whoami)", "abc", "1-", "-5", "1--10", ""
    ])
    def test_invalid_pages_rejected(self, invalid):
        assert not _PAGES_PATTERN.match(invalid), f"Expected {invalid!r} to be invalid"

    def test_load_pdf_odl_rejects_bad_pages(self, pdf_v1_bytes):
        """load_pdf_odl raises ValueError for invalid pages string."""
        from ingest.pdf_opendataloader import load_pdf_odl
        from unittest.mock import patch, MagicMock
        import sys

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        mock_odl = MagicMock()
        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                with pytest.raises(ValueError, match="pages must be"):
                    load_pdf_odl(path, settings=Settings(), pages="../hack")
        finally:
            import os; os.unlink(path)

    def test_load_pdf_odl_accepts_valid_pages(self, pdf_v1_bytes):
        """load_pdf_odl passes valid pages string to convert()."""
        from ingest.pdf_opendataloader import load_pdf_odl
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import sys

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_v1_bytes)
            path = f.name

        def _fake_convert(input_path, output_dir, **kwargs):
            stem = Path(input_path).stem
            (Path(output_dir) / f"{stem}.md").write_text("# Title\n\nContent", encoding="utf-8")

        mock_odl = MagicMock()
        mock_odl.convert.side_effect = _fake_convert

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                load_pdf_odl(path, settings=Settings(), pages="1-5")
        finally:
            import os; os.unlink(path)

        called_kwargs = mock_odl.convert.call_args[1]
        assert called_kwargs.get("pages") == "1-5"
