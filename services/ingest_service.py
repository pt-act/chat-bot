from ingest.policies import process_policy, process_uploaded


def ingest_file(
    file_name: str,
    s3_url: str,
    parser: str | None = None,
    hybrid_mode: str | None = None,
    pages: str | None = None,
):
    return process_policy(
        file_name, s3_url,
        parser_override=parser,
        hybrid_mode_override=hybrid_mode,
        pages_override=pages,
    )


def ingest_local_file(
    file_name: str,
    file_path: str,
    ext: str,
    parser: str | None = None,
    hybrid_mode: str | None = None,
    pages: str | None = None,
):
    """Ingest a locally-saved (uploaded) document. `file_path` is removed when done."""
    return process_uploaded(
        file_name, file_path, ext,
        parser_override=parser,
        hybrid_mode_override=hybrid_mode,
        pages_override=pages,
    )
