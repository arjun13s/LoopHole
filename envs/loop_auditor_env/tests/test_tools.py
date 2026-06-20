import json
from pathlib import Path

import pytest

from loop_auditor_env.tools import get_iteration, get_step, get_trace_summary


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_get_trace_summary_returns_summary():
    trace = load_fixture("clean_trace.json")

    summary = get_trace_summary(trace)

    assert "clean-trace-001" in summary
    assert "iter0.step0.read-avatar" in summary


def test_get_iteration_found():
    trace = load_fixture("clean_trace.json")

    iteration = get_iteration(trace, 1)

    assert iteration["index"] == 1


def test_get_iteration_out_of_range():
    trace = load_fixture("clean_trace.json")

    with pytest.raises(IndexError):
        get_iteration(trace, 99)


def test_get_step_found():
    trace = load_fixture("buggy_routing.json")

    step = get_step(trace, "iter0.step1.edit-admin-route")

    assert step["action_type"] == "tool_call"


def test_get_step_missing_id():
    trace = load_fixture("buggy_routing.json")

    with pytest.raises(KeyError):
        get_step(trace, "missing.step")

