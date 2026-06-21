"""Validation for generated trace bundles and deterministic labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FAILURE_TYPES = {"resource_misuse", "tool_misuse", "routing", "wrong_file_edit"}
FIX_ACTIONS = {"insert", "remove", "replace"}
TOOLS = {"read_file", "write_file", "run_tests", "submit"}


def load_trace_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        rows.append(row)
    return rows


def validate_case_dir(case_dir: Path, ground_truth_path: Path) -> None:
    trace = load_trace_jsonl(case_dir / "trace.jsonl")
    ground_truth = json.loads(ground_truth_path.read_text())
    validate_trace(trace)
    validate_ground_truth(trace, case_dir, ground_truth)


def validate_trace(trace: list[dict[str, Any]]) -> None:
    if not trace:
        raise ValueError("trace must contain at least one ActionSpan")
    seen = set()
    for step in trace:
        for key in ("step_id", "tool_name", "args", "result", "summary"):
            if key not in step:
                raise ValueError(f"missing {key} in step {step.get('step_id')}")
        if step["step_id"] in seen:
            raise ValueError(f"duplicate step_id: {step['step_id']}")
        seen.add(step["step_id"])
        if step["tool_name"] not in TOOLS:
            raise ValueError(f"invalid tool_name at {step['step_id']}: {step['tool_name']}")
        if not isinstance(step["args"], dict):
            raise ValueError(f"args must be object at {step['step_id']}")
        result = step["result"]
        if not isinstance(result, dict) or result.get("status") not in {"ok", "error", "timeout"}:
            raise ValueError(f"invalid result at {step['step_id']}")


def validate_ground_truth(trace: list[dict[str, Any]], case_dir: Path, ground_truth: dict[str, Any]) -> None:
    required = {"case_id", "fault_present", "fault_step_id", "failure_type", "fix"}
    if set(ground_truth) != required:
        raise ValueError(f"ground_truth fields must be {sorted(required)}")

    if ground_truth["fault_present"] is False:
        if ground_truth["fault_step_id"] is not None or ground_truth["failure_type"] is not None:
            raise ValueError("clean ground_truth must have null fault fields")
        if ground_truth["fix"] is not None:
            raise ValueError("clean ground_truth must have null fix")
        _validate_clean_loop(trace)
        return

    step_ids = [step["step_id"] for step in trace]
    fault_step_id = ground_truth["fault_step_id"]
    failure_type = ground_truth["failure_type"]
    if fault_step_id not in step_ids:
        raise ValueError(f"fault_step_id does not exist: {fault_step_id}")
    if failure_type not in FAILURE_TYPES:
        raise ValueError(f"invalid failure_type: {failure_type}")
    fix = ground_truth["fix"]
    if not isinstance(fix, dict):
        raise ValueError("fault ground_truth must include fix object")
    if fix.get("action") not in FIX_ACTIONS:
        raise ValueError(f"invalid fix action: {fix.get('action')}")
    if fix.get("step_id") not in step_ids:
        raise ValueError(f"fix step_id does not exist: {fix.get('step_id')}")
    _validate_fix_target_exists(case_dir, step_ids, fix.get("target"))

    if failure_type == "tool_misuse":
        _validate_tool_misuse_pin(trace, fault_step_id)
    elif failure_type == "routing":
        _validate_routing(trace, fault_step_id)
    elif failure_type == "resource_misuse":
        _validate_resource_misuse(trace, fault_step_id)
    elif failure_type == "wrong_file_edit":
        _validate_wrong_file_edit(trace, fault_step_id, fix["target"])


def _validate_clean_loop(trace: list[dict[str, Any]]) -> None:
    try:
        failing_test = next(i for i, step in enumerate(trace) if step["tool_name"] == "run_tests" and step["result"]["status"] == "error")
        inspect = next(i for i, step in enumerate(trace) if i > failing_test and step["tool_name"] == "read_file")
        fix = next(i for i, step in enumerate(trace) if i > inspect and step["tool_name"] == "write_file")
        passing_test = next(i for i, step in enumerate(trace) if i > fix and step["tool_name"] == "run_tests" and step["result"]["status"] == "ok")
        submit = next(i for i, step in enumerate(trace) if i > passing_test and step["tool_name"] == "submit")
    except StopIteration as exc:
        raise ValueError("clean trace must include failing tests -> inspect -> fix -> passing tests -> submit") from exc
    if not failing_test < inspect < fix < passing_test < submit:
        raise ValueError("clean trace loop order is invalid")


def _validate_fix_target_exists(case_dir: Path, step_ids: list[str], target: str | None) -> None:
    if target is None:
        raise ValueError("fix.target is required")
    if target in step_ids:
        return
    if (case_dir / target).exists():
        return
    raise ValueError(f"fix target does not exist as step id or case path: {target}")


def _validate_tool_misuse_pin(trace: list[dict[str, Any]], fault_step_id: str) -> None:
    idx = _index(trace, fault_step_id)
    if trace[idx]["tool_name"] == "run_tests":
        raise ValueError("tool_misuse must be pinned to the step that ignored the failure, not the failing test")
    prior_failures = [
        step for step in trace[:idx]
        if step["tool_name"] == "run_tests" and step["result"]["status"] == "error"
    ]
    if not prior_failures:
        raise ValueError("tool_misuse fault step must follow a failing run_tests step")


def _validate_routing(trace: list[dict[str, Any]], fault_step_id: str) -> None:
    idx = _index(trace, fault_step_id)
    if trace[idx]["tool_name"] != "submit":
        raise ValueError("routing fault must be pinned to submit")
    last_write = max(i for i, step in enumerate(trace[:idx]) if step["tool_name"] == "write_file")
    if any(step["tool_name"] == "run_tests" for step in trace[last_write + 1:idx]):
        raise ValueError("routing fault must skip run_tests after the final edit")


def _validate_resource_misuse(trace: list[dict[str, Any]], fault_step_id: str) -> None:
    step = trace[_index(trace, fault_step_id)]
    if step["tool_name"] != "read_file" or step.get("tokens", 0) < 7000:
        raise ValueError("resource_misuse must be an oversized read_file step")


def _validate_wrong_file_edit(trace: list[dict[str, Any]], fault_step_id: str, correct_target: str) -> None:
    step = trace[_index(trace, fault_step_id)]
    if step["tool_name"] != "write_file" or step["args"].get("path") == correct_target:
        raise ValueError("wrong_file_edit must point a write_file step at the wrong path")


def _index(trace: list[dict[str, Any]], step_id: str) -> int:
    for idx, step in enumerate(trace):
        if step["step_id"] == step_id:
            return idx
    raise ValueError(f"step_id not found: {step_id}")
