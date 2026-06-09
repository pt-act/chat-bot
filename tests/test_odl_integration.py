"""Group 10 integration tests.

10.2  test_full_odl_ingest_pipeline — mocked ODL JSON → _build_chunks → L1+L2 in Chroma
10.3  test_hierarchical_retrieval_e2e — table query returns table chunk in top-k
10.4  test_multipage_table_merged — two-page table chain merges to one element
10.7  All existing non-PDF ingest tests pass (covered by regression suite; spot-checked here)
10.8  test_legacy_chunks_no_regression — mixed ODL + legacy chunks all return valid Source
"""

import json as _json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from graph.nodes.retrieve_context import _to_source
from ingest.pdf_opendataloader import (
    build_hierarchical_chunks,
    merge_tables,
    walk_tree,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture_json(name: str) -> dict:
    return _json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _load_fixture_md(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Mock ODL helper
# ---------------------------------------------------------------------------


def _make_odl_mock(json_data: dict, md_content: str) -> MagicMock:
    """Mock opendataloader_pdf.convert() that writes fixture files to output_dir."""

    def _fake_convert(input_path: str, output_dir: str, **_kwargs: object) -> None:
        stem = Path(input_path).stem
        out = Path(output_dir)
        (out / f"{stem}.md").write_text(md_content, encoding="utf-8")
        (out / f"{stem}.json").write_text(_json.dumps(json_data), encoding="utf-8")

    mock = MagicMock()
    mock.convert.side_effect = _fake_convert
    return mock


# ---------------------------------------------------------------------------
# 10.2  test_full_odl_ingest_pipeline
# ---------------------------------------------------------------------------


class TestFullOdlIngestPipeline:
    def test_builds_l1_and_l2_chunks(self, ingest_env, simple_pdf_bytes):
        """Mocked ODL JSON → _build_chunks → both L1 (section) and L2 (element) chunks."""
        _fake_redis, _vs = ingest_env
        mock_json = _load_fixture_json("simple_mock.json")
        mock_md = _load_fixture_md("simple_mock.md")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(simple_pdf_bytes)
            path = f.name

        mock_odl = _make_odl_mock(mock_json, mock_md)
        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from ingest.policies import _build_chunks

                chunks, _hashes, diag = _build_chunks(
                    path,
                    "simple-doc",
                    "simple.pdf",
                    "abc123",
                    "2024-01-01T00:00:00Z",
                    ".pdf",
                )
        finally:
            os.unlink(path)

        l1 = [c for c in chunks if c.metadata.get("chunk_level") == 1]
        l2 = [c for c in chunks if c.metadata.get("chunk_level") == 2]

        assert l1, "No L1 (section) chunks produced"
        assert l2, "No L2 (element) chunks produced"
        assert diag["parser"] == "opendataloader"

    def test_l1_chunks_have_section_metadata(self, ingest_env, simple_pdf_bytes):
        """Every L1 chunk carries element_type='section' and a section_title."""
        _fake_redis, _vs = ingest_env
        mock_odl = _make_odl_mock(
            _load_fixture_json("simple_mock.json"),
            _load_fixture_md("simple_mock.md"),
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(simple_pdf_bytes)
            path = f.name

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from ingest.policies import _build_chunks

                chunks, _, _ = _build_chunks(
                    path,
                    "doc",
                    "simple.pdf",
                    "h",
                    "v",
                    ".pdf",
                )
        finally:
            os.unlink(path)

        l1 = [c for c in chunks if c.metadata.get("chunk_level") == 1]
        for chunk in l1:
            assert chunk.metadata.get("element_type") == "section"
            assert chunk.metadata.get("section_title") is not None

    def test_l2_chunks_have_parent_links(self, ingest_env, simple_pdf_bytes):
        """Every L2 chunk's parent_chunk_id exists in the L1 chunk set."""
        _fake_redis, _vs = ingest_env
        mock_odl = _make_odl_mock(
            _load_fixture_json("simple_mock.json"),
            _load_fixture_md("simple_mock.md"),
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(simple_pdf_bytes)
            path = f.name

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from ingest.policies import _build_chunks

                chunks, _, _ = _build_chunks(
                    path,
                    "doc",
                    "simple.pdf",
                    "h",
                    "v",
                    ".pdf",
                )
        finally:
            os.unlink(path)

        l1_hashes = {c.metadata["chunk_hash"] for c in chunks if c.metadata.get("chunk_level") == 1}
        l2 = [c for c in chunks if c.metadata.get("chunk_level") == 2]
        for chunk in l2:
            pid = chunk.metadata.get("parent_chunk_id")
            assert pid in l1_hashes, f"L2 chunk parent_chunk_id={pid!r} not in L1 hashes"

    def test_table_l2_chunk_present(self, ingest_env, simple_pdf_bytes):
        """Fixture has a table element — an L2 chunk with element_type='table' must appear."""
        _fake_redis, _vs = ingest_env
        mock_odl = _make_odl_mock(
            _load_fixture_json("simple_mock.json"),
            _load_fixture_md("simple_mock.md"),
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(simple_pdf_bytes)
            path = f.name

        try:
            with (
                patch("ingest.pdf_opendataloader.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch("ingest.pdf_opendataloader._hybrid_reachable", return_value=(False, "")),
                patch.dict(sys.modules, {"opendataloader_pdf": mock_odl}),
            ):
                from ingest.policies import _build_chunks

                chunks, _, _ = _build_chunks(
                    path,
                    "doc",
                    "simple.pdf",
                    "h",
                    "v",
                    ".pdf",
                )
        finally:
            os.unlink(path)

        table_chunks = [c for c in chunks if c.metadata.get("element_type") == "table"]
        assert table_chunks, "No L2 chunk with element_type='table' found in output"
        # Table content should have pricing information
        combined = " ".join(c.page_content for c in table_chunks)
        assert any(kw in combined for kw in ("Starter", "Pro", "Enterprise", "$")), (
            f"Table chunk content does not contain expected pricing data: {combined[:200]!r}"
        )


# ---------------------------------------------------------------------------
# 10.3  test_hierarchical_retrieval_e2e
# ---------------------------------------------------------------------------


class TestHierarchicalRetrievalE2E:
    def test_table_query_returns_table_chunk(self, vectorstore):
        """After ingesting ODL chunks, a 'table' query surfaces the table chunk."""
        from ingest.retrieval import hierarchical_retrieve

        # Build elements directly from fixture JSON (no convert() needed)
        doc_data = _load_fixture_json("simple_mock.json")
        elements = walk_tree(doc_data)
        l1_chunks, l2_chunks = build_hierarchical_chunks(elements)

        # Add chunks to vectorstore with standard metadata
        all_docs = []
        for i, doc in enumerate(l1_chunks + l2_chunks):
            doc.metadata.setdefault("chunk_hash", f"hash_{i}")
            all_docs.append(doc)

        if all_docs:
            vectorstore.add_documents(all_docs)

        results = hierarchical_retrieve(vectorstore, "compare the pricing table rows", k=3, fetch_k=10)

        assert len(results) <= 3
        # The hierarchical heuristic should surface the table chunk
        element_types = [r.metadata.get("element_type") for r in results]
        assert "table" in element_types, f"Expected 'table' element in top-3 for table query, got: {element_types}"

    def test_overview_query_returns_section_chunk(self, vectorstore):
        """An 'overview' query surfaces the L1 section chunk."""
        from ingest.retrieval import hierarchical_retrieve

        doc_data = _load_fixture_json("simple_mock.json")
        elements = walk_tree(doc_data)
        l1_chunks, l2_chunks = build_hierarchical_chunks(elements)

        all_docs = []
        for i, doc in enumerate(l1_chunks + l2_chunks):
            doc.metadata.setdefault("chunk_hash", f"hash2_{i}")
            all_docs.append(doc)

        if all_docs:
            vectorstore.add_documents(all_docs)

        results = hierarchical_retrieve(vectorstore, "overview of technical specifications", k=3, fetch_k=10)

        chunk_levels = [r.metadata.get("chunk_level") for r in results]
        assert 1 in chunk_levels, f"Expected L1 section chunk in results for overview query, got levels: {chunk_levels}"

    def test_retrieval_result_has_section_metadata(self, vectorstore):
        """Retrieved L2 chunks carry section_title for citation rendering."""
        from ingest.retrieval import hierarchical_retrieve

        doc_data = _load_fixture_json("simple_mock.json")
        elements = walk_tree(doc_data)
        l1_chunks, l2_chunks = build_hierarchical_chunks(elements)

        all_docs = []
        for i, doc in enumerate(l1_chunks + l2_chunks):
            doc.metadata.setdefault("chunk_hash", f"hash3_{i}")
            all_docs.append(doc)

        if all_docs:
            vectorstore.add_documents(all_docs)

        results = hierarchical_retrieve(vectorstore, "pricing information", k=5, fetch_k=10)

        l2_results = [r for r in results if r.metadata.get("chunk_level") == 2]
        for chunk in l2_results:
            assert chunk.metadata.get("section_title") is not None, f"L2 chunk missing section_title: {chunk.metadata}"


# ---------------------------------------------------------------------------
# 10.4  test_multipage_table_merged
# ---------------------------------------------------------------------------


class TestMultipageTableMerged:
    def test_two_page_table_chain_produces_one_element(self):
        """Two table fragments linked by next_table_id → one merged element via walk+merge."""
        doc_data = _load_fixture_json("multipage_table_mock.json")
        raw_elements = walk_tree(doc_data)
        merged_elements = merge_tables(raw_elements)

        tables = [e for e in merged_elements if e.element_type == "table"]
        assert len(tables) == 1, f"Expected 1 merged table, got {len(tables)} tables in output"

    def test_merged_table_spans_both_pages(self):
        """Merged table spans from page 3 to page 4."""
        doc_data = _load_fixture_json("multipage_table_mock.json")
        raw_elements = walk_tree(doc_data)
        merged = merge_tables(raw_elements)

        table = next(e for e in merged if e.element_type == "table")
        assert table.page_number == 3, f"Expected table to start on page 3, got {table.page_number}"
        assert table.page_end == 4, f"Expected table to end on page 4, got {table.page_end}"

    def test_merged_table_content_has_all_rows(self):
        """Merged table content contains rows from both pages."""
        doc_data = _load_fixture_json("multipage_table_mock.json")
        elements = merge_tables(walk_tree(doc_data))
        table = next(e for e in elements if e.element_type == "table")

        # page 3 data: North, South; page 4 data: East, West
        assert "North" in table.content or "$1.2M" in table.content
        assert "East" in table.content or "$2.1M" in table.content

    def test_build_hierarchical_chunks_uses_merged_table(self):
        """build_hierarchical_chunks receives merged elements and creates one table L2 chunk."""
        doc_data = _load_fixture_json("multipage_table_mock.json")
        elements = walk_tree(doc_data)
        # merge_tables is called inside load_pdf_odl; here we simulate that directly
        merged = merge_tables(elements)
        l1_chunks, l2_chunks = build_hierarchical_chunks(merged)

        table_l2 = [c for c in l2_chunks if c.metadata.get("element_type") == "table"]
        assert len(table_l2) == 1, f"Expected 1 table L2 chunk (merged), got {len(table_l2)}"
        # The L2 chunk should carry page_end from the merge
        assert table_l2[0].metadata.get("page_end") == 4

    def test_scanned_mock_json_ingests_without_hybrid(self):
        """scanned_mock.json walks and chunks correctly without requiring hybrid server."""
        doc_data = _load_fixture_json("scanned_mock.json")
        elements = walk_tree(doc_data)
        merged = merge_tables(elements)
        l1, l2 = build_hierarchical_chunks(merged)

        assert l1, "No L1 chunks from scanned_mock.json"
        assert l2, "No L2 chunks from scanned_mock.json"
        # The invoice table should produce an L2 table chunk
        table_chunks = [c for c in l2 if c.metadata.get("element_type") == "table"]
        assert table_chunks, "No table L2 chunk from scanned invoice fixture"


# ---------------------------------------------------------------------------
# 10.7  Spot-check: non-PDF ingest paths unchanged
# ---------------------------------------------------------------------------


class TestNonPdfIngestUnchanged:
    def test_txt_ingest_produces_no_odl_metadata(self, ingest_env):
        """TXT files go through the legacy splitter — no chunk_level or element_type."""
        import os
        import tempfile

        from ingest.policies import _build_chunks

        content = "Plain text content for regression testing of non-PDF ingest."
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            chunks, _, diag = _build_chunks(
                path,
                "txt-doc",
                "doc.txt",
                "hash_txt",
                "v",
                ".txt",
            )
        finally:
            os.unlink(path)

        assert len(chunks) >= 1
        assert diag == {}, "Non-PDF should produce no FR8 diagnostics"
        for chunk in chunks:
            assert "chunk_level" not in chunk.metadata
            assert "element_type" not in chunk.metadata

    def test_docx_load_uses_legacy_splitter(self, ingest_env):
        """DOCX files bypass ODL entirely."""
        from langchain_core.documents import Document

        from ingest.policies import _build_chunks

        with patch("ingest.policies.load_documents") as mock_load:
            mock_load.return_value = [
                Document(page_content="DOCX content paragraph one.\n\nParagraph two.", metadata={"page": 0})
            ]
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
                path = f.name
            try:
                chunks, _, diag = _build_chunks(
                    path,
                    "docx-doc",
                    "doc.docx",
                    "hash_docx",
                    "v",
                    ".docx",
                )
            finally:
                os.unlink(path)

        assert len(chunks) >= 1
        assert diag == {}
        for chunk in chunks:
            assert "chunk_level" not in chunk.metadata


# ---------------------------------------------------------------------------
# 10.8  test_legacy_chunks_no_regression
# ---------------------------------------------------------------------------


class TestLegacyChunksNoRegression:
    """Mixed ODL + legacy chunks — _to_source() returns valid Source for all."""

    def _make_odl_chunk(self) -> Document:
        return Document(
            page_content="Starter plan costs $9/mo for up to 5 users.",
            metadata={
                "doc_id": "pricing",
                "source_file": "pricing.pdf",
                "page_number": 1,
                "chunk_hash": "odl_hash_1",
                "chunk_level": 2,
                "section_title": "Pricing Table",
                "element_type": "table",
                "parent_chunk_id": "l1_hash",
                "page_end": 1,
                "bbox": [72.0, 555.0, 540.0, 614.0],
            },
        )

    def _make_legacy_chunk(self) -> Document:
        return Document(
            page_content="Returns are accepted within 30 days of purchase.",
            metadata={
                "doc_id": "policy",
                "source_file": "policy.pdf",
                "page_number": 2,
                "chunk_hash": "legacy_hash_1",
            },
        )

    def _make_synthesized_chunk(self) -> Document:
        return Document(
            page_content="The refund policy covers all eligible products.",
            metadata={
                "source": "synthesized",
                "chunk_hash": "synth_hash_1",
            },
        )

    def test_odl_chunk_to_source(self):
        """ODL chunk: all four new fields populated."""
        source = _to_source(self._make_odl_chunk(), score=0.88)
        assert source["section"] == "Pricing Table"
        assert source["element_type"] == "table"
        assert source["page_end"] == 1
        assert source["bbox"] == [72.0, 555.0, 540.0, 614.0]
        assert source["score"] == 0.8800

    def test_legacy_chunk_to_source_no_keyerror(self):
        """Legacy chunk: no ODL fields — all four new fields are None, no KeyError."""
        source = _to_source(self._make_legacy_chunk(), score=0.72)
        assert source["section"] is None
        assert source["element_type"] is None
        assert source["page_end"] is None
        assert source["bbox"] is None
        assert source["label"] == "policy.pdf"

    def test_synthesized_chunk_to_source_no_keyerror(self):
        """Synthesized chunk (from learning mode): _to_source() works without standard keys."""
        source = _to_source(self._make_synthesized_chunk())
        assert source["label"] == "synthesized"
        assert source["section"] is None

    def test_mixed_batch_all_valid(self):
        """All chunks in a mixed batch produce valid Source dicts."""
        chunks = [
            self._make_odl_chunk(),
            self._make_legacy_chunk(),
            self._make_synthesized_chunk(),
        ]
        sources = [_to_source(c) for c in chunks]
        assert len(sources) == 3
        for src in sources:
            # These keys must always be present
            for key in ("label", "doc_id", "score", "page", "snippet", "section", "element_type", "page_end", "bbox"):
                assert key in src, f"Key {key!r} missing from source dict"

    def test_dedup_works_with_mixed_chunks(self):
        """_dedup() from retrieve_context handles mixed ODL + legacy without crashing."""
        from graph.nodes.retrieve_context import _dedup

        sources = [
            _to_source(self._make_odl_chunk(), score=0.9),
            _to_source(self._make_legacy_chunk(), score=0.7),
            _to_source(self._make_synthesized_chunk()),
            _to_source(self._make_odl_chunk(), score=0.8),  # duplicate
        ]
        deduped = _dedup(sources)
        assert len(deduped) == 3  # one duplicate removed
