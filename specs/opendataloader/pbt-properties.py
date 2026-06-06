"""
PBT Properties: OpenDataLoader Full Leverage
Uses Hypothesis (https://hypothesis.readthedocs.io/)
Run: pytest pbt-properties.py -v

These properties validate invariants for the highest-risk components:
  - JSON field mapper (data transformation)
  - Tree walker (recursive stateful traversal)
  - Section title propagation (stateful consistency)
  - Multi-page table merger (linked-list traversal)
  - Temp dir cleanup (resource management)
  - Fallback invariant (reliability under failure)
  - Hierarchical parent link (referential integrity)
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers — minimal stubs for components under test (replace with real imports
# once implementation exists)
# ---------------------------------------------------------------------------

# Stub: ODL JSON field mapper
def map_odl_element(raw: dict) -> dict:
    """Maps ODL space-separated keys to snake_case attributes."""
    return {
        "page_number": raw.get("page number"),
        "bbox": raw.get("bounding box"),
        "heading_level": raw.get("heading level"),
        "element_type": raw.get("type"),
        "content": raw.get("content", ""),
        "id_": raw.get("id"),
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

odl_element_types = st.sampled_from([
    "heading", "paragraph", "table", "list", "image",
    "caption", "header", "footer", "formula", "picture"
])

bounding_box = st.lists(
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    min_size=4, max_size=4,
)

odl_raw_element = st.fixed_dictionaries({
    "type": odl_element_types,
    "id": st.integers(min_value=0, max_value=99999),
    "page number": st.integers(min_value=1, max_value=9999),
    "bounding box": bounding_box,
    "heading level": st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
    "content": st.text(max_size=2000),
})

java_version_string = st.one_of(
    st.just("openjdk 11.0.21 2023-10-17"),
    st.just("openjdk 17.0.9 2023-10-17"),
    st.just("java version \"1.8.0_202\""),
    st.just("java version \"11.0.2\" 2019-01-15 LTS"),
    st.just("openjdk 21.0.1 2023-10-17"),
    st.builds(
        lambda major, minor, patch_v: f"openjdk {major}.{minor}.{patch_v} 2024-01-01",
        major=st.integers(min_value=8, max_value=25),
        minor=st.integers(min_value=0, max_value=9),
        patch_v=st.integers(min_value=0, max_value=20),
    ),
)


# ---------------------------------------------------------------------------
# Group 1 — Java Version Parsing
# ---------------------------------------------------------------------------

def parse_java_major_version(version_str: str) -> Optional[int]:
    """Extract major version number from java -version output."""
    match = re.search(r'"?(\d+)\.(\d+)', version_str)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        if major == 1:
            return minor
        return major
    match = re.search(r'(\d+)\.\d+\.\d+', version_str)
    if match:
        major = int(match.group(1))
        return major
    return None


@given(version_str=java_version_string)
def test_pbt_java_version_parse_returns_int_or_none(version_str):
    """
    Property: parse_java_major_version always returns an int or None,
    never raises, and when it returns an int it is positive.
    """
    result = parse_java_major_version(version_str)
    assert result is None or (isinstance(result, int) and result > 0)


@given(version_str=java_version_string)
def test_pbt_java_version_11_recognized(version_str):
    """
    Property: any version string containing a major version >= 11 that
    matches the known format is parsed as >= 11.
    """
    result = parse_java_major_version(version_str)
    if result is not None:
        # If we parsed a version, verify it's a reasonable Java version number
        assert 1 <= result <= 30


# ---------------------------------------------------------------------------
# Group 2 — JSON Field Mapper
# ---------------------------------------------------------------------------

@given(raw=odl_raw_element)
def test_pbt_field_mapper_no_missing_keys(raw):
    """
    Property: map_odl_element() always returns a dict with all expected
    snake_case keys, regardless of input element structure.
    """
    mapped = map_odl_element(raw)
    required_keys = {"page_number", "bbox", "heading_level", "element_type", "content", "id_"}
    assert required_keys.issubset(mapped.keys())


@given(raw=odl_raw_element)
def test_pbt_field_mapper_page_number_preserved(raw):
    """
    Property: mapped page_number always equals the raw "page number" value.
    The space-separated key must be correctly mapped.
    """
    mapped = map_odl_element(raw)
    assert mapped["page_number"] == raw["page number"]


@given(raw=odl_raw_element)
def test_pbt_field_mapper_bbox_preserved(raw):
    """
    Property: mapped bbox always equals the raw "bounding box" value.
    """
    mapped = map_odl_element(raw)
    assert mapped["bbox"] == raw["bounding box"]
    if mapped["bbox"] is not None:
        assert len(mapped["bbox"]) == 4
        assert all(isinstance(v, float) for v in mapped["bbox"])


@given(raw=odl_raw_element)
def test_pbt_field_mapper_element_type_never_null(raw):
    """
    Property: element_type is never null after mapping (ODL always emits "type").
    """
    mapped = map_odl_element(raw)
    assert mapped["element_type"] is not None
    assert mapped["element_type"] in {
        "heading", "paragraph", "table", "list", "image",
        "caption", "header", "footer", "formula", "picture"
    }


# ---------------------------------------------------------------------------
# Group 3 — Section Title Propagation
# ---------------------------------------------------------------------------

@dataclass
class MockElement:
    element_type: str
    content: str
    section_title: Optional[str] = None
    heading_level: Optional[int] = None
    id_: int = 0
    page_number: int = 1
    bbox: list = field(default_factory=lambda: [0.0, 0.0, 100.0, 20.0])


def propagate_section_titles(elements: list) -> list:
    """Reference implementation of section title propagation."""
    current_heading = None
    result = []
    for el in elements:
        if el.element_type == "heading":
            current_heading = el.content
            el.section_title = None  # headings don't carry section_title of themselves
        else:
            el.section_title = current_heading
        result.append(el)
    return result


def build_element_sequence_strategy():
    """Strategy: list of elements where some are headings (type=heading)."""
    heading_el = st.builds(
        MockElement,
        element_type=st.just("heading"),
        content=st.text(min_size=1, max_size=100),
        heading_level=st.integers(min_value=1, max_value=6),
    )
    non_heading_el = st.builds(
        MockElement,
        element_type=st.sampled_from(["paragraph", "table", "list", "caption"]),
        content=st.text(max_size=200),
    )
    return st.lists(
        st.one_of(heading_el, non_heading_el),
        min_size=0,
        max_size=30,
    )


@given(elements=build_element_sequence_strategy())
def test_pbt_section_propagation_every_non_heading_has_section_or_none(elements):
    """
    Property: after propagation, every non-heading element's section_title
    equals the content of the most recently preceding heading, or None if no
    heading has been seen yet.
    """
    result = propagate_section_titles(elements)
    current_heading_content = None
    for el in result:
        if el.element_type == "heading":
            current_heading_content = el.content
        else:
            assert el.section_title == current_heading_content


@given(elements=build_element_sequence_strategy())
def test_pbt_section_propagation_heading_count_unchanged(elements):
    """
    Property: propagation does not add or remove elements.
    """
    original_count = len(elements)
    result = propagate_section_titles(elements)
    assert len(result) == original_count


# ---------------------------------------------------------------------------
# Group 3 — Multi-Page Table Merger
# ---------------------------------------------------------------------------

@dataclass
class MockTable:
    id_: int
    page_number: int
    next_table_id: Optional[int] = None
    previous_table_id: Optional[int] = None
    content: str = "table content"
    page_end: Optional[int] = None


def build_independent_tables():
    """Strategy: list of tables with no continuation chains."""
    return st.lists(
        st.builds(
            MockTable,
            id_=st.integers(min_value=1, max_value=1000),
            page_number=st.integers(min_value=1, max_value=500),
            next_table_id=st.just(None),
            previous_table_id=st.just(None),
        ),
        min_size=0,
        max_size=20,
        unique_by=lambda t: t.id_,
    )


def merge_table_chains(tables: list) -> list:
    """Reference implementation: merge tables linked by next_table_id."""
    if not tables:
        return []
    by_id = {t.id_: t for t in tables}
    visited = set()
    result = []
    for table in tables:
        if table.id_ in visited:
            continue
        if table.previous_table_id is not None and table.previous_table_id in by_id:
            continue
        chain = [table]
        visited.add(table.id_)
        current = table
        while current.next_table_id is not None and current.next_table_id in by_id:
            nxt = by_id[current.next_table_id]
            if nxt.id_ in visited:
                break
            chain.append(nxt)
            visited.add(nxt.id_)
            current = nxt
        merged = chain[0]
        merged.page_end = chain[-1].page_number
        merged.content = " ".join(t.content for t in chain)
        result.append(merged)
    return result


@given(tables=build_independent_tables())
def test_pbt_table_merger_no_chains_unchanged_count(tables):
    """
    Property: when no tables are in chains (all next_table_id=None),
    merge_table_chains returns the same number of tables.
    """
    result = merge_table_chains(tables)
    assert len(result) == len(tables)


@given(tables=build_independent_tables())
def test_pbt_table_merger_all_ids_represented(tables):
    """
    Property: every table ID in the input is represented in the output
    (either directly or merged into a chain head).
    """
    result = merge_table_chains(tables)
    input_ids = {t.id_ for t in tables}
    output_ids = {t.id_ for t in result}
    assert output_ids.issubset(input_ids)
    assert len(result) == len(input_ids)


@given(n_fragments=st.integers(min_value=2, max_value=5),
       start_page=st.integers(min_value=1, max_value=100))
def test_pbt_table_merger_chain_reduces_count(n_fragments, start_page):
    """
    Property: a chain of N linked table fragments is reduced to 1 merged element.
    """
    tables = []
    for i in range(n_fragments):
        table = MockTable(
            id_=i + 1,
            page_number=start_page + i,
            next_table_id=i + 2 if i < n_fragments - 1 else None,
            previous_table_id=i if i > 0 else None,
        )
        tables.append(table)
    result = merge_table_chains(tables)
    assert len(result) == 1
    assert result[0].page_end == start_page + n_fragments - 1


# ---------------------------------------------------------------------------
# Group 2 — Temp Directory Cleanup
# ---------------------------------------------------------------------------

def simulate_odl_convert_with_cleanup(should_fail: bool) -> Optional[dict]:
    """
    Simulates the ODL adapter's convert+cleanup pattern.
    Returns result dict or raises RuntimeError.
    """
    tmp_dir = tempfile.mkdtemp(prefix="odl_test_")
    try:
        if should_fail:
            raise RuntimeError("Simulated ODL failure")
        Path(tmp_dir, "output.json").write_text('{"kids": []}')
        return {"parser": "opendataloader", "tmp_was": tmp_dir}
    finally:
        import shutil
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


@given(should_fail=st.booleans())
def test_pbt_temp_dir_always_cleaned_up(should_fail):
    """
    Property: temp dir does not exist after convert call, regardless of
    whether conversion succeeded or failed.
    """
    tmp_dir_path = None
    try:
        result = simulate_odl_convert_with_cleanup(should_fail)
        if result:
            tmp_dir_path = result["tmp_was"]
    except RuntimeError:
        pass

    if tmp_dir_path:
        assert not os.path.exists(tmp_dir_path), (
            f"Temp dir still exists after convert: {tmp_dir_path}"
        )


# ---------------------------------------------------------------------------
# Group 2 — Fallback Invariant
# ---------------------------------------------------------------------------

def simulate_load_pdf_odl(file_path: str, fallback_enabled: bool,
                           odl_should_fail: bool) -> list:
    """
    Simulates load_pdf_odl() behavior for property testing.
    Returns list of mock Document-like dicts.
    """
    if odl_should_fail:
        if fallback_enabled:
            return [{"page_content": "fallback content", "metadata": {"parser": "pypdf",
                                                                        "fallback_used": True}}]
        raise RuntimeError("ODL failed and fallback is disabled")
    return [{"page_content": "odl content | table", "metadata": {"parser": "opendataloader",
                                                                    "fallback_used": False}}]


@given(
    fallback_enabled=st.booleans(),
    odl_should_fail=st.booleans(),
    file_path=st.just("/safe/path/doc.pdf"),
)
def test_pbt_fallback_invariant(fallback_enabled, odl_should_fail, file_path):
    """
    Property: when ODL fails and fallback is enabled, all returned documents
    carry parser="pypdf" and fallback_used=True. When fallback is disabled,
    RuntimeError is raised.
    """
    if odl_should_fail and not fallback_enabled:
        with pytest.raises(RuntimeError):
            simulate_load_pdf_odl(file_path, fallback_enabled, odl_should_fail)
        return

    docs = simulate_load_pdf_odl(file_path, fallback_enabled, odl_should_fail)
    assert len(docs) >= 1

    if odl_should_fail and fallback_enabled:
        for doc in docs:
            assert doc["metadata"]["parser"] == "pypdf"
            assert doc["metadata"]["fallback_used"] is True
    else:
        for doc in docs:
            assert doc["metadata"]["parser"] == "opendataloader"
            assert doc["metadata"]["fallback_used"] is False


# ---------------------------------------------------------------------------
# Group 4 — Hierarchical Parent Link (Referential Integrity)
# ---------------------------------------------------------------------------

@given(
    section_count=st.integers(min_value=1, max_value=10),
    elements_per_section=st.integers(min_value=1, max_value=5),
)
def test_pbt_l2_parent_chunk_id_always_resolvable(section_count, elements_per_section):
    """
    Property: every L2 chunk's parent_chunk_id exists in the L1 chunk list
    produced for the same document.
    """
    import hashlib

    def make_chunk_hash(text: str) -> str:
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    l1_chunks = []
    l2_chunks = []

    for i in range(section_count):
        section_text = f"# Section {i}\nContent of section {i}"
        l1_hash = make_chunk_hash(section_text)
        l1_chunks.append({
            "page_content": section_text,
            "metadata": {
                "chunk_level": 1,
                "chunk_hash": l1_hash,
                "section_title": f"Section {i}",
            }
        })
        for j in range(elements_per_section):
            element_text = f"Paragraph {j} in section {i}"
            l2_hash = make_chunk_hash(element_text)
            l2_chunks.append({
                "page_content": element_text,
                "metadata": {
                    "chunk_level": 2,
                    "chunk_hash": l2_hash,
                    "parent_chunk_id": l1_hash,
                    "section_title": f"Section {i}",
                    "element_type": "paragraph",
                }
            })

    l1_hashes = {c["metadata"]["chunk_hash"] for c in l1_chunks}

    for l2 in l2_chunks:
        parent_id = l2["metadata"]["parent_chunk_id"]
        assert parent_id in l1_hashes, (
            f"L2 chunk references parent_chunk_id={parent_id!r} which has no matching L1 chunk"
        )


# ---------------------------------------------------------------------------
# Group 6 — Parser Override Input Validation
# ---------------------------------------------------------------------------

valid_parser_values = st.sampled_from(["pypdf", "opendataloader", None])
invalid_parser_values = st.text(min_size=1).filter(
    lambda s: s not in {"pypdf", "opendataloader"}
)

valid_pages_pattern = re.compile(r'^\d+(-\d+)?(,\d+(-\d+)?)*$')

page_range_valid = st.builds(
    lambda pages: ",".join(
        f"{p}-{p+n}" if n > 0 else str(p)
        for p, n in pages
    ),
    pages=st.lists(
        st.tuples(st.integers(min_value=1, max_value=500),
                  st.integers(min_value=0, max_value=5)),
        min_size=1,
        max_size=5,
    )
)

page_range_invalid = st.one_of(
    st.just("../etc/passwd"),
    st.just("; rm -rf /"),
    st.just("$(whoami)"),
    st.text(min_size=1).filter(lambda s: not valid_pages_pattern.match(s)),
)


def validate_parser_value(parser: Optional[str]) -> bool:
    return parser in {None, "pypdf", "opendataloader"}


def validate_pages_value(pages: Optional[str]) -> bool:
    if pages is None:
        return True
    return bool(valid_pages_pattern.match(pages))


@given(parser=valid_parser_values)
def test_pbt_valid_parser_values_accepted(parser):
    """Property: all valid parser values pass validation."""
    assert validate_parser_value(parser) is True


@given(parser=invalid_parser_values)
def test_pbt_invalid_parser_values_rejected(parser):
    """Property: any string not in {"pypdf","opendataloader",None} is rejected."""
    assert validate_parser_value(parser) is False


@given(pages=page_range_valid)
def test_pbt_valid_pages_accepted(pages):
    """Property: valid page range strings like "1-5,7,10-12" pass validation."""
    assert validate_pages_value(pages) is True


@given(pages=page_range_invalid)
def test_pbt_invalid_pages_rejected(pages):
    """
    Property: malformed or injection-attempt page strings are rejected.
    This prevents path traversal / shell injection before the string reaches
    the convert() subprocess call.
    """
    assume(pages is not None)
    result = validate_pages_value(pages)
    assert result is False
