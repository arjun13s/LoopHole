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

    out = _capture(render.dashboard(records, verdicts, traces, source_label="demo fixtures"))

    # Headline takeaway banner (money-shot first).
    assert "catches every planted fault" in out
    # Provenance subtitle so the surface never misleads.
    assert "demo fixtures" in out
    # Money-shot framing + the base-vs-trained delta exist.
    assert "Base vs Trained" in out
    assert "Localization accuracy" in out
    assert "100%" in out  # trained localizes every fault
    # Honest token chart, not a fabricated "tokens saved".
    assert "cheaper audit" in out
    assert "tokens saved" not in out.lower()
    # Per-fault-type breakdown across the three schema-valid fault types.
    assert "Localization by fault type" in out
    for ft in ("routing", "resource_misuse", "tool_misuse"):
        assert ft in out
    # Trace replay highlights the planted fault and the clean trace.
    assert "PLANTED FAULT" in out
    assert "clean trace" in out
    # Verdict drill-down shows the trained model's correct localization (routing → a008).
    assert "Step a008 is the fault" in out


def test_trained_pending_shows_no_misleading_zero():
    # Base-only (real run before the trained model lands): the Trained column must
    # read "pending", never a fake 0% with a negative Δ.
    base_only = [
        {"localization_correct": True, "failure_type_correct": True, "explanation_score": 0.0,
         "reward": 1.0, "trace_tokens": 10, "auditor_tokens": 200, "model": "base", "run_id": "a"},
    ]
    out = _capture(render.dashboard(base_only, {}, {}))
    assert "pending" in out.lower()
    assert "trained run pending" in out.lower()  # headline reflects it
    assert "-1.00" not in out and "-100%" not in out  # no fabricated negative delta


def test_trained_only_real_eval_shows_base_pending():
    # P2's real HUD artifacts are trained-only (no base side yet): the Base column
    # must read "pending", never a fabricated 0% that implies base scored zero.
    trained_only = [
        {"localization_correct": True, "failure_type_correct": True, "explanation_score": 0.5,
         "reward": 1.5, "trace_tokens": 0, "auditor_tokens": 2400, "model": "trained",
         "run_id": "inventory_total__routing"},
        {"localization_correct": False, "failure_type_correct": True, "explanation_score": 0.0,
         "reward": 0.0, "trace_tokens": 0, "auditor_tokens": 2400, "model": "trained",
         "run_id": "inventory_total__wrong_file_edit"},
    ]
    out = _capture(render.dashboard(trained_only, {}, {}, source_label="real held-out eval"))
    assert "base baseline pending" in out.lower()  # headline names the missing side
    assert "pending" in out.lower()
    # Per-fault table still renders (run_id fallback) incl. wrong_file_edit.
    assert "Localization by fault type" in out
    assert "wrong_file_edit" in out
    # No fabricated base delta / no "0%→" base-vs-trained implication.
    assert "→" not in out


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


def test_style_constants_use_palette_hexes():
    # base=red / trained=green money-shot palette, shared with the TUI.
    assert render._GOOD == "bold #22C55E"
    assert render._BAD == "bold #EF4444"
    assert render._DIM == "#94A3B8"
