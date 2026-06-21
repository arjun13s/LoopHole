"""Wiring tests for Person 1's trace dataset (taskset/*.jsonl) into the env."""

import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import config  # noqa: E402
from loop_auditor_env import env as E  # noqa: E402


def test_load_jsonl_heldout_matches_dataset():
    traces = E.load_jsonl_traces(config.TASKSET_DIR / "heldout.jsonl")
    assert len(traces) == 10
    assert all("run_id" in t and "iterations" in t for t in traces)


def test_select_traces_heldout_has_clean_and_planted(monkeypatch):
    monkeypatch.setattr(config, "DATASET", "heldout")
    traces = E.select_traces()
    assert len(traces) == 10
    planted = [t for t in traces if t.get("planted_failure")]
    assert 0 < len(planted) < len(traces)  # a real mix of buggy + clean


def test_select_traces_default_is_fixtures(monkeypatch):
    monkeypatch.setattr(config, "DATASET", "fixtures")
    assert len(E.select_traces()) == 3


def test_select_traces_demo_all_includes_fixtures_and_live(monkeypatch):
    monkeypatch.setattr(config, "DATASET", "demo_all")
    traces = E.select_traces()
    run_ids = {trace["run_id"] for trace in traces}
    assert {"buggy-resource-misuse-001", "clean-trace-001"}.issubset(run_ids)
    assert any(run_id.startswith("date_range_boundary__live_") for run_id in run_ids)
