"""Tests for the self-improvement signal producer (diagnostics.py).

Drives the deterministic detection signals consumed by the (Codex-owned)
self-improvement analyzer. Every signal is a pure function of
(eval_record, raw_verdict, trace_view, ground_truth) — no network, no LLM.
"""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")

from loop_auditor_env import diagnostics  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
SIDECAR_SCHEMA = json.loads((REPO_ROOT / "schemas" / "verdict_sidecar.json").read_text())
VERDICT_SCHEMA = json.loads((REPO_ROOT / "schemas" / "verdict.json").read_text())


def _eval_record(**over):
    base = {
        "run_id": "r1", "model": "base",
        "localization_correct": False, "failure_type_correct": False,
        "explanation_score": 0.0, "reward": 0.0,
        "trace_tokens": 10, "auditor_tokens": 5,
    }
    base.update(over)
    return base


GT = {"step_id": "a7", "failure_type": "tool_misuse",
      "description": "Submitted after the focused tests reported a failure."}
TRACE = {"run_id": "r1", "iterations": [{"index": 0, "steps": [
    {"step_id": "a7", "action_type": "tool_call", "tool_name": "submit"}]}]}


# --- parse_failure -----------------------------------------------------------
def test_unparseable_verdict_sets_verdict_parsed_false():
    rec = diagnostics.build_sidecar_record(
        _eval_record(), "not json at all", {"run_id": "r1", "iterations": []}, None)
    s = rec["signals"]
    assert s["verdict_parsed"] is False
    assert s["raw_present"] is True
    assert s["raw_char_len"] == len("not json at all")
    # core stays a dashboard-valid clean placeholder
    assert rec["fault_present"] is False and rec["predicted_step_id"] is None


def test_empty_verdict_raw_not_present():
    rec = diagnostics.build_sidecar_record(_eval_record(), "   ", {"run_id": "r1", "iterations": []}, None)
    assert rec["signals"]["raw_present"] is False
    assert rec["signals"]["verdict_parsed"] is False


# --- ground-truth mirror + correctness ---------------------------------------
def test_buggy_correct_localization_signals():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "Submitted after the focused tests failed at a7.",
         "proposed_fix": "Do not submit on failing tests; rerun first."}
    er = _eval_record(localization_correct=True, failure_type_correct=True,
                      explanation_score=0.8, reward=1.7)
    rec = diagnostics.build_sidecar_record(er, json.dumps(v), TRACE, GT)
    s = rec["signals"]
    assert s["gt_fault_present"] is True
    assert s["pred_fault_present"] is True
    assert s["gt_step_id"] == "a7" and s["gt_failure_type"] == "tool_misuse"
    assert s["localization_correct"] is True and s["failure_type_correct"] is True
    assert s["explanation_score"] == 0.8 and s["reward"] == 1.7
    assert s["citation_passed"] is True and s["fabricated_step_refs"] == []
    assert s["gt_step_in_trace"] is True
    # core mirrors the validated verdict
    assert rec["fault_present"] is True and rec["predicted_step_id"] == "a7"


def test_clean_trace_signals():
    v = {"fault_present": False, "predicted_step_id": None, "failure_type": None,
         "explanation": "Every step is consistent; no fault.", "proposed_fix": None}
    er = _eval_record(localization_correct=False, reward=1.0)
    rec = diagnostics.build_sidecar_record(er, json.dumps(v), TRACE, None)
    s = rec["signals"]
    assert s["gt_fault_present"] is False
    assert s["gt_step_id"] is None and s["gt_failure_type"] is None
    # clean-gated signals must not trip the dataset rule
    assert s["fix_grounded"] is True and s["gt_step_in_trace"] is True


# --- fabricated_step_ref -----------------------------------------------------
def test_fabricated_step_ref_detected():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "The real bug is at step a99.", "proposed_fix": "fix it"}
    rec = diagnostics.build_sidecar_record(_eval_record(localization_correct=True), json.dumps(v), TRACE, GT)
    s = rec["signals"]
    assert s["citation_passed"] is False
    assert "a99" in s["fabricated_step_refs"]


# --- failure_type_raw + type_out_of_enum -------------------------------------
def test_alias_type_is_normalized_and_in_enum():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "test_failure",
         "explanation": "x at a7", "proposed_fix": "y"}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    s = rec["signals"]
    assert s["failure_type_raw"] == "test_failure"
    assert rec["failure_type"] == "tool_misuse"  # normalized in core
    assert s["type_out_of_enum"] is False


def test_invented_type_is_out_of_enum():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "flakiness",
         "explanation": "x at a7", "proposed_fix": "y"}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    s = rec["signals"]
    assert s["failure_type_raw"] == "flakiness"
    assert s["type_out_of_enum"] is True


# --- dataset_issue signals ---------------------------------------------------
def test_planted_step_not_in_trace():
    gt = {"step_id": "a_missing", "failure_type": "routing", "description": "d"}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, gt)
    assert rec["signals"]["gt_step_in_trace"] is False


def test_fix_grounded_true_with_structured_fix(tmp_path):
    gt = {"step_id": "a7", "failure_type": "tool_misuse", "description": "d",
          "fix": {"action": "rerun", "tool_name": "run_tests"}}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, gt,
                                           base_traces_dir=tmp_path)
    assert rec["signals"]["fix_grounded"] is True


def test_fix_grounded_false_without_base_or_structured_fix(tmp_path):
    gt = {"step_id": "a7", "failure_type": "tool_misuse", "description": "d"}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, gt,
                                           base_traces_dir=tmp_path)
    assert rec["signals"]["fix_grounded"] is False


# --- artifact signals --------------------------------------------------------
def test_rich_case_artifacts_from_metadata(tmp_path):
    case = tmp_path / "case"
    (case / "repo").mkdir(parents=True)
    (case / "repo" / "a.py").write_text("print(1)\n")
    (case / "patch.diff").write_text("--- a\n+++ b\n")
    trace = {"run_id": "x", "metadata": {"case_dir": str(case)}, "iterations": []}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', trace, None)
    s = rec["signals"]
    assert s["is_rich_case"] is True
    assert s["artifact_count"] == 2


def test_non_rich_case_has_no_artifacts():
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, None)
    s = rec["signals"]
    assert s["is_rich_case"] is False
    assert s["artifact_count"] == 0


# --- tool-call aggregation ---------------------------------------------------
def test_tool_calls_aggregated():
    tc = {"read_artifact": 2, "list_artifacts": 1, "get_step": 3, "search_steps": 1, "gate": 4}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, None, tool_calls=tc)
    s = rec["signals"]
    assert s["artifact_tool_calls"] == 3  # read(2)+list(1)
    assert s["inspection_tool_calls"] == 4  # get_step(3)+search_steps(1)


def test_tool_calls_unknown_is_null():
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', TRACE, None)
    s = rec["signals"]
    assert s["artifact_tool_calls"] is None
    assert s["inspection_tool_calls"] is None


# --- prompt_confusion structural flags ---------------------------------------
def test_proposed_fix_contains_code():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "x at a7", "proposed_fix": "```python\ndef fix():\n    return 1\n```"}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["proposed_fix_contains_code"] is True


def test_process_fix_is_not_code():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "x at a7", "proposed_fix": "Run the focused tests before submitting."}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["proposed_fix_contains_code"] is False


def test_explanation_empty_when_fault_claimed():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "", "proposed_fix": "fix it"}
    # an empty explanation still validates (string present); the producer flags the gap
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["explanation_empty"] is True


def test_references_path_token():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "wrong_file_edit",
         "explanation": "It edited src/config_helpers.py instead.", "proposed_fix": "Edit config.py."}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["references_path_token"] is True


# --- fix-concept coverage ----------------------------------------------------
def test_fix_concept_coverage_counts(tmp_path):
    gt = {"step_id": "a7", "failure_type": "tool_misuse", "description": "d"}
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "The worker submitted despite failing tests.",
         "proposed_fix": "Do not submit; rerun the tests before submitting."}
    rec = diagnostics.build_sidecar_record(_eval_record(localization_correct=True), json.dumps(v),
                                           TRACE, gt, base_traces_dir=tmp_path)
    s = rec["signals"]
    assert s["fix_concept_total"] == 2
    assert s["fix_concept_matched"] == 2


# --- robustness: degrade, never crash ---------------------------------------
def test_malformed_ground_truth_does_not_crash(tmp_path):
    # gt missing failure_type would KeyError in expected_correction; must degrade.
    gt = {"step_id": "a2"}  # no failure_type
    rec = diagnostics.build_sidecar_record(
        _eval_record(localization_correct=True), '{"fault_present": false}', TRACE, gt,
        base_traces_dir=tmp_path)
    assert rec["signals"]["fix_concept_total"] == 0  # ungradeable -> dataset_issue territory


def test_corrupt_base_trace_does_not_crash(tmp_path):
    (tmp_path / "corrupt.json").write_text("{ this is not valid json")
    trace = {"run_id": "corrupt__rm", "iterations": [{"index": 0, "steps": [{"step_id": "a2"}]}]}
    gt = {"step_id": "a2", "failure_type": "tool_misuse", "description": "d"}
    rec = diagnostics.build_sidecar_record(
        _eval_record(), '{"fault_present": false}', trace, gt, base_traces_dir=tmp_path)
    assert rec["signals"]["fix_grounded"] is False  # corrupt base -> not grounded, no crash


# --- H3: sidecar core stays valid against the FROZEN verdict.json -------------
def test_out_of_enum_failure_type_nulled_in_core_but_kept_in_signals():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "flaky_test",
         "explanation": "x at a7", "proposed_fix": "y"}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["failure_type"] is None                      # core: dashboard-valid
    assert rec["signals"]["failure_type_raw"] == "flaky_test"  # truth preserved for analyzer
    assert rec["signals"]["type_out_of_enum"] is True


# --- signal precision (regex false positives) --------------------------------
def test_prose_class_is_not_code():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "It triggered a class of resource error.", "proposed_fix": "Avoid that class of action."}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["proposed_fix_contains_code"] is False


def test_word_slash_word_is_not_a_path():
    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "routing",
         "explanation": "It ran before/after the step.", "proposed_fix": "Decide yes/no and continue."}
    rec = diagnostics.build_sidecar_record(_eval_record(), json.dumps(v), TRACE, GT)
    assert rec["signals"]["references_path_token"] is False


def test_gt_step_in_trace_canonical_zero_pad():
    # planted "a7" vs trace "a07": the zero-pad shorthand must still match.
    trace = {"run_id": "z", "iterations": [{"index": 0, "steps": [{"step_id": "a07"}]}]}
    gt = {"step_id": "a7", "failure_type": "tool_misuse", "description": "d"}
    rec = diagnostics.build_sidecar_record(_eval_record(), '{"fault_present": false}', trace, gt)
    assert rec["signals"]["gt_step_in_trace"] is True


# --- schema conformance ------------------------------------------------------
def test_record_conforms_to_schemas():
    from jsonschema import Draft202012Validator

    v = {"fault_present": True, "predicted_step_id": "a7", "failure_type": "tool_misuse",
         "explanation": "Submitted after failing tests at a7.", "proposed_fix": "Rerun first."}
    rec = diagnostics.build_sidecar_record(
        _eval_record(localization_correct=True, failure_type_correct=True, explanation_score=0.5, reward=1.8),
        json.dumps(v), TRACE, GT)
    Draft202012Validator(SIDECAR_SCHEMA).validate(rec)
    core = {k: rec[k] for k in ("fault_present", "predicted_step_id", "failure_type", "explanation", "proposed_fix")}
    Draft202012Validator(VERDICT_SCHEMA).validate(core)
