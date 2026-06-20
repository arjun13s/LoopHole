import pytest

from loop_auditor_env import config
from loop_auditor_env.reward import compute_reward


GROUND_TRUTH = {
    "step_id": "iter0.step1.bad",
    "failure_type": "routing",
    "description": "fixture",
}


def test_reward_full_match_includes_explanation_score():
    verdict = {"predicted_step_id": "iter0.step1.bad", "failure_type": "routing"}

    assert compute_reward(verdict, GROUND_TRUTH, explanation_score=0.8) == pytest.approx(1.7)


def test_reward_wrong_type_keeps_localization_and_explanation():
    verdict = {"predicted_step_id": "iter0.step1.bad", "failure_type": "safety"}

    assert compute_reward(verdict, GROUND_TRUTH, explanation_score=0.8) == pytest.approx(1.4)


def test_reward_wrong_location_gates_explanation_but_not_failure_type():
    verdict = {"predicted_step_id": "iter0.step0.ok", "failure_type": "routing"}

    assert compute_reward(verdict, GROUND_TRUTH, explanation_score=1.0) == pytest.approx(0.3)


def test_reward_wrong_location_and_wrong_type():
    verdict = {"predicted_step_id": "iter0.step0.ok", "failure_type": "safety"}

    assert compute_reward(verdict, GROUND_TRUTH, explanation_score=1.0) == 0.0


def test_reward_clean_trace_no_fault():
    verdict = {"predicted_step_id": config.NO_FAULT_STEP_ID, "failure_type": config.NO_FAULT_TYPE}

    assert compute_reward(verdict, None, explanation_score=1.0) == 1.0


def test_reward_clean_trace_false_positive():
    verdict = {"predicted_step_id": "iter0.step1.bad", "failure_type": "routing"}

    assert compute_reward(verdict, None, explanation_score=1.0) == 0.0

