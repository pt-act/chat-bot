Run pytest --cov=. --cov-fail-under=95 --cov-report=xml --cov-report=term-missing -v
============================= test session starts ==============================
platform linux -- Python 3.10.20, pytest-9.0.3, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.10.20/x64/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/chat-bot/chat-bot
configfile: pyproject.toml
testpaths: tests
plugins: langsmith-0.8.11, cov-7.1.0, anyio-4.13.0
collecting ... collected 441 items / 5 errors

==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_odl_adapter.py __________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_adapter.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_adapter.py:17: in <module>
    from hypothesis import given, settings as h_settings
E   ModuleNotFoundError: No module named 'hypothesis'
_______________ ERROR collecting tests/test_odl_hierarchical.py ________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_hierarchical.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_hierarchical.py:18: in <module>
    from hypothesis import given, settings as h_settings
E   ModuleNotFoundError: No module named 'hypothesis'
_________________ ERROR collecting tests/test_odl_preflight.py _________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_preflight.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_preflight.py:6: in <module>
    from hypothesis import assume, given, strategies as st
E   ModuleNotFoundError: No module named 'hypothesis'
_________________ ERROR collecting tests/test_odl_retrieval.py _________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_retrieval.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_retrieval.py:18: in <module>
    from hypothesis import given, settings as h_settings
E   ModuleNotFoundError: No module named 'hypothesis'
__________________ ERROR collecting tests/test_odl_walker.py ___________________
ImportError while importing test module '/home/runner/work/chat-bot/chat-bot/tests/test_odl_walker.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_odl_walker.py:15: in <module>
    from hypothesis import given, settings as h_settings
E   ModuleNotFoundError: No module named 'hypothesis'
=============================== warnings summary ===============================
../../../../../opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/fastapi/testclient.py:1
  /opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR tests/test_odl_adapter.py
ERROR tests/test_odl_hierarchical.py
ERROR tests/test_odl_preflight.py
ERROR tests/test_odl_retrieval.py
ERROR tests/test_odl_walker.py
!!!!!!!!!!!!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!!!!!!!!!!!!!
========================= 1 warning, 5 errors in 2.51s =========================
Error: Process completed with exit code 2.

---

1s
Run bandit -r . -ll -ii -x ./tests/
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: None
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	running on Python 3.10.20
Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:01
Run started:2026-06-09 15:56:23.349498+00:00

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
	Total lines of code: 9357
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

1s
Run ruff check .
E402 Module level import not at top of file
  --> eval/pdf_comparison.py:29:1
   |
27 |     sys.path.insert(0, str(_ROOT))
28 |
29 | from langchain_core.documents import Document
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
30 | from langchain_text_splitters import RecursiveCharacterTextSplitter
   |

E402 Module level import not at top of file
  --> eval/pdf_comparison.py:30:1
   |
29 | from langchain_core.documents import Document
30 | from langchain_text_splitters import RecursiveCharacterTextSplitter
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
31 |
32 | from ingest.pdf_opendataloader import build_hierarchical_chunks, merge_tables, walk_tree
   |

E402 Module level import not at top of file
  --> eval/pdf_comparison.py:32:1
   |
30 | from langchain_text_splitters import RecursiveCharacterTextSplitter
31 |
32 | from ingest.pdf_opendataloader import build_hierarchical_chunks, merge_tables, walk_tree
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
33 |
34 | _FIXTURES = _ROOT / "tests" / "fixtures"
   |

F401 [*] `dataclasses.field` imported but unused
  --> ingest/pdf_opendataloader.py:24:36
   |
22 | import shutil
23 | import tempfile
24 | from dataclasses import dataclass, field
   |                                    ^^^^^
31 | …g level": level, "page number": page, "bounding box": [0.0, 0.0, 100.0, 20.0]}
   |                                                        ^^^^^^^^^^^^^^^^^^^^^^^^
   |

E501 Line too long (123 > 120)
  --> tests/test_odl_walker.py:35:121
   |
34 | def _paragraph(id_: int, text: str, page: int = 1) -> dict:
35 |     return {"type": "paragraph", "id": id_, "content": text, "page number": page, "bounding box": [0.0, 25.0, 100.0, 40.0]}
   |                                                                                                                         ^^^
   |

F841 Local variable `t1` is assigned to but never used
   --> tests/test_odl_walker.py:225:9
    |
224 |     def test_independent_tables_unchanged(self):
225 |         t1 = _table(1, [["A"]], page=1)
    |         ^^
226 |         t2 = _table(2, [["B"]], page=2)
227 |         elements = [
    |
help: Remove assignment to unused variable `t1`

F841 Local variable `t2` is assigned to but never used
   --> tests/test_odl_walker.py:226:9
    |
224 |     def test_independent_tables_unchanged(self):
225 |         t1 = _table(1, [["A"]], page=1)
226 |         t2 = _table(2, [["B"]], page=2)
    |         ^^
227 |         elements = [
228 |             OdlElement(id_=1, page_number=1, element_type="table", content="A"),
    |
help: Remove assignment to unused variable `t2`

F841 Local variable `chain_start_id` is assigned to but never used
   --> tests/test_odl_walker.py:364:9
    |
363 |     for c in range(m_chains):
364 |         chain_start_id = id_counter
    |         ^^^^^^^^^^^^^^
365 |         for i in range(chain_len):
366 |             tid = id_counter
    |
help: Remove assignment to unused variable `chain_start_id`

Found 189 errors.
[*] 98 fixable with the `--fix` option (6 hidden fixes can be enabled with the `--unsafe-fixes` option).
Error: Process completed with exit code 1.
