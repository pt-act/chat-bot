"""Document loader registry — turns a local file into LangChain ``Document``s.

Supports a handful of common knowledge-base formats behind one ``load_documents``
dispatch so the ingest pipeline is format-agnostic and new formats are a one-line add.

Heavy/optional parsers (``docx2txt``, ``beautifulsoup4``) are imported lazily inside
their loader so importing this module stays cheap and a missing optional parser only
fails the formats that need it.
"""

import logging

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Extensions handled by the plain-text reader (no third-party parser needed).
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
# All ingestable extensions (lowercase, leading dot).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"} | TEXT_EXTENSIONS


def detect_extension(name: str) -> str:
    """Lowercase extension (incl. dot) of a filename or URL; ``""`` if none.

    Strips URL query/fragment so ``.../doc.pdf?sig=…`` resolves to ``.pdf``.
    """
    name = name.split("?", 1)[0].split("#", 1)[0]
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return base[dot:].lower() if dot > 0 else ""


def is_supported(name: str) -> bool:
    return detect_extension(name) in SUPPORTED_EXTENSIONS


def _load_text(file_path: str) -> list[Document]:
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [Document(page_content=text, metadata={"page": 0})]


def _load_docx(file_path: str) -> list[Document]:
    import docx2txt

    text = docx2txt.process(file_path) or ""
    return [Document(page_content=text, metadata={"page": 0})]


def _load_html(file_path: str) -> list[Document]:
    from bs4 import BeautifulSoup

    with open(file_path, encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    # Drop non-content elements before extracting visible text.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return [Document(page_content=soup.get_text(" ", strip=True), metadata={"page": 0})]


def load_documents(file_path: str, ext: str) -> list[Document]:
    """Load a local file into Documents based on its extension.

    Raises ``ValueError`` for an unsupported extension.
    """
    ext = ext.lower()
    if ext == ".pdf":
        return PyPDFLoader(file_path).load()
    if ext in TEXT_EXTENSIONS:
        return _load_text(file_path)
    if ext == ".docx":
        return _load_docx(file_path)
    if ext in (".html", ".htm"):
        return _load_html(file_path)
    raise ValueError(f"Unsupported document format: {ext!r}")
