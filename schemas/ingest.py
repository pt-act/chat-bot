import re

from pydantic import BaseModel, HttpUrl, field_validator

from ingest.loaders import SUPPORTED_EXTENSIONS, detect_extension, is_supported

_MAX_NAME_LEN = 128


def clean_file_name(v: str) -> str:
    """Strict doc-id validation (shared by the URL ingest request).

    Rejects empty names, path separators, and dots so the value is safe to use as a
    Redis key segment and a doc id. Raises ``ValueError`` on rejection.
    """
    v = v.strip()
    if not v:
        raise ValueError("file_name cannot be empty")
    if re.search(r"[/\\.]", v):
        raise ValueError("file_name must not contain path separators or dots")
    if len(v) > _MAX_NAME_LEN:
        raise ValueError(f"file_name too long (max {_MAX_NAME_LEN} characters)")
    return v


def sanitize_doc_id(raw: str) -> str:
    """Derive a safe doc id from an uploaded filename (lenient, never raises).

    Drops the directory and a trailing supported extension, keeps ``[A-Za-z0-9_-]``,
    replaces any other run with ``_``, and truncates. Falls back to ``document``.
    """
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]  # strip any directory component
    ext = detect_extension(base)
    if ext in SUPPORTED_EXTENSIONS:
        base = base[: -len(ext)]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    slug = slug[:_MAX_NAME_LEN].strip("_")
    return slug or "document"


class IngestRequest(BaseModel):
    file_name: str
    s3_url: HttpUrl

    @field_validator("s3_url")
    @classmethod
    def must_be_supported(cls, v: HttpUrl) -> HttpUrl:
        if not is_supported(str(v)):
            allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise ValueError(f"URL must point to a supported document ({allowed})")
        return v

    @field_validator("file_name")
    @classmethod
    def safe_file_name(cls, v: str) -> str:
        return clean_file_name(v)
