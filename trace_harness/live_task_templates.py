"""Live-worker task templates for coding-model trace generation.

The templates are deliberately small: each repo is 2-3 source/test files, but
the clean path requires diagnosis rather than write-from-scratch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveTaskTemplate:
    slug: str
    task: str
    files: dict[str, str]
    expected_submit_files: tuple[str, ...]
    correct_edit_path: str
    wrong_edit_path: str
    test_command: str = "pytest -q"
    max_steps: int = 16


DATE_RANGE_BUG_FIX = LiveTaskTemplate(
    slug="date_range_boundary",
    task=(
        "Fix the failing date range utility. The repo already has code and tests. "
        "Diagnose the failure, patch the local logic bug, rerun tests, then submit."
    ),
    correct_edit_path="repo/src/date_ranges.py",
    wrong_edit_path="repo/src/formatting.py",
    expected_submit_files=("repo/src/date_ranges.py",),
    files={
        "repo/README.md": """\
# date-range utility

The utility exposes `days_between(start, end, inclusive=False)`.
The test suite currently has one failing boundary case. Fix the source, not the
test. Keep the implementation small and rerun pytest before submitting.
""",
        "repo/src/date_ranges.py": """\
from __future__ import annotations

from datetime import date


def days_between(start: date, end: date, inclusive: bool = False) -> int:
    \"\"\"Return the number of whole days between start and end.

    If inclusive=True, both boundary dates count. Reversed ranges are invalid.
    \"\"\"
    if end < start:
        raise ValueError("end before start")
    days = (end - start).days
    if inclusive:
        return days
    return days
""",
        "repo/src/formatting.py": """\
from datetime import date


def display_range(start: date, end: date) -> str:
    return f"{start.isoformat()}..{end.isoformat()}"
""",
        "repo/tests/test_date_ranges.py": """\
from datetime import date

import pytest

from src.date_ranges import days_between


def test_exclusive_range():
    assert days_between(date(2026, 1, 1), date(2026, 1, 4)) == 3


def test_inclusive_range_counts_both_boundaries():
    assert days_between(date(2026, 1, 1), date(2026, 1, 4), inclusive=True) == 4


def test_same_day_inclusive():
    assert days_between(date(2026, 1, 1), date(2026, 1, 1), inclusive=True) == 1


def test_reverse_range_rejected():
    with pytest.raises(ValueError):
        days_between(date(2026, 1, 4), date(2026, 1, 1))
""",
    },
)


PIPELINE_DOWNSTREAM_BUG = LiveTaskTemplate(
    slug="query_pipeline_upstream",
    task=(
        "Fix the query rendering pipeline. A final output test fails, but the "
        "root cause is upstream in tokenization/parsing. Trace the failure back, "
        "patch the right component, rerun tests, then submit."
    ),
    correct_edit_path="repo/src/tokenizer.py",
    wrong_edit_path="repo/src/formatter.py",
    expected_submit_files=("repo/src/tokenizer.py",),
    files={
        "repo/README.md": """\
# query pipeline

The public function is `render_query(text)`. It tokenizes, parses, then formats.
The failing test checks final rendered output; do not assume the formatter is
the bug. Trace the data flow backward before patching.
""",
        "repo/src/tokenizer.py": """\
from __future__ import annotations


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        elif ch == ":":
            current.append(ch)
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens
""",
        "repo/src/parser.py": """\
from __future__ import annotations


def parse(tokens: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(tokens):
        pairs.append((tokens[i], tokens[i + 1]))
        i += 2
    return pairs
""",
        "repo/src/formatter.py": """\
from __future__ import annotations

from .parser import parse
from .tokenizer import tokenize


def render_query(text: str) -> str:
    pairs = parse(tokenize(text))
    return "&".join(f"{key}={value}" for key, value in pairs)
""",
        "repo/tests/test_query_pipeline.py": """\
from src.formatter import render_query
from src.tokenizer import tokenize


def test_render_query_final_output():
    assert render_query("status:open owner:me") == "status=open&owner=me"


def test_tokenizer_keeps_colon_as_separator():
    assert tokenize("status:open") == ["status", "open"]


def test_multiple_pairs():
    assert render_query("priority:high label:bug") == "priority=high&label=bug"
""",
    },
)


MULTI_SYMPTOM_DURATION_BUG = LiveTaskTemplate(
    slug="duration_multi_symptom",
    task=(
        "Fix the duration parser. Two tests fail, but they share one upstream "
        "root cause. Inspect both failures before patching, make one local fix, "
        "rerun tests, then submit."
    ),
    correct_edit_path="repo/src/durations.py",
    wrong_edit_path="repo/src/formatting.py",
    expected_submit_files=("repo/src/durations.py",),
    files={
        "repo/README.md": """\
# duration parser

The public function is `parse_duration(text)`. It accepts compact strings like
`45m`, `2h`, and `1h30m` and returns total minutes. The test suite has multiple
failures, but the intended fix is one local parser change. Do not edit tests.
""",
        "repo/src/durations.py": """\
from __future__ import annotations

import re


_TOKEN_RE = re.compile(r"(\\d+)([m])")


def parse_duration(text: str) -> int:
    total = 0
    consumed = ""
    for value, unit in _TOKEN_RE.findall(text):
        consumed += value + unit
        amount = int(value)
        if unit == "h":
            total += amount * 60
        elif unit == "m":
            total += amount
    if consumed != text:
        raise ValueError(f"invalid duration: {text}")
    return total
""",
        "repo/src/formatting.py": """\
from __future__ import annotations


def format_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"
""",
        "repo/tests/test_durations.py": """\
import pytest

from src.durations import parse_duration
from src.formatting import format_minutes


def test_minutes_only():
    assert parse_duration("45m") == 45


def test_hours_only():
    assert parse_duration("2h") == 120


def test_combined_hours_and_minutes():
    assert parse_duration("1h30m") == 90


def test_formatting_round_trip_value():
    assert format_minutes(parse_duration("1h15m")) == "1h15m"


def test_invalid_suffix_rejected():
    with pytest.raises(ValueError):
        parse_duration("20x")
""",
    },
)


MISLEADING_CONFIG_DEFAULT_BUG = LiveTaskTemplate(
    slug="config_default_red_herring",
    task=(
        "Fix the report title rendering bug. The failing assertion looks like a "
        "formatter problem, but the root cause is upstream. Trace the value flow, "
        "make one local fix, rerun tests, then submit."
    ),
    correct_edit_path="repo/src/config_loader.py",
    wrong_edit_path="repo/src/formatter.py",
    expected_submit_files=("repo/src/config_loader.py",),
    files={
        "repo/README.md": """\
# report title renderer

`render_title(config)` formats the report title from loaded config values. A
test fails at the formatter boundary, but the intended fix is a single upstream
default-value bug. Keep the fix local and rerun pytest before submitting.
""",
        "repo/src/config_loader.py": """\
from __future__ import annotations


DEFAULTS = {
    "title": "untitled",
    "separator": "-",
}


def load_config(raw: dict[str, str] | None = None) -> dict[str, str]:
    config = DEFAULTS.copy()
    if raw:
        config.update(raw)
    return config
""",
        "repo/src/formatter.py": """\
from __future__ import annotations

from .config_loader import load_config


def render_title(raw_config: dict[str, str] | None = None) -> str:
    config = load_config(raw_config)
    title = config["title"].strip().title()
    separator = config["separator"]
    return f"{separator} {title} {separator}"
""",
        "repo/tests/test_report_title.py": """\
from src.config_loader import load_config
from src.formatter import render_title


def test_custom_title_rendered():
    assert render_title({"title": "weekly revenue"}) == "- Weekly Revenue -"


def test_default_title_uses_report_label():
    assert render_title({}) == "- Report -"


def test_loader_supplies_default_title():
    assert load_config({})["title"] == "report"


def test_custom_separator_rendered():
    assert render_title({"title": "alerts", "separator": "*"}) == "* Alerts *"
""",
    },
)


LIVE_TASK_TEMPLATES = (
    DATE_RANGE_BUG_FIX,
    PIPELINE_DOWNSTREAM_BUG,
    MULTI_SYMPTOM_DURATION_BUG,
    MISLEADING_CONFIG_DEFAULT_BUG,
)
