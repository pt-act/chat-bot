"""Group 11 docs link check (11.5).

Verifies that code references in README.md, PTD.md, and docs/odl-operator-guide.md
point to files that actually exist in the repository.

11.6 + 11.7: operator guide security warnings verified by content inspection.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_README = _ROOT / "README.md"
_PTD = _ROOT / "PTD.md"
_OPERATOR_GUIDE = _ROOT / "docs" / "odl-operator-guide.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# File extensions that we consider authoritative project references.
_CODE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".yml", ".yaml", ".json", ".md", ".sh",
})

# Only check references that begin with one of these known project directories.
# This avoids false positives from legacy audit paths and external examples.
_CHECKED_PREFIXES = (
    "ingest/", "graph/", "schemas/", "utils/", "docs/",
    "eval/", "tests/", "web/", "controllers/", "services/",
    "config.py", "main.py",
)


def _extract_file_refs(text: str) -> list[str]:
    """Extract file-path references from Markdown backtick spans.

    Only considers references that:
    - End in a recognised project extension (.py, .ts, .tsx, .yml, .json, .md)
    - Contain a `/` separator (so they look like module paths, not lone filenames)
    - Do not match method/attribute dot notation (e.g. `module.function`)

    Returns de-duplicated list.
    """
    # Backtick-quoted strings only: `ingest/policies.py`
    candidates = re.findall(r'`([a-zA-Z0-9_./-]+)`', text)
    seen: set[str] = set()
    result = []
    for c in candidates:
        # Must contain a slash to look like a path, not just a symbol
        if "/" not in c:
            continue
        # Must end with a recognised project extension
        ext = "." + c.rsplit(".", 1)[-1] if "." in c else ""
        if ext not in _CODE_EXTENSIONS:
            continue
        # Skip URL paths and external references
        if c.startswith("http") or c.startswith("/") or ".." in c:
            continue
        # Only check references in known project directories
        if not any(c.startswith(prefix) for prefix in _CHECKED_PREFIXES):
            continue
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _exists_in_repo(ref: str) -> bool:
    """Return True when the reference resolves to an existing file under _ROOT."""
    return (_ROOT / ref).exists()


# ---------------------------------------------------------------------------
# 11.5  Docs link check
# ---------------------------------------------------------------------------

class TestDocsLinkCheck:
    def _check_doc(self, doc_path: Path) -> list[str]:
        """Return a list of broken references found in the given Markdown file."""
        text = doc_path.read_text(encoding="utf-8")
        refs = _extract_file_refs(text)
        broken = []
        for ref in refs:
            # Skip external links and known-safe patterns
            if ref.startswith("http") or "example.com" in ref:
                continue
            # Only check paths that look like relative file references
            if "/" not in ref and not ref.startswith("ingest") and not ref.startswith("graph"):
                # Single-segment references are often not file paths (e.g. "text.md" as text)
                if not (_ROOT / ref).exists():
                    continue  # benign — not a path reference
            if not _exists_in_repo(ref):
                broken.append(ref)
        return broken

    def test_readme_file_refs_exist(self):
        """All file references in README.md point to existing files."""
        broken = self._check_doc(_README)
        assert broken == [], (
            f"README.md contains references to non-existent files: {broken}"
        )

    def test_ptd_file_refs_exist(self):
        """All file references in PTD.md point to existing files."""
        broken = self._check_doc(_PTD)
        assert broken == [], (
            f"PTD.md contains references to non-existent files: {broken}"
        )

    def test_operator_guide_exists(self):
        """docs/odl-operator-guide.md is present."""
        assert _OPERATOR_GUIDE.exists(), (
            "docs/odl-operator-guide.md not found"
        )

    def test_operator_guide_file_refs_exist(self):
        """All file references in the operator guide point to existing files."""
        broken = self._check_doc(_OPERATOR_GUIDE)
        assert broken == [], (
            f"docs/odl-operator-guide.md contains references to non-existent files: {broken}"
        )

    def test_odl_components_in_ptd(self):
        """PTD.md documents the two new ODL modules."""
        ptd = _PTD.read_text(encoding="utf-8")
        assert "pdf_opendataloader.py" in ptd, "PTD.md missing pdf_opendataloader.py"
        assert "pdf_preflight.py" in ptd, "PTD.md missing pdf_preflight.py"

    def test_odl_config_vars_in_ptd(self):
        """PTD.md configuration table includes ODL env vars."""
        ptd = _PTD.read_text(encoding="utf-8")
        assert "ODL_FORMAT" in ptd, "PTD.md missing ODL_FORMAT in config table"
        assert "ODL_HYBRID" in ptd, "PTD.md missing ODL_HYBRID in config table"
        assert "hierarchical" in ptd, "PTD.md missing 'hierarchical' retrieval strategy"

    def test_odl_l1_l2_in_ptd_storage(self):
        """PTD.md storage model section documents L1/L2 chunk metadata."""
        ptd = _PTD.read_text(encoding="utf-8")
        assert "chunk_level" in ptd, "PTD.md missing chunk_level in storage model"
        assert "section_title" in ptd, "PTD.md missing section_title in storage model"
        assert "parent_chunk_id" in ptd, "PTD.md missing parent_chunk_id in storage model"

    def test_readme_java_requirement(self):
        """README.md documents the Java 11+ requirement."""
        readme = _README.read_text(encoding="utf-8")
        assert "Java 11" in readme or "java-11" in readme.lower() or "java 11" in readme.lower()

    def test_readme_hybrid_mode_docs(self):
        """README.md documents hybrid mode setup."""
        readme = _README.read_text(encoding="utf-8")
        assert "ODL_HYBRID" in readme
        assert "odl-hybrid" in readme or "odl_hybrid" in readme.lower()

    def test_changelog_odl_entry(self):
        """CHANGELOG.md has an entry for the ODL Full Leverage work."""
        changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "OpenDataLoader" in changelog or "ODL" in changelog


# ---------------------------------------------------------------------------
# 11.6  Security warning: operator guide warns about external port exposure
# ---------------------------------------------------------------------------

class TestOperatorGuideSecurity:
    def test_warns_against_external_port(self):
        """11.6: operator guide explicitly warns against exposing odl-hybrid port."""
        guide = _OPERATOR_GUIDE.read_text(encoding="utf-8")
        assert "external" in guide.lower() and ("port" in guide.lower() or "expose" in guide.lower()), (
            "Operator guide must warn against exposing odl-hybrid port externally"
        )

    def test_warns_about_hybrid_url_trust(self):
        """11.7: operator guide warns ODL_HYBRID_URL must point to a trusted host."""
        guide = _OPERATOR_GUIDE.read_text(encoding="utf-8")
        assert "trusted" in guide.lower() or "untrusted" in guide.lower(), (
            "Operator guide must note ODL_HYBRID_URL should point to a trusted host"
        )

    def test_warns_about_internal_network(self):
        """Operator guide notes sidecar is internal-only."""
        guide = _OPERATOR_GUIDE.read_text(encoding="utf-8")
        assert "internal" in guide.lower(), (
            "Operator guide must state that odl-hybrid is on the internal network"
        )

    def test_http_https_scheme_validation_documented(self):
        """Operator guide mentions URL scheme validation."""
        guide = _OPERATOR_GUIDE.read_text(encoding="utf-8")
        assert "http://" in guide or "https://" in guide, (
            "Operator guide must document the expected URL scheme for ODL_HYBRID_URL"
        )
