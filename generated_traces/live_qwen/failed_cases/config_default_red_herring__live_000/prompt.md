Repository root is the current working directory. Task:
Fix the report title rendering bug. The failing assertion looks like a formatter problem, but the root cause is upstream. Trace the value flow, make one local fix, rerun tests, then submit.

Files available:
- repo/README.md
- repo/src/config_loader.py
- repo/src/formatter.py
- repo/tests/test_report_title.py

Use `pytest -q` for tests. If you submit, include exactly one of:
["repo/src/config_loader.py"]

Keep scope narrow. Expected repo size is small; prefer targeted reads.
