"""Deterministic fake coding agent for the supervision demo.

Attempt 1 always edits the wrong file. On attempt 2, it only fixes the right
file if the supervisor-provided hint mentions src/duration.py / parse_duration.
"""

from __future__ import annotations

import os
from pathlib import Path


FIXED_DURATION = '''import re


def parse_duration(text):
    total = 0
    pos = 0
    for match in re.finditer(r"(\\d+)([hms])", text):
        if match.start() != pos:
            raise ValueError(f"invalid duration: {text}")
        value = int(match.group(1))
        unit = match.group(2)
        total += value * {"h": 3600, "m": 60, "s": 1}[unit]
        pos = match.end()
    if pos != len(text) or pos == 0:
        raise ValueError(f"invalid duration: {text}")
    return total
'''


def main() -> None:
    repo = Path(os.environ["LOOP_AUDITOR_REPO"])
    attempt = int(os.environ["LOOP_AUDITOR_ATTEMPT"])
    hint_path = Path(os.environ["LOOP_AUDITOR_HINT_FILE"])
    hint = hint_path.read_text() if hint_path.exists() else ""

    print(f"fake coding agent attempt={attempt}")
    if attempt == 1:
        target = repo / "src" / "date_utils.py"
        target.write_text(
            "def normalize_date(value):\n"
            "    # Tried to handle duration-ish strings here, but tests do not call this.\n"
            "    return value.strip().lower()\n"
        )
        print("edited src/date_utils.py based on the word 'duration' looking date-like")
        print("will rely on supervisor/test loop for feedback")
        return

    if "External evaluator diagnosis" in hint and (
        "src/duration.py" in hint or "parse_duration" in hint
    ):
        (repo / "src" / "duration.py").write_text(FIXED_DURATION)
        print("used evaluator hint; edited src/duration.py::parse_duration")
        return

    target = repo / "src" / "date_utils.py"
    target.write_text(
        target.read_text()
        + "\n\ndef parse_duration_note(value):\n"
        "    return 'still the wrong file'\n"
    )
    print("self-prompt retry stayed in src/date_utils.py and missed the failing function")


if __name__ == "__main__":
    main()
