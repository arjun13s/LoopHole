"""End-to-end base-eval on mocks: DummyBackend + stub judge, no GPU/network.

Verifies the full pipeline produces schema-valid eval-result records and a verdict
sidecar, scores correctly, and is robust to a model that emits non-JSON.
"""

from __future__ import annotations

import json
import math

from training import base_eval
from training.backends import DummyBackend


def _buggy():
    return {
        "run_id": "buggy-1", "task": "fix it",
        "iterations": [{"index": 0, "steps": [
            {"step_id": "iter0.step0", "action_type": "tool_call", "tool_name": "read_file", "tokens": 10},
            {"step_id": "iter0.step1", "action_type": "tool_call", "tool_name": "edit_file", "tokens": 20},
        ]}],
        "planted_failure": {"step_id": "iter0.step1", "failure_type": "routing", "description": "wrong target"},
    }


def _clean():
    return {
        "run_id": "clean-1", "task": "doc it",
        "iterations": [{"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "final", "tokens": 6}]}],
        "planted_failure": None,
    }


def test_pipeline_scores_and_writes_schema_valid_output(tmp_path):
    traces = [_buggy(), _clean()]
    backend = DummyBackend([
        {"fault_present": True, "predicted_step_id": "iter0.step1", "failure_type": "routing", "explanation": "wrong module", "proposed_fix": "edit right one"},
        {"fault_present": False, "predicted_step_id": None, "failure_type": None, "explanation": "clean", "proposed_fix": None},
    ])
    agg = base_eval.run_base_eval(traces, backend, model_tag="base",
                                  explanation_scorer=lambda verdict, gt, view: 0.8, out_dir=tmp_path)

    assert agg["n"] == 2
    assert math.isclose(agg["localization_accuracy"], 1.0)

    results = [json.loads(l) for l in (tmp_path / "eval_results.base.jsonl").read_text().splitlines()]
    verdicts = [json.loads(l) for l in (tmp_path / "verdicts.base.jsonl").read_text().splitlines()]
    assert len(results) == 2 and len(verdicts) == 2
    buggy = next(r for r in results if r["run_id"] == "buggy-1")
    assert buggy["localization_correct"] and math.isclose(buggy["reward"], 1.0 + 0.3 + 0.5 * 0.8)
    clean = next(r for r in results if r["run_id"] == "clean-1")
    assert clean["reward"] == 1.0
    assert verdicts[0]["predicted_step_id"] == "iter0.step1"


def test_pipeline_robust_to_non_json_output(tmp_path):
    backend = DummyBackend(["I think the bug is somewhere but I'm not sure"])  # not JSON
    agg = base_eval.run_base_eval([_buggy()], backend, explanation_scorer=lambda *a: 1.0, out_dir=tmp_path)
    assert agg["localization_accuracy"] == 0.0  # unparseable -> wrong, no crash
    assert agg["mean_reward"] == 0.0


def test_scorer_not_called_when_localization_wrong():
    calls = []
    backend = DummyBackend([{"fault_present": True, "predicted_step_id": "iter0.step0", "failure_type": "safety", "explanation": "x", "proposed_fix": "y"}])
    agg = base_eval.run_base_eval([_buggy()], backend, explanation_scorer=lambda *a: calls.append(1) or 1.0)
    assert calls == []  # explanation scorer only runs on correct localization
    assert agg["mean_reward"] == 0.0


def test_deterministic_scorer_reuses_p2_modules_and_is_default(monkeypatch, tmp_path):
    # The default scorer is Person 2's deterministic fix-by-comparison + citation gate.
    s = base_eval.deterministic_explanation_scorer(base_traces_dir=tmp_path)
    assert callable(s)  # constructing it imports loop_auditor_env's PURE modules cleanly

    # With no scorer injected, run_base_eval falls back to that deterministic default.
    used = {}

    def _stub_scorer(verdict, gt, view):
        used["called"] = True
        return 0.5

    monkeypatch.setattr(base_eval, "deterministic_explanation_scorer", lambda *a, **k: _stub_scorer)
    backend = DummyBackend([{"fault_present": True, "predicted_step_id": "iter0.step1", "failure_type": "routing", "explanation": "wrong module", "proposed_fix": "edit right one"}])
    agg = base_eval.run_base_eval([_buggy()], backend)
    assert used.get("called") is True
    assert math.isclose(agg["mean_reward"], 1.0 + 0.3 + 0.5 * 0.5)
