"""Group 4 tests: Hierarchical Chunk Indexing (L1/L2).

Covers:
- L1/L2 structure and referential integrity (4.4)
- Oversized L1 split (4.5)
- Non-PDF path unchanged (4.6)
- PBT: parent_chunk_id always resolvable (4.7)
- Security: parent_chunk_id is an MD5 hex, not raw user value (4.8)
- Security: _check_duplicate_content path unchanged (4.9)
"""

import re
import tempfile
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st
from langchain_core.documents import Document

from ingest.pdf_opendataloader import (
    OdlElement,
    build_hierarchical_chunks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _el(id_, etype, content, page=1, section_title=None, heading_level=None):
    return OdlElement(
        id_=id_,
        page_number=page,
        element_type=etype,
        content=content,
        section_title=section_title,
        heading_level=heading_level,
    )


def _heading(id_, text, level=1, page=1):
    return _el(id_, "heading", text, page=page, heading_level=level)


def _para(id_, text, section=None, page=1):
    return _el(id_, "paragraph", text, page=page, section_title=section)


def _l1_hashes(l1_chunks: list[Document]) -> set[str]:
    """Extract pre-computed chunk_hash values from L1 Document metadata."""
    return {c.metadata["chunk_hash"] for c in l1_chunks}


# ---------------------------------------------------------------------------
# 4.4  test_l1_l2_structure
# ---------------------------------------------------------------------------


class TestL1L2Structure:
    def _make_two_section_elements(self):
        """2 sections × (1 heading + 3 paragraphs each)."""
        elements = [
            _heading(1, "Section One", level=1),
            _para(2, "Para A of section one", section="Section One"),
            _para(3, "Para B of section one", section="Section One"),
            _para(4, "Para C of section one", section="Section One"),
            _heading(5, "Section Two", level=1),
            _para(6, "Para A of section two", section="Section Two"),
            _para(7, "Para B of section two", section="Section Two"),
            _para(8, "Para C of section two", section="Section Two"),
        ]
        return elements

    def test_returns_two_l1_chunks(self):
        elements = self._make_two_section_elements()
        l1, l2 = build_hierarchical_chunks(elements)
        assert len(l1) == 2, f"Expected 2 L1 chunks, got {len(l1)}"

    def test_returns_six_l2_chunks(self):
        elements = self._make_two_section_elements()
        l1, l2 = build_hierarchical_chunks(elements)
        assert len(l2) == 6, f"Expected 6 L2 chunks, got {len(l2)}"

    def test_all_l2_parent_chunk_ids_match_l1_hashes(self):
        """All L2 parent_chunk_id values are present in the L1 chunk_hash set."""
        elements = self._make_two_section_elements()
        l1, l2 = build_hierarchical_chunks(elements)
        hashes = _l1_hashes(l1)
        for doc in l2:
            pid = doc.metadata.get("parent_chunk_id")
            assert pid is not None, "L2 chunk has no parent_chunk_id"
            assert pid in hashes, f"L2 parent_chunk_id={pid!r} not found in L1 hashes {hashes}"

    def test_l1_metadata_fields(self):
        l1, _ = build_hierarchical_chunks(self._make_two_section_elements())
        for doc in l1:
            assert doc.metadata["chunk_level"] == 1
            assert doc.metadata["element_type"] == "section"
            assert doc.metadata.get("section_title") is not None
            assert doc.metadata.get("parent_chunk_id") is None

    def test_l2_metadata_fields(self):
        _, l2 = build_hierarchical_chunks(self._make_two_section_elements())
        for doc in l2:
            assert doc.metadata["chunk_level"] == 2
            assert doc.metadata["element_type"] == "paragraph"
            assert doc.metadata.get("parent_chunk_id") is not None

    def test_l1_content_contains_heading(self):
        l1, _ = build_hierarchical_chunks(self._make_two_section_elements())
        assert any("Section One" in d.page_content for d in l1)
        assert any("Section Two" in d.page_content for d in l1)

    def test_l1_content_contains_body_text(self):
        l1, _ = build_hierarchical_chunks(self._make_two_section_elements())
        combined = " ".join(d.page_content for d in l1)
        assert "Para A of section one" in combined

    def test_empty_elements_returns_empty(self):
        l1, l2 = build_hierarchical_chunks([])
        assert l1 == []
        assert l2 == []

    def test_elements_with_no_headings_prologue_l1(self):
        """Elements before the first heading form a prologue L1."""
        elements = [
            _para(1, "Orphan paragraph one"),
            _para(2, "Orphan paragraph two"),
        ]
        l1, l2 = build_hierarchical_chunks(elements)
        assert len(l1) == 1
        assert len(l2) == 2
        assert l1[0].metadata["section_title"] is None

    def test_heading_only_section_produces_no_l2(self):
        """A section with only a heading and no body has no L2 chunks."""
        elements = [
            _heading(1, "Title Only"),
            _heading(2, "Second Title"),
            _para(3, "Body under second"),
        ]
        l1, l2 = build_hierarchical_chunks(elements)
        assert len(l1) == 2  # 2 sections
        assert len(l2) == 1  # only 1 body paragraph


# ---------------------------------------------------------------------------
# 4.5  test_oversized_l1_split
# ---------------------------------------------------------------------------


class TestOversizedL1Split:
    def test_oversized_section_is_split(self):
        """L1 content > chunk_size gets split; each part has chunk_level=1."""
        long_text = "word " * 200  # ~1000 chars
        elements = [
            _heading(1, "Big Section"),
            _para(2, long_text),
        ]
        l1, _ = build_hierarchical_chunks(elements, chunk_size=300)
        assert len(l1) > 1, "Oversized section should be split into multiple L1 chunks"
        for doc in l1:
            assert doc.metadata["chunk_level"] == 1
            assert doc.metadata["section_title"] == "Big Section"

    def test_split_l1_l2_parent_links_valid(self):
        """L2 chunks from an oversized section still have a valid parent_chunk_id."""
        long_text = "x " * 200
        elements = [
            _heading(1, "Big Section"),
            _para(2, long_text, section="Big Section"),
            _para(3, "Short paragraph", section="Big Section"),
        ]
        l1, l2 = build_hierarchical_chunks(elements, chunk_size=200)
        hashes = _l1_hashes(l1)
        for doc in l2:
            pid = doc.metadata.get("parent_chunk_id")
            assert pid in hashes, f"parent_chunk_id={pid!r} not in L1 hashes"

    def test_chunk_size_respected(self):
        """After split, no L1 chunk has page_content longer than chunk_size + overlap."""
        long_text = "word " * 300
        elements = [
            _heading(1, "Section"),
            _para(2, long_text),
        ]
        l1, _ = build_hierarchical_chunks(elements, chunk_size=400, chunk_overlap=50)
        for doc in l1:
            assert len(doc.page_content) <= 450, f"L1 chunk too long: {len(doc.page_content)} chars"


# ---------------------------------------------------------------------------
# 4.6  test_non_pdf_unchanged (no chunk_level in output)
# ---------------------------------------------------------------------------


class TestNonPdfUnchanged:
    def test_docx_ingest_no_chunk_level(self, ingest_env):
        """DOCX path through _build_chunks produces no chunk_level in metadata."""
        from ingest.policies import _build_chunks

        fake_redis, _ = ingest_env
        docx_content = "Document content\n\nSecond paragraph"

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name

        try:
            with patch("ingest.policies.load_documents") as mock_load:
                mock_load.return_value = [Document(page_content=docx_content, metadata={"page": 0})]
                chunks, hashes, diag = _build_chunks(
                    path, "test-doc", "test.docx", "abc123", "2024-01-01T00:00:00Z", ".docx"
                )
        finally:
            import os

            os.unlink(path)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert "chunk_level" not in chunk.metadata, "Non-ODL chunk should not have chunk_level field"

    def test_txt_ingest_no_odl_metadata(self, ingest_env):
        """TXT path produces no ODL metadata fields."""
        import os

        from ingest.policies import _build_chunks

        content = "Plain text content for testing"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            chunks, _, _ = _build_chunks(path, "test-txt", "test.txt", "hash123", "2024-01-01T00:00:00Z", ".txt")
        finally:
            os.unlink(path)

        for chunk in chunks:
            assert "chunk_level" not in chunk.metadata
            assert "parent_chunk_id" not in chunk.metadata


# ---------------------------------------------------------------------------
# 4.7  PBT: parent_chunk_id always resolvable
# ---------------------------------------------------------------------------

_section_strategy = st.builds(
    lambda heading_text, n_paras: (
        [OdlElement(id_=0, page_number=1, element_type="heading", content=heading_text, heading_level=1)]
        + [
            OdlElement(
                id_=i + 1,
                page_number=1,
                element_type="paragraph",
                content=f"Para {i} in {heading_text}",
                section_title=heading_text,
            )
            for i in range(n_paras)
        ]
    ),
    heading_text=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" "),
    ),
    n_paras=st.integers(min_value=1, max_value=5),
)


@given(sections=st.lists(_section_strategy, min_size=1, max_size=6))
def test_pbt_l2_parent_chunk_id_always_resolvable(sections):
    """Property: every L2 chunk's parent_chunk_id is in the L1 chunk hash set."""
    elements: list[OdlElement] = []
    for sec in sections:
        elements.extend(sec)

    l1, l2 = build_hierarchical_chunks(elements)

    if not l2:
        return  # nothing to check

    l1_hashes = _l1_hashes(l1)
    for doc in l2:
        pid = doc.metadata.get("parent_chunk_id")
        assert pid is not None, "L2 chunk missing parent_chunk_id"
        assert pid in l1_hashes, f"L2 parent_chunk_id={pid!r} not resolvable in L1 hashes={l1_hashes}"


# ---------------------------------------------------------------------------
# 4.8  Security: parent_chunk_id is a valid MD5 hex, not raw user content
# ---------------------------------------------------------------------------

_MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class TestSecurity:
    def test_parent_chunk_id_is_md5_hex(self):
        """FR 4.8: parent_chunk_id is a 32-char hex MD5, never a raw user string."""
        elements = [
            _heading(1, "Section"),
            _para(2, "Body text", section="Section"),
        ]
        _, l2 = build_hierarchical_chunks(elements)
        for doc in l2:
            pid = doc.metadata["parent_chunk_id"]
            assert _MD5_PATTERN.match(pid), f"parent_chunk_id {pid!r} is not a valid MD5 hex string"

    def test_l1_chunk_hash_is_md5_hex(self):
        """L1 pre-computed chunk_hash is a valid MD5 hex string."""
        elements = [
            _heading(1, "Section"),
            _para(2, "Body text"),
        ]
        l1, _ = build_hierarchical_chunks(elements)
        for doc in l1:
            h = doc.metadata.get("chunk_hash", "")
            assert _MD5_PATTERN.match(h), f"L1 chunk_hash {h!r} is not valid MD5"

    def test_user_content_not_in_parent_chunk_id(self):
        """Malicious heading content does not appear in parent_chunk_id."""
        malicious = "'; DROP TABLE chunks; --"
        elements = [
            _heading(1, malicious),
            _para(2, "Body", section=malicious),
        ]
        _, l2 = build_hierarchical_chunks(elements)
        for doc in l2:
            pid = doc.metadata["parent_chunk_id"]
            assert malicious not in pid

    def test_check_duplicate_content_path_unchanged(self, ingest_env):
        """FR 4.9: _check_duplicate_content uses file hash key, unaffected by L1/L2."""
        from ingest.policies import _check_duplicate_content

        fake_redis, _ = ingest_env
        # Simulate a pre-existing entry
        from ingest.keys import CONTENT_HASHES_KEY

        fake_redis.hset(CONTENT_HASHES_KEY, "existinghash", "existing-doc-id")

        result = _check_duplicate_content(fake_redis, "existinghash", "new-doc-id")
        assert result is not None
        assert result["status"] == "skipped"

        # Same hash, same doc_id → not a duplicate
        result2 = _check_duplicate_content(fake_redis, "existinghash", "existing-doc-id")
        assert result2 is None


# ---------------------------------------------------------------------------
# Integration: _build_chunks produces correct L1+L2 when ODL elements present
# ---------------------------------------------------------------------------


class TestBuildChunksIntegration:
    def test_odl_path_produces_l1_l2_metadata(self, ingest_env):
        """_build_chunks with mocked ODL returns chunks with chunk_level metadata."""
        import os
        from unittest.mock import patch

        from ingest.pdf_opendataloader import OdlElement
        from ingest.policies import _build_chunks

        elements = [
            OdlElement(id_=1, page_number=1, element_type="heading", content="Test Section", heading_level=1),
            OdlElement(
                id_=2,
                page_number=1,
                element_type="paragraph",
                content="Test paragraph content.",
                section_title="Test Section",
            ),
        ]

        pdf_content = b"%PDF-1.4\n%test"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_content)
            path = f.name

        try:
            with (
                patch("ingest.pdf_preflight.preflight_check", return_value=(True, "")),
                patch(
                    "ingest.policies.load_pdf_odl",
                    return_value=(
                        [
                            Document(
                                page_content="md chunk",
                                metadata={
                                    "page": 0,
                                    "parser": "opendataloader",
                                    "fallback_used": False,
                                    "parser_mode": "local",
                                },
                            )
                        ],
                        elements,
                        {
                            "parser": "opendataloader",
                            "fallback_used": "false",
                            "page_count": "1",
                            "element_count": "2",
                            "parser_mode": "local",
                        },
                    ),
                ),
            ):
                chunks, hashes, diag = _build_chunks(
                    path,
                    "test-pdf",
                    "test.pdf",
                    "abc123",
                    "2024-01-01T00:00:00Z",
                    ".pdf",
                )
        finally:
            os.unlink(path)

        # Should have L1 + L2 chunks
        chunk_levels = [c.metadata.get("chunk_level") for c in chunks]
        assert 1 in chunk_levels, "Expected at least one L1 chunk"
        assert 2 in chunk_levels, "Expected at least one L2 chunk"

        # Verify standard metadata also present
        for c in chunks:
            assert "doc_id" in c.metadata
            assert "chunk_hash" in c.metadata
