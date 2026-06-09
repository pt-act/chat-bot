"""Group 3 tests: JSON Tree Walker, Section Propagation, Table Merger.

Covers:
- walk_tree() heading propagation (3.6)
- _extract_content() table extraction (3.7)
- merge_tables() multi-page merge (3.8)
- PBT: element_type never null (3.9)
- PBT: section propagation invariant (3.10)
- PBT: table merger count formula (3.11)
- Security: malformed/missing kids handled gracefully (3.12)
- Security: _extract_content never evals content (3.13)
"""

from hypothesis import given
from hypothesis import strategies as st

from ingest.pdf_opendataloader import (
    OdlElement,
    _extract_content,
    merge_tables,
    walk_tree,
)

# ---------------------------------------------------------------------------
# Fixture JSON builders
# ---------------------------------------------------------------------------


def _heading(id_: int, text: str, level: int = 1, page: int = 1) -> dict:
    return {
        "type": "heading",
        "id": id_,
        "content": text,
        "heading level": level,
        "page number": page,
        "bounding box": [0.0, 0.0, 100.0, 20.0],
    }


def _paragraph(id_: int, text: str, page: int = 1) -> dict:
    return {
        "type": "paragraph",
        "id": id_,
        "content": text,
        "page number": page,
        "bounding box": [0.0, 25.0, 100.0, 40.0],
    }


def _table(id_: int, rows: list[list[str]], page: int = 1, next_id=None, prev_id=None) -> dict:
    el = {
        "type": "table",
        "id": id_,
        "page number": page,
        "bounding box": [0.0, 50.0, 100.0, 80.0],
        "rows": [
            {
                "cells": [
                    {
                        "kids": [
                            {"type": "paragraph", "content": cell, "id": 9000 + i * 10 + j, "page number": page}
                            for j, cell in enumerate(row_cells)
                        ]
                    }
                    for i, row_cells in enumerate(rows)
                ]
            }
        ],
    }
    if next_id is not None:
        el["next table id"] = next_id
    if prev_id is not None:
        el["previous table id"] = prev_id
    return el


def _doc(*kids) -> dict:
    return {"kids": list(kids), "number of pages": 1}


# ---------------------------------------------------------------------------
# 3.6  test_walker_heading_propagation
# ---------------------------------------------------------------------------


class TestWalkerHeadingPropagation:
    def test_h1_propagated_to_subsequent_paragraphs(self):
        """All paragraphs after H1 carry section_title=H1_text until another heading."""
        doc = _doc(
            _heading(1, "Introduction", level=1),
            _paragraph(2, "First paragraph"),
            _paragraph(3, "Second paragraph"),
            _heading(4, "Methods", level=2),
            _paragraph(5, "Third paragraph"),
        )
        elements = walk_tree(doc)
        assert len(elements) == 5

        h1, p1, p2, h2, p3 = elements

        assert h1.element_type == "heading"
        assert h1.section_title is None  # headings don't carry their own section_title

        assert p1.section_title == "Introduction"
        assert p2.section_title == "Introduction"

        assert h2.element_type == "heading"
        assert p3.section_title == "Methods"

    def test_no_heading_before_paragraph_section_is_none(self):
        doc = _doc(
            _paragraph(1, "Orphan paragraph"),
            _heading(2, "Late heading"),
            _paragraph(3, "After heading"),
        )
        elements = walk_tree(doc)
        orphan, h, after = elements
        assert orphan.section_title is None
        assert after.section_title == "Late heading"

    def test_empty_document_returns_empty_list(self):
        assert walk_tree({"kids": []}) == []

    def test_missing_kids_key_returns_empty_list(self):
        assert walk_tree({}) == []

    def test_header_footer_skipped_by_default(self):
        doc = _doc(
            {"type": "header", "id": 1, "content": "Page Header", "page number": 1},
            _paragraph(2, "Body text"),
            {"type": "footer", "id": 3, "content": "Footer", "page number": 1},
        )
        elements = walk_tree(doc, include_header_footer=False)
        assert len(elements) == 1
        assert elements[0].element_type == "paragraph"

    def test_header_footer_included_when_configured(self):
        doc = _doc(
            {"type": "header", "id": 1, "content": "Page Header", "page number": 1},
            _paragraph(2, "Body text"),
        )
        elements = walk_tree(doc, include_header_footer=True)
        assert len(elements) == 2
        assert elements[0].element_type == "header"


# ---------------------------------------------------------------------------
# 3.7  test_walker_table_extraction
# ---------------------------------------------------------------------------


class TestExtractContent:
    def test_table_two_rows_returns_cell_text(self):
        table = {
            "type": "table",
            "id": 1,
            "page number": 1,
            "rows": [
                {
                    "cells": [
                        {"kids": [{"type": "paragraph", "content": "Name", "id": 10, "page number": 1}]},
                        {"kids": [{"type": "paragraph", "content": "Value", "id": 11, "page number": 1}]},
                    ]
                },
                {
                    "cells": [
                        {"kids": [{"type": "paragraph", "content": "Alice", "id": 12, "page number": 1}]},
                        {"kids": [{"type": "paragraph", "content": "42", "id": 13, "page number": 1}]},
                    ]
                },
            ],
        }
        content = _extract_content(table)
        assert "Name" in content
        assert "Value" in content
        assert "Alice" in content
        assert "42" in content

    def test_paragraph_returns_content(self):
        el = {"type": "paragraph", "content": "Hello world", "id": 1}
        assert _extract_content(el) == "Hello world"

    def test_heading_returns_content(self):
        el = {"type": "heading", "content": "Section Title", "id": 1, "heading level": 1}
        assert _extract_content(el) == "Section Title"

    def test_list_extracts_items(self):
        el = {
            "type": "list",
            "id": 1,
            "list items": [
                {"content": "Item one"},
                {"content": "Item two"},
                {"content": "Item three"},
            ],
        }
        content = _extract_content(el)
        assert "Item one" in content
        assert "Item two" in content

    def test_image_returns_empty(self):
        el = {"type": "image", "id": 1}
        assert _extract_content(el) == ""

    def test_formula_returns_latex(self):
        el = {"type": "formula", "id": 1, "content": r"\frac{a}{b}"}
        assert _extract_content(el) == r"\frac{a}{b}"

    def test_picture_returns_description(self):
        el = {"type": "picture", "id": 1, "description": "A bar chart showing sales"}
        assert _extract_content(el) == "A bar chart showing sales"

    def test_header_excluded_by_default(self):
        el = {"type": "header", "id": 1, "content": "Page 1"}
        assert _extract_content(el, include_header_footer=False) == ""

    def test_header_included_when_flag_set(self):
        el = {"type": "header", "id": 1, "content": "Page 1"}
        assert _extract_content(el, include_header_footer=True) == "Page 1"

    def test_empty_table_returns_empty_string(self):
        el = {"type": "table", "id": 1, "rows": []}
        assert _extract_content(el) == ""

    def test_missing_content_field_returns_empty(self):
        el = {"type": "paragraph", "id": 1}
        assert _extract_content(el) == ""


# ---------------------------------------------------------------------------
# 3.8  test_table_merge
# ---------------------------------------------------------------------------


class TestTableMerge:
    def test_two_linked_tables_merged_to_one(self):
        """Tables on pages 3 and 4 linked by next_table_id merge to one element."""
        t1 = _table(10, [["Row 1 Col 1"]], page=3, next_id=11)
        t2 = _table(11, [["Row 2 Col 1"]], page=4, prev_id=10)
        doc = _doc(_heading(1, "Data", level=1), t1, t2)
        elements = walk_tree(doc)

        merged = merge_tables(elements)
        tables = [e for e in merged if e.element_type == "table"]

        assert len(tables) == 1, f"Expected 1 table, got {len(tables)}"
        assert tables[0].page_end == 4
        assert "Row 1" in tables[0].content
        assert "Row 2" in tables[0].content

    def test_independent_tables_unchanged(self):
        elements = [
            OdlElement(id_=1, page_number=1, element_type="table", content="A"),
            OdlElement(id_=2, page_number=2, element_type="table", content="B"),
        ]
        result = merge_tables(elements)
        assert len(result) == 2

    def test_non_table_elements_pass_through(self):
        elements = [
            OdlElement(id_=1, page_number=1, element_type="heading", content="Title"),
            OdlElement(id_=2, page_number=1, element_type="paragraph", content="Text"),
        ]
        result = merge_tables(elements)
        assert result == elements

    def test_three_fragment_chain_merged_to_one(self):
        elements = [
            OdlElement(id_=1, page_number=1, element_type="table", content="Part 1", next_table_id=2),
            OdlElement(
                id_=2, page_number=2, element_type="table", content="Part 2", previous_table_id=1, next_table_id=3
            ),
            OdlElement(id_=3, page_number=3, element_type="table", content="Part 3", previous_table_id=2),
        ]
        result = merge_tables(elements)
        tables = [e for e in result if e.element_type == "table"]
        assert len(tables) == 1
        assert tables[0].page_end == 3

    def test_empty_list_returns_empty(self):
        assert merge_tables([]) == []

    def test_page_end_is_last_fragment_page(self):
        elements = [
            OdlElement(id_=5, page_number=7, element_type="table", content="A", next_table_id=6),
            OdlElement(id_=6, page_number=9, element_type="table", content="B", previous_table_id=5),
        ]
        result = merge_tables(elements)
        assert result[0].page_end == 9


# ---------------------------------------------------------------------------
# 3.9  PBT: walk_tree never produces element with null element_type
# ---------------------------------------------------------------------------

_ODL_TYPES = ["heading", "paragraph", "table", "list", "image", "caption", "header", "footer", "formula", "picture"]

_flat_element_strategy = st.fixed_dictionaries(
    {
        "type": st.sampled_from(_ODL_TYPES),
        "id": st.integers(min_value=0, max_value=9999),
        "page number": st.integers(min_value=1, max_value=999),
        "content": st.text(max_size=200),
        "bounding box": st.just([0.0, 0.0, 100.0, 20.0]),
        "heading level": st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
    }
)

_flat_doc_strategy = st.builds(
    lambda kids: {"kids": kids},
    kids=st.lists(_flat_element_strategy, min_size=0, max_size=20),
)


@given(doc=_flat_doc_strategy)
def test_pbt_walk_tree_no_null_element_type(doc):
    """Property: every element from walk_tree has a non-null element_type."""
    elements = walk_tree(doc)
    for el in elements:
        assert el.element_type is not None
        assert len(el.element_type) > 0


# ---------------------------------------------------------------------------
# 3.10  PBT: section propagation invariant
# ---------------------------------------------------------------------------

_heading_strategy = st.fixed_dictionaries(
    {
        "type": st.just("heading"),
        "id": st.integers(min_value=0, max_value=9999),
        "page number": st.integers(min_value=1, max_value=999),
        "content": st.text(min_size=1, max_size=100),
        "heading level": st.integers(min_value=1, max_value=6),
    }
)

_non_heading_strategy = st.fixed_dictionaries(
    {
        "type": st.sampled_from(["paragraph", "caption", "image"]),
        "id": st.integers(min_value=0, max_value=9999),
        "page number": st.integers(min_value=1, max_value=999),
        "content": st.text(max_size=200),
    }
)

_mixed_doc_strategy = st.builds(
    lambda kids: {"kids": kids},
    kids=st.lists(
        st.one_of(_heading_strategy, _non_heading_strategy),
        min_size=0,
        max_size=30,
    ),
)


@given(doc=_mixed_doc_strategy)
def test_pbt_section_propagation_invariant(doc):
    """Property: non-heading section_title equals the most-recently-seen heading."""
    elements = walk_tree(doc, include_header_footer=True)
    current_heading_text = None
    for el in elements:
        if el.element_type == "heading":
            current_heading_text = el.content
        else:
            assert el.section_title == current_heading_text, (
                f"element {el.id_!r} has section_title={el.section_title!r}, expected {current_heading_text!r}"
            )


# ---------------------------------------------------------------------------
# 3.11  PBT: merge_tables count formula
# ---------------------------------------------------------------------------


@given(
    m_chains=st.integers(min_value=0, max_value=5),
    chain_len=st.integers(min_value=2, max_value=4),
    n_independent=st.integers(min_value=0, max_value=5),
)
def test_pbt_merge_tables_count_formula(m_chains, chain_len, n_independent):
    """Property: merge reduces count by (total_fragments - num_chains) for M chains of length L.

    elements_in = M * L + N_independent
    elements_out = M + N_independent   (each chain of L → 1)
    """
    elements: list[OdlElement] = []
    id_counter = 1

    for c in range(m_chains):
        for i in range(chain_len):
            tid = id_counter
            next_id = id_counter + 1 if i < chain_len - 1 else None
            prev_id = id_counter - 1 if i > 0 else None
            elements.append(
                OdlElement(
                    id_=tid,
                    page_number=i + 1,
                    element_type="table",
                    content=f"chain {c} fragment {i}",
                    next_table_id=next_id,
                    previous_table_id=prev_id,
                )
            )
            id_counter += 1

    for _ in range(n_independent):
        elements.append(
            OdlElement(
                id_=id_counter,
                page_number=1,
                element_type="table",
                content="independent",
            )
        )
        id_counter += 1

    result = merge_tables(elements)

    expected_count = m_chains + n_independent
    assert len(result) == expected_count, (
        f"Expected {expected_count} after merging {m_chains} chains×{chain_len} "
        f"+ {n_independent} independent, got {len(result)}"
    )


# ---------------------------------------------------------------------------
# 3.12  Security: malformed elements handled gracefully
# ---------------------------------------------------------------------------


class TestWalkerSecurity:
    def test_missing_kids_key_safe(self):
        """FR 3.12: walker handles missing 'kids' without raising."""
        result = walk_tree({})
        assert result == []

    def test_none_kids_safe(self):
        result = walk_tree({"kids": None})
        assert result == []

    def test_element_missing_type_skipped(self):
        doc = {"kids": [{"id": 1, "content": "no type here"}]}
        result = walk_tree(doc)
        assert result == []

    def test_malformed_table_rows_safe(self):
        """Walker and extract_content handle table with missing 'rows' key."""
        el = {"type": "table", "id": 1, "page number": 1}
        content = _extract_content(el)
        assert content == ""

    def test_malformed_list_items_safe(self):
        el = {"type": "list", "id": 1, "page number": 1}
        content = _extract_content(el)
        assert content == ""

    def test_deep_nesting_does_not_crash(self):
        """Deeply nested container elements are walked without stack overflow."""
        doc: dict = {"kids": []}
        current = doc
        for i in range(50):
            child = {"type": "paragraph", "id": i, "content": f"p{i}", "page number": 1}
            current["kids"] = [child]
            current = child
        walk_tree(doc)  # must not raise

    def test_extract_content_does_not_eval_content(self):
        """FR 3.13: content strings are treated as data, never executed."""
        el = {"type": "paragraph", "content": "__import__('os').system('echo pwned')"}
        result = _extract_content(el)
        # Content is returned as-is string, not executed
        assert "__import__" in result
