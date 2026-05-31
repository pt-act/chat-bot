"""Tests for the multi-format document loader registry and format validation."""

import tempfile
from unittest.mock import patch

import pytest

from ingest.loaders import detect_extension, is_supported, load_documents


def _tmp(suffix: str, data: bytes) -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(data)
    f.close()
    return f.name


class TestExtensionDetection:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("report.pdf", ".pdf"),
            ("REPORT.PDF", ".pdf"),
            ("notes.MD", ".md"),
            ("https://x.com/a/b/doc.docx?sig=abc#frag", ".docx"),
            ("/path/to/page.html", ".html"),
            ("no_extension", ""),
            (".hidden", ""),  # leading dot only → not an extension
        ],
    )
    def test_detect_extension(self, name, expected):
        assert detect_extension(name) == expected

    def test_is_supported(self):
        assert is_supported("a.pdf") and is_supported("a.txt") and is_supported("a.html")
        assert not is_supported("a.exe") and not is_supported("noext")


class TestLoadDocuments:
    def test_loads_plain_text(self):
        path = _tmp(".txt", b"hello world\nsecond line")
        docs = load_documents(path, ".txt")
        assert len(docs) == 1
        assert "hello world" in docs[0].page_content
        assert docs[0].metadata["page"] == 0

    def test_loads_markdown_as_text(self):
        path = _tmp(".md", b"# Title\n\nSome **bold** content.")
        docs = load_documents(path, ".md")
        assert "Some" in docs[0].page_content

    def test_loads_html_stripping_tags(self):
        html = b"<html><head><style>.x{}</style></head><body><h1>Hi</h1><p>Body text</p></body></html>"
        path = _tmp(".html", html)
        docs = load_documents(path, ".html")
        text = docs[0].page_content
        assert "Hi" in text and "Body text" in text
        assert "<h1>" not in text and ".x{}" not in text  # tags + style dropped

    def test_loads_docx_via_docx2txt(self):
        path = _tmp(".docx", b"PK\x03\x04 fake zip")  # content irrelevant — loader is patched
        with patch("docx2txt.process", return_value="Extracted DOCX text") as mock_proc:
            docs = load_documents(path, ".docx")
        mock_proc.assert_called_once()
        assert docs[0].page_content == "Extracted DOCX text"

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError):
            load_documents("whatever", ".exe")


class TestUrlFormatValidation:
    def test_accepts_supported_url_formats(self):
        from schemas.ingest import IngestRequest

        for url in [
            "https://b.s3.amazonaws.com/p.pdf",
            "https://b.s3.amazonaws.com/p.docx",
            "https://b.s3.amazonaws.com/p.html",
            "https://b.s3.amazonaws.com/notes.md",
        ]:
            req = IngestRequest(file_name="doc", s3_url=url)
            assert str(req.s3_url).startswith("https://")

    def test_rejects_unsupported_url_format(self):
        from pydantic import ValidationError

        from schemas.ingest import IngestRequest

        with pytest.raises(ValidationError):
            IngestRequest(file_name="doc", s3_url="https://b.s3.amazonaws.com/malware.exe")
