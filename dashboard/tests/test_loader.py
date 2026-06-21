"""TDD: schema-validated loading of eval-results, verdict sidecar, and traces.

The loader is the trust boundary: every external record is validated against the
FROZEN schemas before any rendering. Invalid data fails fast with a clear error.
"""

from __future__ import annotations

import argparse
import json

import pytest

from dashboard import loader


def _write(p, lines):
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))


def _eval_rec(model_tag="base", run_id="a"):
    return {
        "run_id": run_id,
        "model": model_tag,
        "localization_correct": True,
        "failure_type_correct": True,
        "explanation_score": 0.5,
        "reward": 1.8,
        "trace_tokens": 100,
        "auditor_tokens": 40,
    }


def test_frozen_schemas_are_loadable():
    # The loader must be able to find and parse the repo's frozen schemas.
    for name in ("eval_result", "verdict", "trace"):
        schema = loader.load_schema(name)
        assert schema.get("title")


def test_load_eval_results_valid(tmp_path):
    p = tmp_path / "results.jsonl"
    _write(p, [_eval_rec("base"), _eval_rec("trained")])
    recs = loader.load_eval_results([p])
    assert len(recs) == 2
    assert {r["model"] for r in recs} == {"base", "trained"}


def test_load_eval_results_rejects_invalid(tmp_path):
    bad = _eval_rec()
    bad["explanation_score"] = 1.5  # out of [0,1] -> schema violation
    p = tmp_path / "bad.jsonl"
    _write(p, [bad])
    with pytest.raises(loader.ValidationError):
        loader.load_eval_results([p])


def test_load_eval_results_skips_blank_lines(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps(_eval_rec()) + "\n\n   \n")
    assert len(loader.load_eval_results([p])) == 1


def test_load_verdicts_missing_file_is_optional(tmp_path):
    # Sidecar is optional: absent file -> empty mapping, never an error.
    assert loader.load_verdicts(tmp_path / "nope.jsonl") == {}


def test_load_verdicts_keys_by_run_and_model(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    _write(p, [{
        "run_id": "a", "model": "trained", "fault_present": True,
        "predicted_step_id": "iter0.step1", "failure_type": "routing",
        "explanation": "why", "proposed_fix": "fix",
    }])
    v = loader.load_verdicts(p)
    assert v[("a", "trained")]["predicted_step_id"] == "iter0.step1"


def test_load_traces_keys_by_run_id(tmp_path):
    t = {
        "run_id": "x", "task": "t", "iterations": [
            {"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "final"}]}
        ],
        "planted_failure": None,
    }
    p = tmp_path / "x.json"
    p.write_text(json.dumps(t))
    traces = loader.load_traces([p])
    assert traces["x"]["task"] == "t"


def test_load_traces_accepts_wrong_file_edit_with_structured_fix(tmp_path):
    t = {
        "run_id": "wrong-file", "task": "t", "iterations": [
            {"index": 0, "steps": [{"step_id": "a007", "action_type": "tool_call"}]}
        ],
        "planted_failure": {
            "step_id": "a007",
            "failure_type": "wrong_file_edit",
            "description": "edited the sibling helper instead of the intended implementation file",
            "fix": {
                "action": "replace",
                "step_id": "a007",
                "target": "repo/src/date_ranges.py",
                "tool_name": "write_file",
            },
        },
    }
    p = tmp_path / "wrong-file.json"
    p.write_text(json.dumps(t))
    traces = loader.load_traces([p])
    assert traces["wrong-file"]["planted_failure"]["failure_type"] == "wrong_file_edit"


def test_resolve_inputs_mock_returns_bundled_fixtures():
    args = argparse.Namespace(mock=True, results=None, verdicts=None, traces=None)
    results, verdicts, traces = loader.resolve_inputs(args)
    assert results == [loader.FIXTURES_DIR / "eval_results.jsonl"]
    assert verdicts == loader.FIXTURES_DIR / "verdicts.jsonl"
    assert traces == sorted((loader.FIXTURES_DIR / "traces").glob("*.json"))


def test_resolve_inputs_explicit_paths():
    from pathlib import Path

    args = argparse.Namespace(
        mock=False,
        results=["results/base.jsonl", "results/trained.jsonl"],
        verdicts="results/verdicts.jsonl",
        traces=None,
    )
    results, verdicts, traces = loader.resolve_inputs(args)
    assert results == [Path("results/base.jsonl"), Path("results/trained.jsonl")]
    assert verdicts == Path("results/verdicts.jsonl")
    assert traces == []
