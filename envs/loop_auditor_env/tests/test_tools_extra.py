# envs/loop_auditor_env/tests/test_tools_extra.py
import json
from pathlib import Path

from loop_auditor_env import config
from loop_auditor_env.tools import (
    get_errors,
    get_reference_solution,
    get_step_io,
    search_steps,
)


def _trace():
    p = sorted((config.FIXTURES_DIR).glob("buggy_routing*.json"))[0]
    return json.loads(Path(p).read_text())


def test_search_steps_matches_tool_and_io_case_insensitive():
    t = _trace()
    hits = search_steps(t, "ADMIN")  # appears in input/output of the planted step
    assert any(s["step_id"] == "iter0.step1.edit-admin-route" for s in hits)


def test_search_steps_no_match_returns_empty():
    assert search_steps(_trace(), "zzzzz-nope") == []


def test_get_errors_filters_status():
    t = {"iterations": [{"index": 0, "steps": [
        {"step_id": "a", "action_type": "tool_call", "status": "ok"},
        {"step_id": "b", "action_type": "tool_call", "status": "error"},
        {"step_id": "c", "action_type": "tool_call", "status": "timeout"},
    ]}]}
    ids = [s["step_id"] for s in get_errors(t)]
    assert ids == ["b", "c"]


def test_get_step_io_returns_untruncated():
    t = _trace()
    io = get_step_io(t, "iter0.step1.edit-admin-route")
    assert io["step_id"] == "iter0.step1.edit-admin-route"
    assert "admin" in str(io["output"]).lower()


def test_get_reference_solution_absent_is_none():
    assert get_reference_solution(_trace()) is None


def test_get_reference_solution_present():
    assert get_reference_solution({"reference_solution": "edit customer checkout"}) == "edit customer checkout"
