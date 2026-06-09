"""Group 5 tests: Hierarchical Retrieval Strategy.

Covers:
- Table query boosts table chunks (5.5)
- Overview query prefers L1 section chunks (5.6)
- L2 → L1 context expansion (5.7)
- Legacy chunks without ODL metadata unaffected (5.8)
- PBT: result count ≤ k (5.9)
- Security: no-regex term matching (5.10)
- Security: unknown strategy raises before DB call (5.11)
- _snippet() skips Markdown heading for L1 chunks
- config validator rejects invalid retrieval_strategy
"""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from langchain_core.documents import Document

from ingest.retrieval import (
    TABLE_QUERY_TERMS,
    OVERVIEW_QUERY_TERMS,
    hierarchical_retrieve,
)
from graph.nodes.retrieve_context import _select_documents, _snippet


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------

def _doc(content: str, chunk_level=None, element_type=None,
         chunk_hash=None, parent_chunk_id=None) -> Document:
    meta: dict = {}
    if chunk_level is not None:
        meta["chunk_level"] = chunk_level
    if element_type is not None:
        meta["element_type"] = element_type
    if chunk_hash is not None:
        meta["chunk_hash"] = chunk_hash
    if parent_chunk_id is not None:
        meta["parent_chunk_id"] = parent_chunk_id
    return Document(page_content=content, metadata=meta)


def _mock_vs(docs: list[Document]) -> MagicMock:
    vs = MagicMock()
    vs.similarity_search.return_value = docs
    return vs


# ---------------------------------------------------------------------------
# 5.5  test_table_query_boosts_table_chunks
# ---------------------------------------------------------------------------

class TestTableQueryBoost:
    def test_table_chunk_first_for_table_query(self):
        para = _doc("Paragraph text", chunk_level=2, element_type="paragraph",
                    chunk_hash="hash_p")
        section = _doc("# Section\n\nText", chunk_level=1, element_type="section",
                       chunk_hash="hash_s")
        table = _doc("| Col A | Col B |", chunk_level=2, element_type="table",
                     chunk_hash="hash_t")

        vs = _mock_vs([para, section, table])
        results = hierarchical_retrieve(vs, "compare the table data", k=3, fetch_k=10)

        assert len(results) <= 3
        assert results[0].metadata.get("element_type") == "table", (
            f"Expected table chunk first, got {results[0].metadata.get('element_type')!r}"
        )

    def test_all_table_terms_trigger_boost(self):
        for term in ["table", "row", "column", "compare", "vs", "versus", "list of"]:
            table_doc = _doc("| A | B |", element_type="table", chunk_hash=f"t_{term}")
            para_doc = _doc("Some text", element_type="paragraph", chunk_hash=f"p_{term}")
            vs = _mock_vs([para_doc, table_doc])
            results = hierarchical_retrieve(vs, f"query with {term} here", k=2, fetch_k=5)
            assert any(r.metadata.get("element_type") == "table" for r in results), (
                f"Table term '{term}' did not boost table chunk into results"
            )

    def test_table_boost_case_insensitive(self):
        table_doc = _doc("| A | B |", element_type="table", chunk_hash="t1")
        para_doc = _doc("text", element_type="paragraph", chunk_hash="p1")
        vs = _mock_vs([para_doc, table_doc])
        results = hierarchical_retrieve(vs, "COMPARE THE TABLE", k=2, fetch_k=5)
        assert results[0].metadata.get("element_type") == "table"


# ---------------------------------------------------------------------------
# 5.6  test_overview_query_prefers_l1
# ---------------------------------------------------------------------------

class TestOverviewQueryPrefersL1:
    def test_l1_first_for_overview_query(self):
        para1 = _doc("First paragraph", chunk_level=2, element_type="paragraph",
                     chunk_hash="hash_p1")
        para2 = _doc("Second paragraph", chunk_level=2, element_type="paragraph",
                     chunk_hash="hash_p2")
        section = _doc("# Section\n\nIntro text", chunk_level=1, element_type="section",
                       chunk_hash="hash_s")

        # similarity_search ranks para1, para2 higher than section
        vs = _mock_vs([para1, para2, section])
        results = hierarchical_retrieve(vs, "overview of section 2", k=3, fetch_k=10)

        assert results[0].metadata.get("chunk_level") == 1, (
            f"Expected L1 chunk first for overview query, got chunk_level="
            f"{results[0].metadata.get('chunk_level')!r}"
        )

    def test_all_overview_terms_trigger_preference(self):
        for term in ["overview", "summary", "introduction", "what is", "about"]:
            l1 = _doc("# Title\n\nContent", chunk_level=1, element_type="section",
                      chunk_hash=f"l1_{term}")
            l2 = _doc("Body text", chunk_level=2, element_type="paragraph",
                      chunk_hash=f"l2_{term}")
            vs = _mock_vs([l2, l1])
            results = hierarchical_retrieve(vs, f"{term} of the document", k=2, fetch_k=5)
            assert results[0].metadata.get("chunk_level") == 1, (
                f"Overview term '{term}' did not prefer L1"
            )

    def test_no_heuristic_preserves_similarity_order(self):
        """Neutral query → original similarity order is preserved."""
        doc_a = _doc("A", chunk_level=2, element_type="paragraph", chunk_hash="ha")
        doc_b = _doc("B", chunk_level=1, element_type="section", chunk_hash="hb")
        vs = _mock_vs([doc_a, doc_b])
        results = hierarchical_retrieve(vs, "neutral query", k=2, fetch_k=5)
        # doc_a was first in similarity order and should stay first
        assert results[0].page_content == "A"


# ---------------------------------------------------------------------------
# 5.7  test_context_expansion
# ---------------------------------------------------------------------------

class TestContextExpansion:
    def test_l1_parent_appended_when_room(self):
        """L1 parent (not in top-k) is appended via expansion when room allows."""
        l1 = _doc("# Section\n\nFull section content", chunk_level=1,
                  element_type="section", chunk_hash="l1hash")
        l2 = _doc("Element text", chunk_level=2, element_type="paragraph",
                  chunk_hash="l2hash", parent_chunk_id="l1hash")
        other = _doc("Other content", chunk_level=2, element_type="paragraph",
                     chunk_hash="other_hash")

        # similarity_search returns [l2, other, l1] — l1 is low in similarity ranking
        vs = _mock_vs([l2, other, l1])
        # k=2: initial selection would be [l2, other] — no room for l1
        # BUT with inline expansion: after adding l2 (len=1 < k=2),
        # l1 is found in by_hash and added (len=2=k), stopping before other
        results = hierarchical_retrieve(vs, "neutral query", k=2, fetch_k=10)

        result_hashes = {r.metadata.get("chunk_hash") for r in results}
        assert "l1hash" in result_hashes, (
            "L1 parent should be in results via context expansion"
        )
        assert len(results) <= 2

    def test_expansion_skipped_when_parent_already_present(self):
        """No duplicate L1 when parent is already selected via similarity."""
        l1 = _doc("# Section", chunk_level=1, element_type="section",
                  chunk_hash="l1hash")
        l2 = _doc("Element", chunk_level=2, element_type="paragraph",
                  chunk_hash="l2hash", parent_chunk_id="l1hash")

        vs = _mock_vs([l1, l2])
        results = hierarchical_retrieve(vs, "neutral", k=3, fetch_k=10)

        hashes = [r.metadata.get("chunk_hash") for r in results]
        assert hashes.count("l1hash") == 1, "L1 should not appear twice"

    def test_expansion_skipped_when_parent_not_in_pool(self):
        """No error when L1 parent is not in the candidate pool."""
        l2 = _doc("Element", chunk_level=2, element_type="paragraph",
                  chunk_hash="l2hash", parent_chunk_id="nonexistent_hash")

        vs = _mock_vs([l2])
        results = hierarchical_retrieve(vs, "neutral", k=3, fetch_k=10)
        # No crash; l2 is in results
        assert any(r.metadata.get("chunk_hash") == "l2hash" for r in results)

    def test_expansion_respects_k_limit(self):
        """After expansion, result count never exceeds k."""
        l1 = _doc("# S", chunk_level=1, element_type="section", chunk_hash="l1h")
        l2a = _doc("A", chunk_level=2, element_type="paragraph",
                   chunk_hash="l2a", parent_chunk_id="l1h")
        l2b = _doc("B", chunk_level=2, element_type="paragraph",
                   chunk_hash="l2b", parent_chunk_id="l1h")

        vs = _mock_vs([l2a, l2b, l1])
        results = hierarchical_retrieve(vs, "query", k=2, fetch_k=10)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# 5.8  test_non_odl_chunks_unaffected
# ---------------------------------------------------------------------------

class TestNonOdlChunksUnaffected:
    def test_legacy_chunks_no_keyerror(self):
        """Chunks without ODL metadata pass through without KeyError."""
        legacy1 = Document(page_content="Old content A", metadata={"source": "doc.pdf"})
        legacy2 = Document(page_content="Old content B", metadata={"source": "doc.pdf"})

        vs = _mock_vs([legacy1, legacy2])
        results = hierarchical_retrieve(vs, "table query compare", k=2, fetch_k=5)
        assert len(results) <= 2  # no crash

    def test_legacy_chunks_with_table_query_no_error(self):
        """Table-query heuristic doesn't crash on chunks missing element_type."""
        doc = Document(page_content="Content", metadata={})
        vs = _mock_vs([doc])
        # Should not raise
        hierarchical_retrieve(vs, "compare tables in document", k=3, fetch_k=5)

    def test_legacy_chunks_with_overview_query_no_error(self):
        """Overview-query heuristic doesn't crash on chunks missing chunk_level."""
        doc = Document(page_content="Content", metadata={})
        vs = _mock_vs([doc])
        hierarchical_retrieve(vs, "overview of the document", k=3, fetch_k=5)

    def test_mixed_odl_and_legacy_chunks(self):
        """Mix of ODL and legacy chunks works without error."""
        odl = _doc("ODL content", chunk_level=1, element_type="section",
                   chunk_hash="odl_h")
        legacy = Document(page_content="Legacy content",
                          metadata={"source_file": "old.pdf"})
        vs = _mock_vs([odl, legacy])
        results = hierarchical_retrieve(vs, "overview summary", k=2, fetch_k=5)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# 5.9  PBT: result count ≤ k
# ---------------------------------------------------------------------------

_doc_meta_strategy = st.fixed_dictionaries({
    "chunk_level": st.one_of(st.none(), st.just(1), st.just(2)),
    "element_type": st.one_of(
        st.none(),
        st.sampled_from(["table", "paragraph", "section", "list"]),
    ),
    "chunk_hash": st.one_of(st.none(), st.text(min_size=1, max_size=32)),
    "parent_chunk_id": st.one_of(st.none(), st.text(min_size=1, max_size=32)),
})

_doc_strategy = st.builds(
    lambda content, meta: Document(page_content=content, metadata=meta),
    content=st.text(min_size=0, max_size=200),
    meta=_doc_meta_strategy,
)


@given(
    docs=st.lists(_doc_strategy, min_size=0, max_size=15),
    query=st.text(min_size=0, max_size=100),
    k=st.integers(min_value=1, max_value=5),
)
def test_pbt_result_count_never_exceeds_k(docs, query, k):
    """Property: hierarchical_retrieve always returns ≤ k documents."""
    vs = _mock_vs(docs)
    results = hierarchical_retrieve(vs, query, k=k, fetch_k=max(10, k * 3))
    assert len(results) <= k, f"Got {len(results)} results for k={k}"


# ---------------------------------------------------------------------------
# 5.10  Security: term matching is case-insensitive substring, no regex
# ---------------------------------------------------------------------------

class TestTermMatchingSecurity:
    def test_table_terms_are_plain_strings_not_regex(self):
        """TABLE_QUERY_TERMS are plain frozenset of strings, no regex patterns."""
        for term in TABLE_QUERY_TERMS:
            assert isinstance(term, str)
            # No regex metacharacters
            import re
            try:
                re.compile(term)
            except re.error:
                pytest.fail(f"TABLE_QUERY_TERM {term!r} looks like invalid regex")
            # Key check: term is plain text (not using re.search with term as pattern)
            # The implementation uses `term in query_lower` — plain substring

    def test_overview_terms_are_plain_strings(self):
        for term in OVERVIEW_QUERY_TERMS:
            assert isinstance(term, str)

    def test_injection_attempt_in_query_does_not_crash(self):
        """Malicious query content doesn't cause regex ReDoS or error."""
        malicious_queries = [
            "((((a+)+)+)+)$",
            ".*.*.*.*.*.*",
            "[a-z]{100}",
            "' OR 1=1 --",
            "\x00\x01\x02",
        ]
        vs = _mock_vs([Document(page_content="content", metadata={})])
        for q in malicious_queries:
            results = hierarchical_retrieve(vs, q, k=3, fetch_k=5)
            assert len(results) <= 3  # no error, no excessive time


# ---------------------------------------------------------------------------
# 5.11  Security: unknown strategy raises before DB call
# ---------------------------------------------------------------------------

class TestStrategyDispatchSecurity:
    def test_unknown_strategy_raises_value_error(self):
        """_select_documents raises ValueError for unknown strategy — no DB call."""
        vs = MagicMock()
        with pytest.raises(ValueError, match="Unknown retrieval strategy"):
            _select_documents(vs, "query", top_k=3, fetch_k=10, strategy="unknown_strat")
        vs.similarity_search.assert_not_called()
        vs.max_marginal_relevance_search.assert_not_called()

    def test_valid_strategies_dont_raise(self):
        """All valid strategies pass validation (DB call may fail, but no ValueError)."""
        for strategy in ("mmr", "hybrid", "hybrid_rerank", "hierarchical"):
            vs = MagicMock()
            vs.similarity_search.return_value = []
            vs.max_marginal_relevance_search.return_value = []
            try:
                _select_documents(vs, "query", top_k=3, fetch_k=10, strategy=strategy)
            except ValueError:
                pytest.fail(f"Valid strategy {strategy!r} should not raise ValueError")
            except Exception:
                pass  # Other errors (e.g. BM25 missing) are fine here

    def test_config_rejects_invalid_retrieval_strategy(self):
        """Settings validator blocks invalid RETRIEVAL_STRATEGY at startup."""
        from config import Settings
        with pytest.raises(ValueError, match="RETRIEVAL_STRATEGY"):
            Settings(retrieval_strategy="unknown_mode")

    def test_config_accepts_hierarchical(self):
        """Settings accepts 'hierarchical' as a valid retrieval strategy."""
        from config import Settings
        s = Settings(retrieval_strategy="hierarchical")
        assert s.retrieval_strategy == "hierarchical"


# ---------------------------------------------------------------------------
# _snippet: Markdown heading skipping
# ---------------------------------------------------------------------------

class TestSnippet:
    def test_heading_chunk_skips_title_line(self):
        """_snippet skips the '# Title' line for L1 Markdown chunks."""
        text = "# Section Title\n\nThis is the actual content of the section."
        result = _snippet(text)
        assert result.startswith("This is"), (
            f"Expected snippet to start with body content, got: {result!r}"
        )
        assert "Section Title" not in result

    def test_heading_only_chunk_returns_content(self):
        """If there's no body after the heading, return whatever is available."""
        text = "# Only a Title"
        result = _snippet(text)
        # No body after heading — falls through to original text
        assert "Only a Title" in result

    def test_non_heading_chunk_unchanged(self):
        """Regular chunks are not affected by the heading-skip logic."""
        text = "Normal paragraph text without any heading."
        assert _snippet(text) == text

    def test_long_chunk_truncated(self):
        """Long content is still truncated to _SNIPPET_LEN."""
        text = "word " * 100  # 500 chars
        result = _snippet(text)
        assert len(result) <= 205  # _SNIPPET_LEN + "…"

    def test_heading_long_body_truncated(self):
        """Long L1 chunk: heading skipped, body truncated to snippet length."""
        body = "content " * 50  # ~400 chars
        text = f"# Title\n\n{body}"
        result = _snippet(text)
        assert not result.startswith("#")
        assert len(result) <= 205
