"""Pilot-driven tests for the Textual TUI. Skipped when Textual is absent."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from rich.console import Console

from dashboard import loader, model as model_mod
from dashboard.interactive import LoopholeTUI


def _build_app() -> LoopholeTUI:
    results_paths, verdicts_path, trace_paths = loader.bundled_fixture_paths()
    records = loader.load_eval_results(results_paths)
    verdicts = loader.load_verdicts(verdicts_path)
    traces = loader.load_traces(trace_paths)
    by = model_mod.split_by_model(records)
    base = model_mod.aggregate(by.get("base", []))
    trained = model_mod.aggregate(by.get("trained", []))
    return LoopholeTUI(base, trained, traces, verdicts)


def _detail_text(app: LoopholeTUI) -> str:
    console = Console(record=True, width=120)
    console.print(app.query_one("#detail").renderable)
    return console.export_text()


def test_sidebar_lists_summary_and_traces():
    async def scenario():
        app = _build_app()
        async with app.run_test():
            assert len(app.query_one("#sidebar")) == 4  # Summary + 3 traces

    asyncio.run(scenario())


def test_summary_is_default_view():
    async def scenario():
        app = _build_app()
        async with app.run_test():
            assert "Base vs Trained" in _detail_text(app)

    asyncio.run(scenario())


def test_selecting_trace_shows_planted_fault():
    async def scenario():
        app = _build_app()
        async with app.run_test() as pilot:
            app.query_one("#sidebar").index = 1  # first trace: buggy-resource-001
            await pilot.pause()
            assert "PLANTED FAULT" in _detail_text(app)

    asyncio.run(scenario())


def test_s_returns_to_summary():
    async def scenario():
        app = _build_app()
        async with app.run_test() as pilot:
            app.query_one("#sidebar").index = 1
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            assert "Base vs Trained" in _detail_text(app)

    asyncio.run(scenario())
