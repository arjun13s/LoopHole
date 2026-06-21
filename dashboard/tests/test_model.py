"""TDD: the pure aggregation + base-vs-trained delta layer.

These functions are the analytical core of the money-shot. They must be pure,
deterministic, and independent of Rich/Textual and of loop_auditor_env.
"""

from __future__ import annotations

import math

from dashboard import model


def _rec(model_tag, loc, ftype, expl, reward, trace_tok, aud_tok, run_id="r"):
    return {
        "run_id": run_id,
        "model": model_tag,
        "localization_correct": loc,
        "failure_type_correct": ftype,
        "explanation_score": expl,
        "reward": reward,
        "trace_tokens": trace_tok,
        "auditor_tokens": aud_tok,
    }


def test_aggregate_empty_is_safe():
    agg = model.aggregate([])
    assert agg.n == 0
    assert agg.localization_accuracy == 0.0
    assert agg.mean_reward == 0.0
    assert agg.total_auditor_tokens == 0


def test_per_fault_breakdown_groups_by_fault_type():
    traces = {
        "r1": {"run_id": "r1", "planted_failure": {"step_id": "a1", "failure_type": "routing"}},
        "r2": {"run_id": "r2", "planted_failure": {"step_id": "a2", "failure_type": "routing"}},
        "c1": {"run_id": "c1", "planted_failure": None},
    }
    records = [
        _rec("base", False, False, 0.0, 0.0, 1, 1, run_id="r1"),
        _rec("base", True, True, 0.0, 1.0, 1, 1, run_id="r2"),
        _rec("trained", True, True, 0.8, 1.7, 1, 1, run_id="r1"),
        _rec("trained", True, True, 0.8, 1.7, 1, 1, run_id="r2"),
        _rec("base", True, True, 0.0, 1.0, 1, 1, run_id="c1"),
        _rec("trained", True, True, 0.0, 1.0, 1, 1, run_id="c1"),
    ]
    rows = {r.fault_type: r for r in model.per_fault_breakdown(records, traces)}
    assert rows["routing"].n == 2
    assert rows["routing"].base_localization == 0.5      # 1 of 2
    assert rows["routing"].trained_localization == 1.0   # 2 of 2
    assert math.isclose(rows["routing"].delta, 0.5)
    assert rows["clean"].n == 1
    # No traces -> no breakdown (dashboard omits the table).
    assert model.per_fault_breakdown(records, {}) == []


def test_aggregate_computes_means_and_totals():
    recs = [
        _rec("base", True, True, 0.5, 1.8, 100, 40, run_id="a"),
        _rec("base", False, False, 0.0, 0.0, 200, 60, run_id="b"),
    ]
    agg = model.aggregate(recs)
    assert agg.n == 2
    assert math.isclose(agg.localization_accuracy, 0.5)
    assert math.isclose(agg.failure_type_accuracy, 0.5)
    assert math.isclose(agg.mean_explanation_score, 0.25)
    assert math.isclose(agg.mean_reward, 0.9)
    assert agg.total_trace_tokens == 300
    assert agg.total_auditor_tokens == 100


def test_split_by_model_groups_records():
    recs = [
        _rec("base", True, True, 0.5, 1.8, 100, 40),
        _rec("trained", True, True, 0.9, 1.8, 100, 30),
    ]
    by = model.split_by_model(recs)
    assert set(by) == {"base", "trained"}
    assert by["base"][0]["auditor_tokens"] == 40
    assert by["trained"][0]["auditor_tokens"] == 30


def test_delta_base_vs_trained_is_trained_minus_base():
    base = [
        _rec("base", False, False, 0.0, 0.0, 100, 50, run_id="a"),
        _rec("base", True, True, 0.4, 1.7, 100, 50, run_id="b"),
    ]
    trained = [
        _rec("trained", True, True, 0.8, 1.9, 100, 30, run_id="a"),
        _rec("trained", True, True, 0.9, 1.95, 100, 30, run_id="b"),
    ]
    d = model.delta(model.aggregate(base), model.aggregate(trained))
    # trained localizes 2/2 vs base 1/2 -> +0.5
    assert math.isclose(d.localization_accuracy, 0.5)
    # trained is more concise -> negative auditor-token delta (a real, honest saving)
    assert d.total_auditor_tokens == -40
    assert d.mean_reward > 0


def test_planted_step_id_extracts_from_trace():
    trace = {"run_id": "x", "planted_failure": {"step_id": "iter0.step1", "failure_type": "routing", "description": "d"}}
    assert model.planted_step_id(trace) == "iter0.step1"
    clean = {"run_id": "y", "planted_failure": None}
    assert model.planted_step_id(clean) is None
