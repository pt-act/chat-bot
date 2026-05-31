"""Tests for the ingest path guard (_validate_ingest_path) — path-traversal defense.

Production ingest paths are always server-created temp/staged files; the guard resolves
symlinks and rejects anything that isn't a regular file inside an allowed base dir
(system temp or INGEST_INCOMING_DIR), notably a crafted path on the durable ingest queue.
"""

import os
import tempfile

import pytest

from ingest.policies import _validate_ingest_path


def test_real_temp_file_passes():
    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tmp.write(b"hi")
    tmp.close()
    try:
        assert _validate_ingest_path(tmp.name) == os.path.realpath(tmp.name)
    finally:
        os.remove(tmp.name)


def test_missing_file_rejected():
    with pytest.raises(ValueError, match="not a regular file"):
        _validate_ingest_path("/tmp/does-not-exist-3f9a2b.txt")


def test_path_outside_allowed_dirs_rejected():
    # A real file that exists but lives outside temp / the staged-upload dir.
    with pytest.raises(ValueError, match="outside the allowed"):
        _validate_ingest_path("/etc/passwd")


def test_symlink_escaping_temp_is_rejected(tmp_path):
    # A symlink inside an allowed dir that resolves to a sensitive file must be rejected.
    link = tmp_path / "evil_link"
    try:
        os.symlink("/etc/passwd", link)
    except OSError:  # pragma: no cover - environments without symlink support
        pytest.skip("symlinks unsupported here")
    with pytest.raises(ValueError, match="outside the allowed"):
        _validate_ingest_path(str(link))
