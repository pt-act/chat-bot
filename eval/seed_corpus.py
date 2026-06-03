#!/usr/bin/env python
"""Seed a Chroma collection for the eval harness (#19 — opt-in eval CI).

`eval/run_ragas.py --mode live` retrieves from the configured Chroma collection, so the
collection must be populated first. This helper ingests every supported document under a
corpus directory (default ``eval/corpus/``) through the real ingest pipeline. If that
directory is missing or empty, it falls back to a small built-in policy so the scheduled
eval workflow always has something to retrieve against.

Usage:
    EVAL_CORPUS_DIR=eval/corpus uv run --with-requirements requirements.txt eval/seed_corpus.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Seeding only needs Redis + ChromaDB, not an LLM. Default to providers that
# work without API keys so the script succeeds in CI where no secrets are set.
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("EMBEDDING_PROVIDER", "fastembed")
os.environ.setdefault("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

_DEFAULT_POLICY = """\
Return Policy
Customers may return any item within 30 days of purchase for a full refund. Returns require
prior authorization and the original order number. Items must be unused and in their original
packaging.

Refund Policy
Refunds are processed within 5 to 7 business days after the returned item is received, to the
original payment method only. Shipping fees are non-refundable unless the return is due to our error.

Shipping Policy
Standard shipping takes 5 to 7 business days. Express shipping delivers within 2 to 3 business
days for an additional fee. International orders may take 10 to 20 business days.

Exchange Policy
Items may be exchanged within 14 days of purchase with the original receipt, subject to availability.

Warranty
Products include a twelve month manufacturer warranty against defects.

Privacy and Data Policy
We collect personal data only to process your order. Your data is never sold to third parties,
and you may request deletion of your data at any time.
"""


def main() -> int:
    from ingest.loaders import SUPPORTED_EXTENSIONS, detect_extension
    from ingest.policies import process_uploaded

    corpus = Path(os.environ.get("EVAL_CORPUS_DIR", ROOT / "eval" / "corpus"))
    files: list[Path] = []
    if corpus.is_dir():
        files = [p for p in sorted(corpus.iterdir()) if detect_extension(p.name) in SUPPORTED_EXTENSIONS]

    if not files:
        tmp_dir = Path(tempfile.mkdtemp())
        default = tmp_dir / "policy.md"
        default.write_text(_DEFAULT_POLICY, encoding="utf-8")
        files = [default]
        print("No corpus files found; seeding the built-in default policy.")

    for f in files:
        ext = detect_extension(f.name)
        doc_id = f.stem.replace(" ", "_").lower()
        # process_uploaded deletes the file it is given, so copy to a throwaway temp first.
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.close()
        shutil.copy(f, tmp.name)
        result = process_uploaded(doc_id, tmp.name, ext)
        print(f"  seeded {doc_id}: {result.get('status')} (chunks={result.get('total')})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
