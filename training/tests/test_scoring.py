"""TDD: the pure scoring core — implements the FROZEN reward spec independently.

Mirrors schemas/reward_spec.json (§1.4) and schemas/verdict.json (main: "NONE"/"none"
clean-trace sentinels). No dependency on loop_auditor_env / hud / anthropic, so it
runs anywhere and the base-eval pipeline is testable without GPUs or network.
"""

from __future__ import annotations

import math

from training import scoring


def test_strip_ground_truth_separates_planted_failure():
    trace = {"run_id": "r", "task": "t", "iterations": [], "planted_failure": {"step_id": "s1", "failure_type": "routing", "description": "d"}}
    view, gt = scoring.strip_ground_truth(trace)
    assert "planted_failure" not in view
    assert view["run_id"] == "r"
    assert gt["step_id"] == "s1"


def test_strip_ground_truth_clean_trace_returns_none_gt():
    view, gt = scoring.strip_ground_truth({"run_id": "r", "iterations": [], "planted_failure": None})
    assert gt is None


def test_count_trace_tokens_sums_step_tokens():
    trace = {"iterations": [
        {"steps": [{"tokens": 12}, {"tokens": 18}]},
        {"steps": [{"tokens": 8}]},
    ]}
    assert scoring.count_trace_tokens(trace) == 38


def test_parse_verdict_accepts_json_string_and_dict():
    d = {"predicted_step_id": "s1", "failure_type": "routing", "explanation": "e", "proposed_fix": "f"}
    assert scoring.parse_verdict(d) == d
    assert scoring.parse_verdict('{"predicted_step_id": "s1", "failure_type": "routing", "explanation": "e", "proposed_fix": "f"}')["failure_type"] == "routing"


def test_parse_verdict_extracts_json_from_noisy_text():
    raw = 'Sure! Here is my verdict:\n{"predicted_step_id":"s1","failure_type":"routing","explanation":"e","proposed_fix":"f"}\nDone.'
    assert scoring.parse_verdict(raw)["predicted_step_id"] == "s1"


def test_score_record_buggy_correct_localization_uses_full_reward():
    gt = {"step_id": "iter0.step1", "failure_type": "routing"}
    v = {"predicted_step_id": "iter0.step1", "failure_type": "routing", "explanation": "why", "proposed_fix": "fix"}
    rec = scoring.score_record("r", "base", v, gt, trace_tokens=40, auditor_tokens=120, explanation_score=0.8)
    assert rec["localization_correct"] is True
    assert rec["failure_type_correct"] is True
    # 1.0*1 + 0.3*1 + 0.5*0.8
    assert math.isclose(rec["reward"], 1.0 + 0.3 + 0.4)
    assert rec["model"] == "base" and rec["trace_tokens"] == 40 and rec["auditor_tokens"] == 120


def test_score_record_buggy_wrong_localization_zeros_explanation():
    gt = {"step_id": "iter0.step1", "failure_type": "routing"}
    v = {"predicted_step_id": "iter0.step0", "failure_type": "safety", "explanation": "x", "proposed_fix": "y"}
    rec = scoring.score_record("r", "base", v, gt, 40, 120, explanation_score=0.9)
    assert rec["localization_correct"] is False
    assert rec["explanation_score"] == 0.0  # only counts when localization correct
    assert rec["reward"] == 0.0


def test_score_record_clean_trace_correct_is_reward_one():
    v = {"fault_present": False, "predicted_step_id": None, "failure_type": None, "explanation": "clean", "proposed_fix": None}
    rec = scoring.score_record("r", "trained", v, None, 27, 90, explanation_score=0.0)
    assert rec["localization_correct"] is True
    assert rec["reward"] == 1.0


def test_score_record_clean_trace_false_positive_is_reward_zero():
    v = {"fault_present": True, "predicted_step_id": "iter0.step1", "failure_type": "tool_misuse", "explanation": "x", "proposed_fix": "y"}
    rec = scoring.score_record("r", "base", v, None, 27, 90, explanation_score=0.0)
    assert rec["localization_correct"] is False
    assert rec["reward"] == 0.0
