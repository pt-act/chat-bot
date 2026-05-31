from ingest.policies import process_policy, process_uploaded


def ingest_file(file_name: str, s3_url: str):
    # You can add preprocessing / validation here

    result = process_policy(file_name, s3_url)

    return result


def ingest_local_file(file_name: str, file_path: str, ext: str):
    """Ingest a locally-saved (uploaded) document. `file_path` is removed when done."""
    return process_uploaded(file_name, file_path, ext)
