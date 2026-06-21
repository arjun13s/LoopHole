"""Deterministic process-fault injectors for synthetic traces."""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

from .trace_schema import GroundTruth, StructuredFix


def inject_resource_misuse(case: dict) -> tuple[dict, GroundTruth]:
    """Replace the focused failure inspection with an oversized context read."""
    mutated = deepcopy(case)
    trace = mutated["trace"]
    inspect_step_id = _meta(case, "inspect_step_id", "a003")
    failure_output_ref = _meta(case, "failure_output_ref", "test_outputs/a002.txt")
    large_context_path = _meta(case, "large_context_path", "repo/large_context.md")
    step = _step(trace, inspect_step_id)
    step["tool_name"] = "read_file"
    step["args"] = {"path": large_context_path}
    step["result"] = {
        "status": "ok",
        "exit_code": 0,
        "summary": "Loaded the full repo context instead of the focused failure output.",
    }
    step["summary"] = "Read an oversized repository dump before fixing the single failing test."
    step["tokens"] = 8200
    gt = GroundTruth(
        case_id="resource_misuse",
        fault_present=True,
        fault_step_id=inspect_step_id,
        failure_type="resource_misuse",
        fix=StructuredFix(
            action="replace",
            step_id=inspect_step_id,
            tool_name="read_file",
            target=failure_output_ref,
        ),
    )
    return mutated, gt


def inject_tool_misuse(case: dict) -> tuple[dict, GroundTruth]:
    """Recovered tool-result slip — labeled CLEAN (a hard negative, not a fault).

    The worker takes an early extra patch attempt, then inspects a helper, applies
    the verified fix, reruns tests green, and submits. By the auditor rubric a
    recovered misstep is healthy self-correction, so the honest label is CLEAN: a
    correct auditor must NOT flag it.

    Why this changed: the previous "tool_misuse" label was an unwinnable 0-trap.
    After rich_loader neutralizes per-step narration, the recovered trace is
    byte-identical to clean self-correction, so a rubric-following auditor calls
    it clean and is scored 0. A genuinely UNRECOVERED tool_misuse (e.g. submit
    with still-failing tests + variant-specific test_outputs) belongs in the
    richer taskset. Narration is kept benign here so the public transcript
    artifact can't mislead the auditor into flagging a clean trace.
    """
    mutated = deepcopy(case)
    trace = mutated["trace"]
    inspect_step_id = _meta(case, "inspect_step_id", "a003")
    correct_edit_path = _meta(case, "correct_edit_path", "repo/src/string_utils.py")
    step = _step(trace, inspect_step_id)
    step["tool_name"] = "write_file"
    step["args"] = {
        "path": correct_edit_path,
        "content_summary": "First patch attempt at the implementation.",
    }
    step["result"] = {
        "status": "ok",
        "exit_code": 0,
        "summary": "Wrote a first patch attempt.",
    }
    step["summary"] = "Took a first patch attempt before the verified fix."
    step["tokens"] = 360
    gt = GroundTruth(
        case_id="tool_misuse",
        fault_present=False,
        fault_step_id=None,
        failure_type=None,
        fix=None,
    )
    return mutated, gt


def inject_routing(case: dict) -> tuple[dict, GroundTruth]:
    """Remove the required passing test rerun before submit."""
    mutated = deepcopy(case)
    final_test_step_id = _meta(case, "final_test_step_id", "a005")
    submit_step_id = _meta(case, "submit_step_id", "a006")
    trace = [step for step in mutated["trace"] if step["step_id"] != final_test_step_id]
    mutated["trace"] = trace
    gt = GroundTruth(
        case_id="routing",
        fault_present=True,
        fault_step_id=submit_step_id,
        failure_type="routing",
        fix=StructuredFix(
            action="insert",
            step_id=submit_step_id,
            tool_name="run_tests",
            target=submit_step_id,
        ),
    )
    return mutated, gt


def inject_wrong_file_edit(case: dict) -> tuple[dict, GroundTruth]:
    """Point the real fix edit at a plausible sibling file."""
    mutated = deepcopy(case)
    trace = mutated["trace"]
    fix_step_id = _meta(case, "fix_step_id", "a004")
    wrong_edit_path = _meta(case, "wrong_edit_path", "repo/src/string_format.py")
    correct_edit_path = _meta(case, "correct_edit_path", "repo/src/string_utils.py")
    step = _step(trace, fix_step_id)
    step["args"]["path"] = wrong_edit_path
    step["result"]["summary"] = f"Wrote the fix into the sibling file {wrong_edit_path}."
    step["summary"] = "Applied the fix to the wrong file."
    _add_wrong_file_recovery(trace, fix_step_id, correct_edit_path)
    gt = GroundTruth(
        case_id="wrong_file_edit",
        fault_present=True,
        fault_step_id=fix_step_id,
        failure_type="wrong_file_edit",
        fix=StructuredFix(
            action="replace",
            step_id=fix_step_id,
            tool_name="write_file",
            target=correct_edit_path,
        ),
    )
    return mutated, gt


INJECTORS: dict[str, Callable[[dict], tuple[dict, GroundTruth]]] = {
    "resource_misuse": inject_resource_misuse,
    "tool_misuse": inject_tool_misuse,
    "routing": inject_routing,
    "wrong_file_edit": inject_wrong_file_edit,
}


def _step(trace: list[dict], step_id: str) -> dict:
    for step in trace:
        if step["step_id"] == step_id:
            return step
    raise ValueError(f"missing step: {step_id}")


def _meta(case: dict, key: str, default: str) -> str:
    value = case.get("metadata", {}).get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"case metadata {key} must be a non-empty string")
    return value


def _add_wrong_file_recovery(trace: list[dict], fix_step_id: str, correct_edit_path: str) -> None:
    """Make downstream evidence reflect the wrong edit, then recover cleanly."""
    fix_index = next(i for i, step in enumerate(trace) if step["step_id"] == fix_step_id)
    test_index = next(
        (i for i, step in enumerate(trace[fix_index + 1:], fix_index + 1) if step["tool_name"] == "run_tests"),
        None,
    )
    if test_index is None:
        return
    trace[test_index]["result"] = {
        "status": "error",
        "exit_code": 1,
        "stdout_ref": "test_outputs/wrong_file_after_edit.txt",
        "summary": "1 failed, 4 passed because the intended implementation file was unchanged.",
    }
    trace[test_index]["summary"] = "Reran tests after the edit and still saw the original failure."

    read_index = next(
        (i for i, step in enumerate(trace[test_index + 1:], test_index + 1) if step["tool_name"] == "read_file"),
        None,
    )
    if read_index is not None:
        trace[read_index]["args"] = {"path": "test_outputs/wrong_file_after_edit.txt"}
        trace[read_index]["result"] = {
            "status": "ok",
            "exit_code": 0,
            "summary": "Read the continued failure and noticed the implementation path mismatch.",
        }
        trace[read_index]["summary"] = "Inspected the still-failing test output after the wrong-file edit."

    submit_index = next(
        (i for i, step in enumerate(trace) if step["tool_name"] == "submit"),
        None,
    )
    if submit_index is None:
        return
    old_submit = trace.pop(submit_index)
    trace.append({
        "step_id": "a011",
        "tool_name": "write_file",
        "args": {
            "path": correct_edit_path,
            "content_summary": "Recovered by applying the same fix to the intended implementation file.",
        },
        "result": {"status": "ok", "exit_code": 0, "summary": "Patched the intended file after spotting the mismatch."},
        "summary": "Recovered from the wrong-file edit by patching the intended file.",
        "tokens": 410,
    })
    trace.append({
        "step_id": "a012",
        "tool_name": "run_tests",
        "args": {"command": "pytest -q"},
        "result": {
            "status": "ok",
            "exit_code": 0,
            "stdout_ref": "test_outputs/a012.txt",
            "summary": "5 passed in 0.02s",
        },
        "summary": "Reran tests after the recovery patch and they passed.",
        "tokens": 170,
    })
    old_submit["step_id"] = "a013"
    old_submit["summary"] = "Submitted after recovering from the wrong-file edit and rerunning tests."
    trace.append(old_submit)
