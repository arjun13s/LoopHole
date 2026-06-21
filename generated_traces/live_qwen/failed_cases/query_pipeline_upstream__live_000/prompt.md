Repository root is the current working directory. Task:
Fix the query rendering pipeline. A final output test fails, but the root cause is upstream in tokenization/parsing. Trace the failure back, patch the right component, rerun tests, then submit.

Files available:
- repo/README.md
- repo/src/formatter.py
- repo/src/parser.py
- repo/src/tokenizer.py
- repo/tests/test_query_pipeline.py

Use `pytest -q` for tests. If you submit, include exactly one of:
["repo/src/tokenizer.py"]

Keep scope narrow. Expected repo size is small; prefer targeted reads.
