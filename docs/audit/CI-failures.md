6s
Run pytest --cov=. --cov-fail-under=95 --cov-report=xml --cov-report=term-missing -v
============================= test session starts ==============================
platform linux -- Python 3.10.20, pytest-9.0.3, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.10.20/x64/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/chat-bot/chat-bot
configfile: pyproject.toml
testpaths: tests
plugins: langsmith-0.8.11, cov-7.1.0, anyio-4.13.0
collecting ... collected 309 items / 1 error

==================================== ERRORS ====================================
_________________ ERROR collecting tests/test_odl_preflight.py _________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_preflight.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_preflight.py:6: in <module>
    from hypothesis import assume, given, strategies as st
E   ModuleNotFoundError: No module named 'hypothesis'
=============================== warnings summary ===============================
../../../../../opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/fastapi/testclient.py:1
  /opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR tests/test_odl_preflight.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
========================= 1 warning, 1 error in 1.97s ==========================
Error: Process completed with exit code 2.

---
Run bandit -r . -ll -ii -x ./tests/
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: None
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	running on Python 3.10.20
Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:01
Run started:2026-06-09 13:26:24.947870+00:00

Test results:
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: ./opendataloader-pdf/python/opendataloader-pdf/src/opendataloader_pdf/hybrid_server.py:84:15
83	# Configuration
84	DEFAULT_HOST = "0.0.0.0"
85	DEFAULT_PORT = 5002

--------------------------------------------------
>> Issue: [B104:hardcoded_bind_all_interfaces] Possible binding to all interfaces.
   Severity: Medium   Confidence: Medium
   CWE: CWE-605 (https://cwe.mitre.org/data/definitions/605.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b104_hardcoded_bind_all_interfaces.html
   Location: ./opendataloader-pdf/scripts/experiments/docling_fastapi_bench.py:108:26
107	
108	    uvicorn.run(app, host="0.0.0.0", port=FASTAPI_PORT, log_level="warning")
109	

--------------------------------------------------

Code scanned:
	Total lines of code: 8508
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 0

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 218
		Medium: 2
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 2
		High: 218
Files skipped (0):
Error: Process completed with exit code 1.

---

Run ruff check .
I001 [*] Import block is un-sorted or un-formatted
  --> opendataloader-pdf/build-scripts/fetch_shaded_jar.py:8:1
   |
 6 |   """
 7 |
 8 | / import argparse
 9 | | import logging
10 | | import re
11 | | import shutil
12 | | import sys
13 | | from pathlib import Path
14 | | from typing import Optional
15 | |
16 | | # Requires 'packaging' library (pip install packaging)
17 | | from packaging.version import parse as parse_version
   | |____________________________________________________^
18 |
19 |   def find_latest_jar_by_semver(target_dir: Path) -> Optional[Path]:
   |
help: Organize imports

UP045 [*] Use `X | None` for type annotations
  --> opendataloader-pdf/build-scripts/fetch_shaded_jar.py:19:52
   |
17 | from packaging.version import parse as parse_version
18 |
19 | def find_latest_jar_by_semver(target_dir: Path) -> Optional[Path]:
   |                                                    ^^^^^^^^^^^^^^
20 |     """Finds the shaded JAR with the highest semantic version in its filename."""
   |
help: Convert to `X | None`

E501 Line too long (122 > 120)
  --> opendataloader-pdf/build-scripts/fetch_shaded_jar.py:57:121
   |
55 |     parser = argparse.ArgumentParser(description="Copies the latest shaded JAR to the Python source tree.")
56 |     parser.add_argument("java_target_dir", type=Path, help="Path to the Java module's 'target' directory.")
57 |     parser.add_argument("python_jars_dir", type=Path, help="Path to the Python package's destination directory for JARs.")
534 |     if pages is None:
535 |         return True
    |
help: Convert to `X | None`

I001 [*] Import block is un-sorted or un-formatted
  --> tests/test_odl_preflight.py:3:1
   |
 1 |   """Tests for OpenDataLoader preflight checks, config validation, and PDF loader dispatch."""
 2 |
 3 | / from unittest.mock import MagicMock, patch
 4 | |
 5 | | import pytest
 6 | | from hypothesis import assume, given, strategies as st
 7 | |
 8 | | from config import Settings, get_settings
 9 | | from ingest.loaders import load_documents
10 | | from ingest.pdf_preflight import (
11 | |     _hybrid_reachable,
12 | |     _java_available,
13 | |     _odl_importable,
14 | |     _parse_java_version,
15 | |     preflight_check,
16 | | )
   | |_^
17 |
18 |   # ───────────────────────────────
   |
help: Organize imports

F401 [*] `hypothesis.assume` imported but unused
 --> tests/test_odl_preflight.py:6:24
  |
5 | import pytest
6 | from hypothesis import assume, given, strategies as st
  |                        ^^^^^^
7 |
8 | from config import Settings, get_settings
  |
help: Remove unused import: `hypothesis.assume`

F401 [*] `config.get_settings` imported but unused
  --> tests/test_odl_preflight.py:8:30
   |
 6 | from hypothesis import assume, given, strategies as st
 7 |
 8 | from config import Settings, get_settings
   |                              ^^^^^^^^^^^^
 9 | from ingest.loaders import load_documents
10 | from ingest.pdf_preflight import (
   |
help: Remove unused import: `config.get_settings`

Found 101 errors.
[*] 42 fixable with the `--fix` option (2 hidden fixes can be enabled with the `--unsafe-fixes` option).
Error: Process completed with exit code 1.
