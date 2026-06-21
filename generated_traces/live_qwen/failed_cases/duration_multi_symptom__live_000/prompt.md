Repository root is the current working directory. Task:
Fix the duration parser. Two tests fail, but they share one upstream root cause. Inspect both failures before patching, make one local fix, rerun tests, then submit.

Files available:
- repo/README.md
- repo/src/durations.py
- repo/src/formatting.py
- repo/tests/test_durations.py

Use `pytest -q` for tests. If you submit, include exactly one of:
["repo/src/durations.py"]

Keep scope narrow. Expected repo size is small; prefer targeted reads.
