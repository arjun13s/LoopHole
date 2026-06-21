"""Pure spread-stats helper for the N-up GRPO pre-flight tool."""

from loop_auditor_env.scripts import run_many


def test_summarize_spread_drops_none():
    s = run_many.summarize([0.0, 1.0, 0.5, None])
    assert s["n"] == 4 and s["got"] == 3
    assert s["min"] == 0.0 and s["max"] == 1.0 and s["spread"] == 1.0
    assert s["mean"] == 0.5


def test_summarize_empty_is_none():
    s = run_many.summarize([None, None])
    assert s["got"] == 0
    assert s["spread"] is None and s["mean"] is None


def test_summarize_zero_spread_flagged_value():
    s = run_many.summarize([0.7, 0.7, 0.7])
    assert s["got"] == 3 and s["spread"] == 0.0
