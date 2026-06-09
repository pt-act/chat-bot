"""OpenDataLoader PDF adapter — Markdown chunks + JSON tree walker.

Group 2 (Track 1):
- opendataloader_pdf.convert() in a scoped temp dir
- RecursiveCharacterTextSplitter on the resulting Markdown
- PyPDFLoader fallback when PDF_PARSER_FALLBACK=true

Group 3 (Tree Walker):
- OdlElement dataclass with snake_case attributes mapped from ODL JSON keys
- _extract_content() recursive text extractor
- walk_tree() depth-first walker with section-title propagation
- merge_tables() multi-page table chain merger
- load_pdf_odl() upgraded to format="json,markdown"; walks JSON for accurate
  page_count and element metadata; Markdown remains the chunk content source
"""

import hashlib
import json as _json
import logging
import math
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import get_settings
from ingest.pdf_preflight import _hybrid_reachable, preflight_check

logger = logging.getLogger(__name__)

# ODL uses horizontal rules as page separators in Markdown output.
_PAGE_SEP = "\n---\n"

# Element types whose text is fully captured by _extract_content (no further walker descent).
_LEAF_TYPES = frozenset(
    {
        "heading",
        "paragraph",
        "caption",
        "table",
        "list",
        "image",
        "formula",
        "picture",
        "header",
        "footer",
    }
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class OdlElement:
    """One structural element extracted from an ODL JSON document."""

    id_: int
    page_number: int
    element_type: str
    content: str
    section_title: str | None = None
    heading_level: int | None = None
    bbox: list[float] | None = None
    page_end: int | None = None
    next_table_id: int | None = None
    previous_table_id: int | None = None


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------


def _extract_content(element: dict, include_header_footer: bool = False) -> str:
    """Recursively extract plain text from an ODL JSON element.

    Returns an empty string for element types that carry no textual RAG value
    (image, or header/footer when the flag is off).
    """
    el_type = element.get("type", "")

    if el_type in ("heading", "paragraph", "caption"):
        return element.get("content", "")

    if el_type == "list":
        parts: list[str] = []
        for item in element.get("list items", []):
            # List items may carry direct "content" or nest kids
            item_text = item.get("content", "")
            if not item_text:
                for kid in item.get("kids", []):
                    item_text += _extract_content(kid, include_header_footer)
            if item_text:
                parts.append(item_text)
        return "\n".join(parts)

    if el_type == "table":
        parts = []
        for row in element.get("rows", []):
            for cell in row.get("cells", []):
                for kid in cell.get("kids", []):
                    kid_text = _extract_content(kid, include_header_footer)
                    if kid_text:
                        parts.append(kid_text)
        return " | ".join(parts)

    if el_type in ("header", "footer"):
        return element.get("content", "") if include_header_footer else ""

    if el_type == "image":
        return ""

    if el_type == "formula":
        return element.get("content", "")

    if el_type == "picture":
        return element.get("description", "")

    # Unknown / container — try the direct "content" field, fall back to empty.
    return element.get("content", "")


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def walk_tree(
    doc: dict,
    include_header_footer: bool = False,
) -> list[OdlElement]:
    """Depth-first walk of an ODL JSON document; returns a flat list of OdlElements.

    Section-title propagation: the text of the most recently seen heading is
    injected as ``section_title`` on every subsequent non-heading element.
    Header/footer elements are omitted unless include_header_footer is True.
    """
    elements: list[OdlElement] = []
    current_heading_text: str | None = None

    def _walk(kids: list) -> None:
        nonlocal current_heading_text
        for el in kids or []:
            el_type = el.get("type", "")
            if not el_type:
                continue
            if el_type in ("header", "footer") and not include_header_footer:
                continue

            content = _extract_content(el, include_header_footer)
            odl_el = OdlElement(
                id_=el.get("id", 0),
                page_number=el.get("page number", 1),
                element_type=el_type,
                content=content,
                heading_level=el.get("heading level"),
                bbox=el.get("bounding box"),
                next_table_id=el.get("next table id"),
                previous_table_id=el.get("previous table id"),
            )

            if el_type == "heading":
                current_heading_text = content
                # Headings do not carry a section_title of their own (they define it)
            else:
                odl_el.section_title = current_heading_text

            elements.append(odl_el)

            # Recurse into non-leaf containers (e.g. section wrappers with nested kids).
            if el_type not in _LEAF_TYPES:
                _walk(el.get("kids", []))

    _walk(doc.get("kids", []))
    return elements


# ---------------------------------------------------------------------------
# Multi-page table merger
# ---------------------------------------------------------------------------


def merge_tables(elements: list[OdlElement]) -> list[OdlElement]:
    """Merge tables linked by ``next_table_id`` into single logical elements.

    Tables that are fragment continuations (have a ``previous_table_id`` pointing
    to another table in the list) are absorbed into the chain head and removed.
    Non-table elements pass through unchanged.
    """
    if not elements:
        return []

    table_by_id: dict[int, OdlElement] = {el.id_: el for el in elements if el.element_type == "table"}
    absorbed: set[int] = set()
    result: list[OdlElement] = []

    for el in elements:
        if el.element_type != "table":
            result.append(el)
            continue

        if el.id_ in absorbed:
            continue

        # Skip continuation fragments — they'll be consumed by their chain head.
        if el.previous_table_id is not None and el.previous_table_id in table_by_id:
            continue

        # Walk the forward chain from this head.
        chain = [el]
        absorbed.add(el.id_)
        current = el
        while current.next_table_id is not None and current.next_table_id in table_by_id:
            nxt = table_by_id[current.next_table_id]
            if nxt.id_ in absorbed:
                break
            chain.append(nxt)
            absorbed.add(nxt.id_)
            current = nxt

        if len(chain) > 1:
            el.content = "\n".join(c.content for c in chain if c.content)
            el.page_end = chain[-1].page_number

        result.append(el)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _approx_page_count(md_text: str) -> int:
    """Estimate page count from horizontal-rule page separators."""
    return max(1, md_text.count(_PAGE_SEP) + 1)


def _make_splitter(chunk_size: int = 800, chunk_overlap: int = 100) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ".", " ", ""]
    )


# Allowed page-range pattern — validated before passing to the convert() subprocess.
_PAGES_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")


def _validate_bbox(bbox) -> list[float] | None:
    """Return a validated 4-float bbox list, or None when malformed.

    Guards against non-numeric, NaN/Inf, or wrong-length values from ODL JSON
    before they are written to ChromaDB / Redis metadata (FR 6.10).
    """
    if bbox is None:
        return None
    try:
        floats = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    if len(floats) != 4 or not all(math.isfinite(v) for v in floats):
        return None
    return floats


def _clean_odl_text(text: str) -> str:
    """Mirrors policies._clean_text — must match for chunk_hash consistency."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _odl_chunk_hash(text: str) -> str:
    """Mirrors policies._chunk_hash — MD5 of cleaned text."""
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# Hierarchical chunk builder (Group 4)
# ---------------------------------------------------------------------------


def build_hierarchical_chunks(
    elements: list[OdlElement],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> tuple[list[Document], list[Document]]:
    """Build L1 (section) and L2 (element) Document pairs from walker elements.

    Returns ``(l1_chunks, l2_chunks)``.

    L1 — one Document per heading section.  Content = heading + all body element
    text joined with ``\\n\\n``.  Oversized sections are split with
    RecursiveCharacterTextSplitter; each split piece carries ``chunk_level=1``
    and the same ``section_title``.

    L2 — one Document per non-heading element.  Content = element text.
    ``parent_chunk_id`` is the pre-computed ``chunk_hash`` of the *first* L1
    split piece for the same section (deterministic, equals the value
    ``policies._build_chunks`` will compute later because both apply the same
    cleaning and MD5 hashing).
    """
    l1_chunks: list[Document] = []
    l2_chunks: list[Document] = []
    splitter = _make_splitter(chunk_size, chunk_overlap)

    # -----------------------------------------------------------------------
    # Group elements into sections: (heading_element | None, [body_elements])
    # -----------------------------------------------------------------------
    sections: list[tuple[OdlElement | None, list[OdlElement]]] = []
    current_heading: OdlElement | None = None
    current_body: list[OdlElement] = []

    for el in elements:
        if el.element_type == "heading":
            # Flush the previous section (even if empty prologue)
            if current_body or current_heading is not None:
                sections.append((current_heading, current_body))
            current_heading = el
            current_body = []
        else:
            current_body.append(el)

    # Flush final section
    if current_heading is not None or current_body:
        sections.append((current_heading, current_body))

    # -----------------------------------------------------------------------
    # Build L1 + L2 Documents for each section
    # -----------------------------------------------------------------------
    for heading, body in sections:
        section_title = heading.content if heading else None
        heading_level = heading.heading_level if heading else None
        section_page = heading.page_number if heading else (body[0].page_number if body else 1)
        section_page_end = body[-1].page_number if body else section_page

        # --- Build L1 section content ---
        l1_parts: list[str] = []
        if heading:
            level = heading.heading_level or 1
            l1_parts.append(f"{'#' * level} {heading.content}")
        for el in body:
            if el.content.strip():
                l1_parts.append(el.content.strip())

        l1_raw = "\n\n".join(l1_parts)
        if not l1_raw.strip():
            continue  # entirely empty section — skip

        # Split oversized sections; apply cleaning so hashes are stable.
        split_docs = splitter.create_documents([l1_raw])
        first_l1_hash: str | None = None

        for split_doc in split_docs:
            cleaned = _clean_odl_text(split_doc.page_content)
            if not cleaned:
                continue
            part_hash = _odl_chunk_hash(cleaned)
            if first_l1_hash is None:
                first_l1_hash = part_hash

            l1_chunks.append(
                Document(
                    page_content=cleaned,
                    metadata={
                        "page": section_page,
                        "chunk_level": 1,
                        "section_title": section_title,
                        "element_type": "section",
                        "parent_chunk_id": None,
                        "heading_level": heading_level,
                        "bbox": None,
                        "page_end": section_page_end,
                        # Pre-computed so tests can verify referential integrity without
                        # going through _build_chunks().  policies._build_chunks will
                        # recompute and store the same value under "chunk_hash".
                        "chunk_hash": part_hash,
                    },
                )
            )

        # --- Build L2 element Documents ---
        for el in body:
            content = _clean_odl_text(el.content)
            if not content:
                continue
            l2_chunks.append(
                Document(
                    page_content=content,
                    metadata={
                        "page": el.page_number,
                        "chunk_level": 2,
                        "section_title": el.section_title,
                        "element_type": el.element_type,
                        "parent_chunk_id": first_l1_hash,
                        "heading_level": None,
                        "bbox": _validate_bbox(el.bbox),  # FR 6.10: sanitise before storage
                        "page_end": el.page_end,
                    },
                )
            )

    return l1_chunks, l2_chunks


def _pypdf_fallback(file_path: str) -> tuple[list[Document], list, dict]:
    """Load PDF with PyPDFLoader and split, returning (chunks, elements, diagnostics)."""
    pages = PyPDFLoader(file_path).load()
    chunks = _make_splitter().split_documents(pages)
    for doc in chunks:
        doc.metadata.update({"parser": "pypdf", "fallback_used": True, "parser_mode": "local"})
    return (
        chunks,
        [],
        {
            "parser": "pypdf",
            "fallback_used": "true",
            "page_count": str(len(pages)),
            "element_count": str(len(chunks)),
            "parser_mode": "local",
        },
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_pdf_odl(
    file_path: str,
    settings=None,
    pages: str | None = None,
    hybrid_mode_override: str | None = None,
) -> tuple[list[Document], list[OdlElement], dict]:
    """Convert a PDF with OpenDataLoader and return (split_chunks, elements, diagnostics).

    split_chunks: Markdown text split by RecursiveCharacterTextSplitter — chunk content.
    elements: list[OdlElement] from the JSON tree walker (empty when JSON unavailable).
    diagnostics: FR8 fields — parser, fallback_used, page_count, element_count, parser_mode.

    pages: optional page-range string (e.g. "1-10") validated against the allowed pattern
        before being passed to convert() — prevents shell-injection (FR 6.11).
    hybrid_mode_override: per-request override for settings.odl_hybrid_mode.

    The temporary ODL output directory is always removed, even on exception.
    Raises RuntimeError when preflight fails and PDF_PARSER_FALLBACK is disabled.
    """
    if settings is None:
        settings = get_settings()

    # FR 6.11: validate pages before it reaches the convert() subprocess.
    if pages is not None and not _PAGES_RE.match(pages):
        raise ValueError(f"pages must be a range like '1-10' or '1-5,8,12-15' — got {pages!r}")

    ok, reason = preflight_check()
    if not ok:
        if settings.pdf_parser_fallback:
            logger.warning("ODL preflight failed (%s); falling back to PyPDFLoader", reason)
            return _pypdf_fallback(file_path)
        raise RuntimeError(f"OpenDataLoader preflight failed: {reason}")

    # Determine whether hybrid mode is actually usable right now.
    # Checking at call-time (not only at preflight) means we correctly strip hybrid
    # params from convert() when the server is unreachable + fallback is enabled,
    # rather than letting convert() fail with a connection error.
    use_hybrid = False
    if settings.odl_hybrid:
        hybrid_ok, hybrid_reason = _hybrid_reachable(settings.odl_hybrid_url)
        if hybrid_ok:
            use_hybrid = True
        elif settings.odl_hybrid_fallback:
            logger.warning(
                "Hybrid server unreachable (%s); using local Java only for %s",
                hybrid_reason,
                Path(file_path).name,
            )
        else:
            raise RuntimeError(f"Hybrid server unreachable and ODL_HYBRID_FALLBACK is disabled: {hybrid_reason}")

    parser_mode = "hybrid" if use_hybrid else "local"
    tmp_dir = tempfile.mkdtemp(prefix="odl_")
    try:
        import opendataloader_pdf

        stem = Path(file_path).stem
        odl_format = settings.odl_format  # default "json,markdown"
        effective_hybrid_mode = hybrid_mode_override or settings.odl_hybrid_mode

        convert_kwargs: dict = {
            "input_path": file_path,
            "output_dir": tmp_dir,
            "format": odl_format,
            "quiet": True,
        }
        if settings.odl_reading_order:
            convert_kwargs["reading_order"] = settings.odl_reading_order
        if settings.odl_use_struct_tree:
            convert_kwargs["use_struct_tree"] = True
        if pages:
            convert_kwargs["pages"] = pages
        if use_hybrid:
            convert_kwargs["hybrid"] = settings.odl_hybrid
            convert_kwargs["hybrid_mode"] = effective_hybrid_mode
            if settings.odl_hybrid_url:
                convert_kwargs["hybrid_url"] = settings.odl_hybrid_url
            if settings.odl_enrich_formula:
                convert_kwargs["enrich_formula"] = True
            if settings.odl_enrich_pictures:
                convert_kwargs["enrich_pictures"] = True

        opendataloader_pdf.convert(**convert_kwargs)

        md_path = Path(tmp_dir) / f"{stem}.md"
        if not md_path.exists():
            raise RuntimeError(f"ODL did not produce expected Markdown file '{md_path.name}'")

        md_text = md_path.read_text(encoding="utf-8")
        page_count = _approx_page_count(md_text)
        elements: list[OdlElement] = []

        # Walk JSON when available — provides accurate page_count and element metadata.
        if "json" in odl_format:
            json_path = Path(tmp_dir) / f"{stem}.json"
            if json_path.exists():
                try:
                    doc_data = _json.loads(json_path.read_text(encoding="utf-8"))
                    page_count = int(doc_data.get("number of pages", page_count))
                    raw_elements = walk_tree(
                        doc_data,
                        include_header_footer=settings.odl_include_header_footer,
                    )
                    elements = merge_tables(raw_elements)
                except Exception as walk_exc:
                    logger.warning(
                        "ODL JSON walk failed for %s (%s); falling back to Markdown-only",
                        Path(file_path).name,
                        walk_exc,
                    )

        base_doc = Document(
            page_content=md_text,
            metadata={
                "page": 0,
                "parser": "opendataloader",
                "fallback_used": False,
                "parser_mode": parser_mode,
            },
        )
        chunks = _make_splitter().split_documents([base_doc])

        # element_count: prefer walker element count; fall back to chunk count.
        element_count = len(elements) if elements else len(chunks)

        return (
            chunks,
            elements,
            {
                "parser": "opendataloader",
                "fallback_used": "false",
                "page_count": str(page_count),
                "element_count": str(element_count),
                "parser_mode": parser_mode,
            },
        )

    except Exception as exc:
        if settings.pdf_parser_fallback:
            logger.warning(
                "ODL conversion failed for %s (%s); falling back to PyPDFLoader",
                Path(file_path).name,
                exc,
            )
            return _pypdf_fallback(file_path)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
