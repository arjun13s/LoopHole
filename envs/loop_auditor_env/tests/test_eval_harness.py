import pytest

from loop_auditor_env import eval_harness


GROUND_TRUTH = {
    "step_id": "a7",
    "failure_type": "tool_misuse",
    "description": "Submitted after the focused tests reported a failure.",
}


def test_explanation_judge_is_gated_on_localization(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("judge should not run for wrong localization")

    monkeypatch.setattr(eval_harness.judge, "score_explanation", fail_if_called)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a3",
        "failure_type": "tool_misuse",
        "explanation": "Fluent but wrong step.",
        "proposed_fix": "Fix the wrong step.",
    }

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view={"run_id": "r1", "iterations": []},
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is False
    assert record["explanation_score"] == 0.0
    assert record["reward"] == 0.3


def test_explanation_judge_runs_when_localization_is_correct(monkeypatch):
    monkeypatch.setattr(eval_harness.judge, "score_explanation", lambda *args: 0.8)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a7",
        "failure_type": "tool_misuse",
        "explanation": "At a7 the worker submitted after the final test command failed.",
        "proposed_fix": "Fix the failing case and rerun tests before submitting.",
    }

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view={"run_id": "r1", "iterations": []},
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is True
    assert record["explanation_score"] == 0.8
    assert record["reward"] == pytest.approx(1.7)
