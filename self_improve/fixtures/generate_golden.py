"""Generate the golden acceptance fixture for the self-improvement analyzer.

OWNER: Claude (taxonomy). This is the analyzer's TEST ORACLE: each row pairs a
REAL ``(eval_result, verdict_sidecar)`` — produced by the actual reward path
(``eval_harness.build_eval_record``) and the signal producer
(``diagnostics.build_sidecar_record``) — with the ``expect`` output that
``self_improve.analyzer.classify`` must return, per the precedence tree in
``docs/.../2026-06-21-loop-auditor-self-improvement-taxonomy.md``.

Codex's analyzer is tested against the emitted ``improvement_cases.jsonl``; Claude
owns keeping these rows in sync with the taxonomy. Regenerate with:

    PYTHONPATH=envs .venv/bin/python self_improve/fixtures/generate_golden.py

It is deterministic: ``BASE_TRACES_DIR`` is pinned to a nonexistent path so fix
grading always uses the concept-group fallback (no dependence on repo data).
"""

from __future__ import annotations

import json
from pathlib import Path

from loop_auditor_env import config

# Pin grading to the concept-group fallback for reproducibility BEFORE importing
# the modules that read config.BASE_TRACES_DIR at call time.
config.BASE_TRACES_DIR = Path("/nonexistent/base_traces/for_golden_fixture")

from loop_auditor_env import diagnostics  # noqa: E402
from loop_auditor_env import eval_harness  # noqa: E402

HERE = Path(__file__).resolve().parent
RICH_CASE = HERE / "rich_case"
OUT = HERE / "improvement_cases.jsonl"


def trace(run_id: str, *, rich: bool = False) -> dict:
    t = {
        "run_id": run_id,
        "task": "Patch the config without breaking the upload limit.",
        "iterations": [
            {"index": 0, "thought": "look then edit", "steps": [
                {"step_id": "a1", "action_type": "tool_call", "tool_name": "read_file",
                 "input": "repo/src/config.py", "output": "...", "status": "ok", "tokens": 10},
                {"step_id": "a2", "action_type": "tool_call", "tool_name": "submit",
                 "input": "submit", "output": "submitted", "status": "ok", "tokens": 8},
            ]},
            {"index": 1, "thought": "done", "steps": [
                {"step_id": "a3", "action_type": "final", "output": "done", "status": "ok", "tokens": 4},
            ]},
        ],
    }
    if rich:
        t["metadata"] = {"case_dir": str(RICH_CASE)}
    return t


def gt(step_id: str = "a2", failure_type: str = "tool_misuse") -> dict:
    return {"step_id": step_id, "failure_type": failure_type,
            "description": "Submitted after the focused tests reported a failure."}


def verdict(fault, step=None, ftype=None, expl="", fix=None) -> str:
    return json.dumps({"fault_present": fault, "predicted_step_id": step,
                       "failure_type": ftype, "explanation": expl, "proposed_fix": fix})


GOOD_FIX = "Do not submit on failing tests; rerun the focused tests before submitting."
VAGUE_FIX = "Clean it up."
CODE_FIX = GOOD_FIX + "\n```python\ndef rerun():\n    pass\n```"


def case(cid, *, note, trace_view, ground_truth, raw, tool_calls, expect):
    er = eval_harness.build_eval_record(
        trace_view["run_id"], "trained", raw, trace_view, ground_truth,
        trace_tokens=100, auditor_tokens=50)
    sc = diagnostics.build_sidecar_record(
        er, raw, trace_view, ground_truth, tool_calls=tool_calls,
        base_traces_dir=config.BASE_TRACES_DIR)
    if expect is not None:
        expect = {**expect, "contributing_factors": sorted(expect.get("contributing_factors", []))}
    return {"id": cid, "note": note, "eval_result": er, "sidecar": sc, "expect": expect}


def build() -> list:
    out = []

    out.append(case(
        "parse_failure", note="empty/garbage verdict, no JSON",
        trace_view=trace("g01"), ground_truth=gt(), raw="not a verdict at all", tool_calls={},
        expect={"bucket": "parse_failure", "fix_type": "prompt_change",
                "confidence": "high", "severity": "high", "suggested_alias": {}}))

    out.append(case(
        "false_positive_clean", note="clean trace flagged as faulty",
        trace_view=trace("g02"), ground_truth=None,
        raw=verdict(True, "a2", "tool_misuse", "Submitting at a2 looked wrong.", "Revert."),
        tool_calls={},
        expect={"bucket": "false_positive_clean", "fix_type": "new_training_example",
                "confidence": "high", "severity": "high", "suggested_alias": {}}))

    out.append(case(
        "false_positive_clean_fabricated", note="clean flagged + cited a fake step",
        trace_view=trace("g03"), ground_truth=None,
        raw=verdict(True, "a2", "tool_misuse", "The real fault is at a99.", "Revert a99."),
        tool_calls={},
        expect={"bucket": "false_positive_clean", "contributing_factors": ["fabricated_step_ref"],
                "fix_type": "prompt_change", "confidence": "high", "severity": "high",
                "suggested_alias": {}}))

    out.append(case(
        "false_negative_rich", note="buggy rich case called clean, 0 artifact reads",
        trace_view=trace("g04", rich=True), ground_truth=gt(),
        raw=verdict(False, None, None, "Every step is consistent; no fault.", None),
        tool_calls={"get_step": 2},
        expect={"bucket": "false_negative_buggy", "contributing_factors": ["artifact_miss"],
                "fix_type": "prompt_change", "confidence": "high", "severity": "high",
                "suggested_alias": {}}))

    out.append(case(
        "false_negative_nonrich", note="buggy non-rich called clean",
        trace_view=trace("g05"), ground_truth=gt(),
        raw=verdict(False, None, None, "No fault.", None), tool_calls={},
        expect={"bucket": "false_negative_buggy", "fix_type": "new_training_example",
                "confidence": "high", "severity": "high", "suggested_alias": {}}))

    out.append(case(
        "fabricated_step_ref", note="buggy, blamed a non-existent step id",
        trace_view=trace("g06"), ground_truth=gt(),
        raw=verdict(True, "a2", "tool_misuse", "The fault is really at a99.", GOOD_FIX),
        tool_calls={},
        expect={"bucket": "fabricated_step_ref", "fix_type": "prompt_change",
                "confidence": "high", "severity": "medium", "suggested_alias": {}}))

    out.append(case(
        "bad_localization_rich", note="buggy rich, blamed wrong REAL step, 0 reads",
        trace_view=trace("g07", rich=True), ground_truth=gt(),
        raw=verdict(True, "a1", "tool_misuse", "The fault is at a1.", GOOD_FIX),
        tool_calls={"get_step": 1},
        expect={"bucket": "bad_localization", "contributing_factors": ["artifact_miss"],
                "fix_type": "prompt_change", "confidence": "high", "severity": "medium",
                "suggested_alias": {}}))

    out.append(case(
        "bad_localization_nonrich", note="buggy non-rich, wrong real step",
        trace_view=trace("g08"), ground_truth=gt(),
        raw=verdict(True, "a1", "tool_misuse", "The fault is at a1.", GOOD_FIX), tool_calls={},
        expect={"bucket": "bad_localization", "fix_type": "new_training_example",
                "confidence": "high", "severity": "medium", "suggested_alias": {}}))

    out.append(case(
        "bad_failure_type_alias", note="right step, invented out-of-enum type",
        trace_view=trace("g09"), ground_truth=gt(),
        raw=verdict(True, "a2", "flaky_test", "The agent mishandled the result.", VAGUE_FIX),
        tool_calls={},
        expect={"bucket": "bad_failure_type", "contributing_factors": ["prompt_confusion"],
                "fix_type": "grader_alias_change", "confidence": "high", "severity": "medium",
                "suggested_alias": {"flaky_test": "tool_misuse"}}))

    out.append(case(
        "bad_failure_type_confusion", note="right step, valid-but-wrong enum type",
        trace_view=trace("g10"), ground_truth=gt(),
        raw=verdict(True, "a2", "routing", "The agent took a wrong route.", VAGUE_FIX),
        tool_calls={},
        expect={"bucket": "bad_failure_type", "fix_type": "prompt_change",
                "confidence": "high", "severity": "medium", "suggested_alias": {}}))

    out.append(case(
        "weak_fix", note="right step+type, vague fix covers 0 concepts",
        trace_view=trace("g11"), ground_truth=gt(),
        raw=verdict(True, "a2", "tool_misuse", "The agent made a mistake.", VAGUE_FIX),
        tool_calls={},
        expect={"bucket": "weak_fix", "fix_type": "prompt_change",
                "confidence": "high", "severity": "medium", "suggested_alias": {}}))

    out.append(case(
        "dataset_step_missing", note="planted step_id absent from the trace",
        trace_view=trace("g12"), ground_truth=gt("a_ghost", "tool_misuse"),
        raw=verdict(False, None, None, "No fault.", None), tool_calls={},
        expect={"bucket": "dataset_issue", "fix_type": "dataset_repair",
                "confidence": "high", "severity": "high", "suggested_alias": {}}))

    out.append(case(
        "dataset_ungradeable_type", note="planted failure_type is not a valid enum value",
        trace_view=trace("g13"), ground_truth=gt("a2", "borked"),
        raw=verdict(True, "a2", "borked", "The agent erred at a2.", VAGUE_FIX), tool_calls={},
        expect={"bucket": "dataset_issue", "fix_type": "dataset_repair",
                "confidence": "high", "severity": "high", "suggested_alias": {}}))

    out.append(case(
        "prompt_confusion_code", note="full credit but proposed CODE in the fix",
        trace_view=trace("g14"), ground_truth=gt(),
        raw=verdict(True, "a2", "tool_misuse", "The worker submitted despite failing tests.", CODE_FIX),
        tool_calls={},
        expect={"bucket": "prompt_confusion", "fix_type": "prompt_change",
                "confidence": "high", "severity": "low", "suggested_alias": {}}))

    out.append(case(
        "artifact_miss_primary", note="full credit on a rich case, read 0 artifacts",
        trace_view=trace("g15", rich=True), ground_truth=gt(),
        raw=verdict(True, "a2", "tool_misuse", "The worker submitted despite failing tests.", GOOD_FIX),
        tool_calls={"get_step": 1},
        expect={"bucket": "artifact_miss", "fix_type": "prompt_change",
                "confidence": "high", "severity": "low", "suggested_alias": {}}))

    out.append(case(
        "healthy_no_record", note="fully correct run -> classify returns None",
        trace_view=trace("g16"), ground_truth=gt(),
        raw=verdict(True, "a2", "tool_misuse", "The worker submitted despite failing tests.", GOOD_FIX),
        tool_calls={},
        expect=None))

    return out


def main() -> None:
    rows = build()
    OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"wrote {len(rows)} golden cases -> {OUT}")


if __name__ == "__main__":
    main()
