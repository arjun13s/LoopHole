"""Trace-loading + schema-validation for the base-eval CLI (no network)."""

from __future__ import annotations

import json

import pytest

from training import run_base_eval


def _trace(run_id="t"):
    return {
        "run_id": run_id, "task": "x",
        "iterations": [{"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "final"}]}],
        "planted_failure": None,
    }


def test_load_traces_from_directory(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_trace("a")))
    (tmp_path / "b.json").write_text(json.dumps(_trace("b")))
    traces = run_base_eval.load_traces(tmp_path)
    assert {t["run_id"] for t in traces} == {"a", "b"}


def test_load_traces_from_jsonl(tmp_path):
    p = tmp_path / "set.jsonl"
    p.write_text(json.dumps(_trace("a")) + "\n" + json.dumps(_trace("b")) + "\n")
    assert len(run_base_eval.load_traces(p)) == 2


def test_validate_traces_accepts_conforming_and_rejects_divergent():
    run_base_eval.validate_traces([_trace()])  # frozen-schema conforming -> ok
    # Person-1-style trace (id/actions instead of run_id/steps) must be rejected (issue #3 guard).
    divergent = {"id": "x", "env": "LoopAuditorEnv", "iterations": [{"index": 0, "actions": []}], "planted_failure": None}
    with pytest.raises(Exception):
        run_base_eval.validate_traces([divergent])
