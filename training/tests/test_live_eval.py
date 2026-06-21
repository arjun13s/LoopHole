"""Adapter for Person 1's live Qwen traces -> base-eval, on the REAL dataset.

These run against the committed `generated_traces/live_qwen/` fixtures (no GPU, no
network): they prove the flat live trace.jsonl shape flows through the normalizer
into schema-valid base eval-result records with honest token accounting.
"""

from __future__ import annotations

import json

import pytest

from training import base_eval, live_eval, scoring
from training.backends import DummyBackend

LIVE_ROOT = live_eval.LIVE_ROOT

pytestmark = pytest.mark.skipif(
    not (LIVE_ROOT / "clean_cases").is_dir(),
    reason="live_qwen dataset not present",
)


def test_manifest_covers_clean_and_labeled_cases():
    rows = live_eval.build_manifest()
    by_id = {r["case_id"] for r in rows}
    # 4 clean + 16 labeled (4 cases x 4 fault types) in the committed dataset.
    assert sum(r["failure_type"] == "clean" for r in rows) == 4
    assert sum(r["failure_type"] != "clean" for r in rows) == 16
    assert "date_range_boundary__live_000" in by_id
    assert "date_range_boundary__live_000__routing" in by_id
    # Every row points at a real trace + ground-truth sidecar (no failed_cases).
    for r in rows:
        assert r["case_dir"].startswith("generated_traces/live_qwen/")
        assert r["ground_truth"].endswith(".json")


def test_load_live_traces_normalizes_and_preserves_tokens():
    traces = live_eval.load_live_traces()
    assert len(traces) == 20
    for t in traces:
        # Normalized Shape A: run_id + iterations[].steps[], no leaked planted_failure key on the view.
        assert t["run_id"] and t["iterations"]
        # Honest audit cost survives the normalizer's token-stripping.
        assert scoring.count_trace_tokens(t) > 0
    # A labeled case carries a structured fix for deterministic grading.
    routing = next(t for t in traces if t["run_id"] == "date_range_boundary__live_000__routing")
    assert routing["planted_failure"]["failure_type"] == "routing"
    assert routing["planted_failure"].get("fix") is not None


def test_base_eval_runs_over_live_traces_and_is_schema_valid(tmp_path):
    traces = live_eval.load_live_traces()
    # Stub the auditor: clean verdict for every case (proves plumbing, not accuracy).
    backend = DummyBackend([
        {"fault_present": False, "predicted_step_id": None, "failure_type": None,
         "explanation": "stub", "proposed_fix": None}
        for _ in traces
    ])
    agg = base_eval.run_base_eval(traces, backend, model_tag="base", out_dir=tmp_path)

    assert agg["n"] == 20
    assert agg["total_trace_tokens"] > 0  # honest audit-cost feeds the dashboard chart
    # A blanket "no fault" verdict is correct on the 4 clean cases only.
    assert agg["localization_accuracy"] == pytest.approx(4 / 20)

    results = [json.loads(l) for l in (tmp_path / "eval_results.base.jsonl").read_text().splitlines()]
    verdicts = [json.loads(l) for l in (tmp_path / "verdicts.base.jsonl").read_text().splitlines()]
    assert len(results) == 20 and len(verdicts) == 20
    # Clean cases scored reward 1.0; buggy cases missed by the stub score 0.0.
    clean = next(r for r in results if r["run_id"] == "date_range_boundary__live_000")
    assert clean["reward"] == 1.0
    buggy = next(r for r in results if r["run_id"] == "date_range_boundary__live_000__routing")
    assert buggy["reward"] == 0.0
