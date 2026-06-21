"""Render smoke tests: the static report builds and contains the load-bearing facts.

We render to a recorded Console (no TTY needed) and assert the money-shot numbers
and highlights are present — this is what makes the dashboard CLI-agent visible.
"""

from __future__ import annotations

from rich.console import Console

from dashboard import loader, render


def _capture(renderable) -> str:
    console = Console(record=True, width=100)
    console.print(renderable)
    return console.export_text()


def test_dashboard_renders_money_shot_and_replay():
    results_paths, verdicts_path, trace_paths = loader.bundled_fixture_paths()
    records = loader.load_eval_results(results_paths)
    verdicts = loader.load_verdicts(verdicts_path)
    traces = loader.load_traces(trace_paths)

    out = _capture(render.dashboard(records, verdicts, traces))

    # Money-shot framing + the base-vs-trained delta exist.
    assert "Base vs Trained" in out
    assert "Localization accuracy" in out
    # Trained localized 3/3 vs base 1/3.
    assert "100%" in out and "33%" in out
    # Honest token chart, not a fabricated "tokens saved".
    assert "cheaper audit" in out
    assert "tokens saved" not in out.lower()
    # Trace replay highlights the planted fault and the clean trace.
    assert "PLANTED FAULT" in out
    assert "clean trace" in out
    # Verdict drill-down shows the trained model's correct localization.
    assert "iter0.step1.overwrite-limit" in out


def test_token_chart_marks_trained_cheaper():
    base = render.model_mod.aggregate([
        {"localization_correct": False, "failure_type_correct": False, "explanation_score": 0.0,
         "reward": 0.0, "trace_tokens": 10, "auditor_tokens": 200, "model": "base", "run_id": "a"},
    ])
    trained = render.model_mod.aggregate([
        {"localization_correct": True, "failure_type_correct": True, "explanation_score": 0.9,
         "reward": 1.9, "trace_tokens": 10, "auditor_tokens": 120, "model": "trained", "run_id": "a"},
    ])
    out = _capture(render.token_chart(base, trained))
    assert "200" in out and "120" in out
