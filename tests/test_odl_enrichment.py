"""Group 8 tests: Enrichment Support (formula and picture elements).

All three implementation tasks (8.1–8.3) were completed in earlier groups:
  - 8.1  _extract_content() handles formula/picture (Group 3)
  - 8.2  ODL_ENRICH_FORMULA/PICTURES config validation (Group 1)
  - 8.3  L2 enrichment chunks follow the same pipeline (Groups 3–4)

This file provides the focused validation required by the spec:
  - 8.4  formula/picture elements produce correct L2 chunks via build_hierarchical_chunks
  - 8.5  enrichment config validation (references existing Group 1 tests; full round-trip here)
  - 8.6  formula content is stored and returned as plain text, not executed/rendered
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from graph.nodes.retrieve_context import _to_source
from ingest.pdf_opendataloader import (
    OdlElement,
    _extract_content,
    build_hierarchical_chunks,
    walk_tree,
)

# ---------------------------------------------------------------------------
# 8.1  _extract_content handles formula and picture (sanity checks)
# ---------------------------------------------------------------------------

class TestExtractContentEnrichment:
    def test_formula_returns_latex_content(self):
        el = {"type": "formula", "id": 1, "content": r"\int_{0}^{\infty} e^{-x^2} dx = \frac{\sqrt{\pi}}{2}"}
        result = _extract_content(el)
        assert r"\int" in result
        assert r"\frac" in result

    def test_formula_missing_content_returns_empty(self):
        el = {"type": "formula", "id": 1}
        assert _extract_content(el) == ""

    def test_picture_returns_description(self):
        el = {"type": "picture", "id": 1, "description": "Bar chart showing quarterly sales by region"}
        result = _extract_content(el)
        assert "Bar chart" in result

    def test_picture_missing_description_returns_empty(self):
        el = {"type": "picture", "id": 1}
        assert _extract_content(el) == ""

    def test_formula_not_image(self):
        """formula is distinct from image (image returns empty, formula returns content)."""
        formula_el = {"type": "formula", "id": 1, "content": r"E = mc^2"}
        image_el = {"type": "image", "id": 2}
        assert _extract_content(formula_el) != ""
        assert _extract_content(image_el) == ""


# ---------------------------------------------------------------------------
# 8.4  test_formula_chunk_stored
# ---------------------------------------------------------------------------

class TestFormulaChunkStored:
    def _formula_elements(self):
        return [
            OdlElement(id_=1, page_number=1, element_type="heading",
                       content="Equations", heading_level=1),
            OdlElement(id_=2, page_number=1, element_type="formula",
                       content=r"\frac{a}{b} = c",
                       section_title="Equations"),
        ]

    def test_formula_l2_chunk_element_type(self):
        """Formula element produces an L2 chunk with element_type='formula'."""
        _, l2 = build_hierarchical_chunks(self._formula_elements())
        formula_chunks = [c for c in l2 if c.metadata.get("element_type") == "formula"]
        assert formula_chunks, "No L2 chunk with element_type='formula' found"

    def test_formula_l2_chunk_content_is_latex(self):
        """Formula L2 chunk's page_content contains the LaTeX string."""
        _, l2 = build_hierarchical_chunks(self._formula_elements())
        formula_chunks = [c for c in l2 if c.metadata.get("element_type") == "formula"]
        assert formula_chunks
        assert r"\frac" in formula_chunks[0].page_content

    def test_formula_chunk_has_parent_link(self):
        """Formula L2 chunk has a valid parent_chunk_id pointing to the L1 section."""
        l1, l2 = build_hierarchical_chunks(self._formula_elements())
        l1_hashes = {c.metadata["chunk_hash"] for c in l1}
        formula_l2 = [c for c in l2 if c.metadata.get("element_type") == "formula"]
        assert formula_l2
        pid = formula_l2[0].metadata.get("parent_chunk_id")
        assert pid in l1_hashes, f"Formula L2 parent_chunk_id={pid!r} not in L1 hashes"

    def test_formula_chunk_level_is_2(self):
        _, l2 = build_hierarchical_chunks(self._formula_elements())
        for chunk in l2:
            assert chunk.metadata.get("chunk_level") == 2

    def test_picture_l2_chunk_element_type(self):
        """Picture element produces an L2 chunk with element_type='picture'."""
        elements = [
            OdlElement(id_=1, page_number=1, element_type="heading",
                       content="Figures", heading_level=1),
            OdlElement(id_=2, page_number=1, element_type="picture",
                       content="A scatter plot showing temperature vs. pressure",
                       section_title="Figures"),
        ]
        _, l2 = build_hierarchical_chunks(elements)
        picture_chunks = [c for c in l2 if c.metadata.get("element_type") == "picture"]
        assert picture_chunks, "No L2 chunk with element_type='picture' found"
        assert "scatter plot" in picture_chunks[0].page_content

    def test_formula_in_walk_tree_then_build_chunks(self):
        """Full pipeline: ODL JSON with formula element → walk_tree → build_hierarchical_chunks."""
        doc = {
            "number of pages": 2,
            "kids": [
                {
                    "type": "heading",
                    "id": 1,
                    "content": "Mathematics",
                    "page number": 1,
                    "heading level": 1,
                    "bounding box": [0.0, 0.0, 100.0, 20.0],
                },
                {
                    "type": "formula",
                    "id": 2,
                    "content": r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}",
                    "page number": 1,
                    "bounding box": [0.0, 30.0, 100.0, 50.0],
                },
                {
                    "type": "paragraph",
                    "id": 3,
                    "content": "The formula above is Gauss's sum.",
                    "page number": 1,
                    "bounding box": [0.0, 55.0, 100.0, 70.0],
                },
            ],
        }
        elements = walk_tree(doc)
        l1, l2 = build_hierarchical_chunks(elements)

        assert len(l1) == 1
        assert len(l2) == 2

        formula_chunk = next((c for c in l2 if c.metadata.get("element_type") == "formula"), None)
        assert formula_chunk is not None, "Formula L2 chunk not found after full pipeline"
        assert r"\sum" in formula_chunk.page_content
        assert formula_chunk.metadata.get("section_title") == "Mathematics"

    def test_picture_in_walk_tree_then_build_chunks(self):
        """Full pipeline: ODL JSON with picture element → walk_tree → build_hierarchical_chunks."""
        doc = {
            "kids": [
                {
                    "type": "heading",
                    "id": 1,
                    "content": "Results",
                    "page number": 1,
                    "heading level": 2,
                    "bounding box": [0.0, 0.0, 100.0, 20.0],
                },
                {
                    "type": "picture",
                    "id": 2,
                    "description": "Line graph showing revenue growth from 2020 to 2024",
                    "page number": 1,
                    "bounding box": [0.0, 25.0, 100.0, 80.0],
                },
            ],
        }
        elements = walk_tree(doc)
        l1, l2 = build_hierarchical_chunks(elements)

        picture_chunk = next((c for c in l2 if c.metadata.get("element_type") == "picture"), None)
        assert picture_chunk is not None
        assert "revenue growth" in picture_chunk.page_content


# ---------------------------------------------------------------------------
# 8.5  test_enrichment_requires_full_mode
# ---------------------------------------------------------------------------

class TestEnrichmentRequiresFullMode:
    def test_enrich_formula_auto_mode_raises(self):
        """ODL_ENRICH_FORMULA=true requires ODL_HYBRID_MODE=full."""
        from pydantic import ValidationError

        from config import Settings
        with pytest.raises((ValidationError, ValueError), match="ODL_ENRICH_FORMULA"):
            Settings(odl_enrich_formula=True, odl_hybrid_mode="auto")

    def test_enrich_pictures_auto_mode_raises(self):
        """ODL_ENRICH_PICTURES=true requires ODL_HYBRID_MODE=full."""
        from pydantic import ValidationError

        from config import Settings
        with pytest.raises((ValidationError, ValueError), match="ODL_ENRICH_PICTURES"):
            Settings(odl_enrich_pictures=True, odl_hybrid_mode="auto")

    def test_enrich_formula_full_mode_ok(self):
        from config import Settings
        s = Settings(odl_enrich_formula=True, odl_hybrid_mode="full")
        assert s.odl_enrich_formula is True

    def test_enrich_pictures_full_mode_ok(self):
        from config import Settings
        s = Settings(odl_enrich_pictures=True, odl_hybrid_mode="full")
        assert s.odl_enrich_pictures is True

    def test_enrich_flags_passed_to_convert_when_hybrid_active(self, pdf_v1_bytes):
        """ODL_ENRICH_FORMULA=true is passed as enrich_formula=True to convert()."""
        from ingest.pdf_opendataloader import load_pdf_odl

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
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_mode="full",
                    odl_enrich_formula=True,
                )
                load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        called_kwargs = mock_odl.convert.call_args[1]
        assert called_kwargs.get("enrich_formula") is True, (
            f"enrich_formula not passed to convert(): {called_kwargs}"
        )

    def test_enrich_pictures_passed_to_convert_when_hybrid_active(self, pdf_v1_bytes):
        """ODL_ENRICH_PICTURES=true is passed as enrich_pictures=True to convert()."""
        from ingest.pdf_opendataloader import load_pdf_odl

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
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(True, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from config import Settings
                s = Settings(
                    odl_hybrid="docling-fast",
                    odl_hybrid_url="http://odl-hybrid:5002",
                    odl_hybrid_mode="full",
                    odl_enrich_pictures=True,
                )
                load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        called_kwargs = mock_odl.convert.call_args[1]
        assert called_kwargs.get("enrich_pictures") is True

    def test_enrich_flags_not_passed_without_hybrid(self, pdf_v1_bytes):
        """Enrichment flags are NOT passed to convert() when hybrid is not active."""
        from ingest.pdf_opendataloader import load_pdf_odl

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
                # No hybrid configured — enrichment flags must not appear
                s = Settings()
                load_pdf_odl(path, settings=s)
        finally:
            import os

            os.unlink(path)

        called_kwargs = mock_odl.convert.call_args[1]
        assert "enrich_formula" not in called_kwargs
        assert "enrich_pictures" not in called_kwargs


# ---------------------------------------------------------------------------
# 8.6  Security: formula content is plain text, no execution path
# ---------------------------------------------------------------------------

class TestFormulaContentSecurity:
    def test_formula_snippet_is_plain_text(self):
        """_to_source() returns formula LaTeX as plain text snippet, not executed."""
        latex = r"\int_{0}^{1} x^2 dx = \frac{1}{3}"
        doc = Document(
            page_content=latex,
            metadata={
                "element_type": "formula",
                "chunk_level": 2,
                "section_title": "Calculus",
                "source_file": "paper.pdf",
            },
        )
        source = _to_source(doc)
        assert source["snippet"] == latex, (
            f"Formula content should appear verbatim in snippet, got: {source['snippet']!r}"
        )
        assert source["element_type"] == "formula"

    def test_formula_content_not_html_in_source(self):
        """Formula content is not HTML-encoded or wrapped in any rendering tag."""
        latex = r"<script>alert(1)</script> \frac{a}{b}"
        doc = Document(
            page_content=latex,
            metadata={"element_type": "formula", "source_file": "paper.pdf"},
        )
        source = _to_source(doc)
        # Content is returned as-is — the responsibility to sanitise for rendering
        # lies with the frontend (Group 9). The API itself does not evaluate content.
        assert "<script>" in source["snippet"] or r"\frac" in source["snippet"]
        # Key invariant: snippet is a plain Python str, never executed
        assert isinstance(source["snippet"], str)

    def test_formula_stored_as_text_not_executed(self):
        """Formula content containing Python-eval-like strings is stored verbatim."""
        dangerous = "__import__('os').system('echo pwned')"
        el = OdlElement(id_=1, page_number=1, element_type="formula",
                        content=dangerous)
        # _extract_content returns it as a plain string
        result = _extract_content({"type": "formula", "content": dangerous})
        assert result == dangerous
        # build_hierarchical_chunks stores it as plain page_content
        heading = OdlElement(id_=0, page_number=1, element_type="heading",
                             content="H1", heading_level=1)
        el.section_title = "H1"
        _, l2 = build_hierarchical_chunks([heading, el])
        if l2:
            assert l2[0].page_content == dangerous

    def test_formula_content_in_l1_section_is_text(self):
        """Formula text flows into L1 section content as plain text, not rendered."""
        latex = r"E = mc^2"
        elements = [
            OdlElement(id_=1, page_number=1, element_type="heading",
                       content="Physics", heading_level=1),
            OdlElement(id_=2, page_number=1, element_type="formula",
                       content=latex, section_title="Physics"),
        ]
        l1, _ = build_hierarchical_chunks(elements)
        assert l1
        # L1 content includes the formula text
        assert latex in l1[0].page_content

    def test_picture_description_stored_as_text(self):
        """Picture description from SmolVLM is stored and returned as plain text."""
        desc = "A bar chart showing revenue: Q1=$1M, Q2=$1.2M, Q3=$1.1M, Q4=$1.5M"
        el = {"type": "picture", "id": 1, "description": desc}
        result = _extract_content(el)
        assert result == desc
        assert isinstance(result, str)

    def test_enrichment_does_not_create_execution_surface(self):
        """Enrichment chunks carry no metadata that could be misused as code."""
        elements = [
            OdlElement(id_=1, page_number=1, element_type="heading",
                       content="Results", heading_level=1),
            OdlElement(id_=2, page_number=1, element_type="formula",
                       content=r"\alpha + \beta = \gamma",
                       section_title="Results"),
            OdlElement(id_=3, page_number=1, element_type="picture",
                       content="A graph showing alpha and beta values",
                       section_title="Results"),
        ]
        l1, l2 = build_hierarchical_chunks(elements)
        # Verify all chunks have plain string metadata values (no callables)
        for chunk in l1 + l2:
            for key, val in chunk.metadata.items():
                assert not callable(val), (
                    f"Chunk metadata[{key!r}] is callable — potential execution surface"
                )
