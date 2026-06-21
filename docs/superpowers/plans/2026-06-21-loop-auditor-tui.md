# Interactive Loop-Auditor TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a navigable, keyboard-driven Textual TUI to the Loop-Auditor dashboard that wraps the existing Rich renderables — the first of two demo surfaces (recorded, then live).

**Architecture:** A thin Textual shell (`dashboard/interactive.py`) over the existing pure layers. `loader` loads/validates, `model` aggregates, and `render.py`'s renderables drop straight into a Textual `Static`. Input resolution moves into `loader.resolve_inputs` so the static and TUI paths share one copy. Textual stays an optional extra; the static path remains dependency-free.

**Tech Stack:** Python ≥3.11, Rich (existing), Textual (optional `[interactive]` extra), pytest. No dependency on `loop_auditor_env`.

## Global Constraints

- Python `requires-python = ">=3.11"` (do not lower).
- Textual is an **optional** dependency only: `[project.optional-dependencies] interactive = ["textual>=0.60"]` (already present in `dashboard/pyproject.toml`). The static render must still import and run with Textual absent.
- No new runtime dependency in the base `dependencies` list (keep `rich>=13.7`, `jsonschema>=4.0` only).
- No `import` of `loop_auditor_env` anywhere in `dashboard/`.
- All external records remain schema-validated via `loader` before rendering — do not bypass it.
- Palette (dark slate "Developer Tool / IDE"), applied consistently — green only ever means improvement/correct, red only ever means regression/miss:
  - background `#0F172A`, card/panel `#1B2336`, foreground `#F8FAFC`, muted `#94A3B8`, border `#475569`, accent/success `#22C55E`, destructive/miss `#EF4444`.
  - base column/series = `#EF4444` (red), trained column/series = `#22C55E` (green).
- All commands run from inside `dashboard/` (its `pyproject.toml` sets `pythonpath = [".."]`, `testpaths = ["tests"]`). Use the venv at `dashboard/.venv`.

---

### Task 1: Share input resolution via `loader.resolve_inputs`

Move the `_resolve_inputs` helper out of `__main__.py` into `loader.py` as a public function so both the static and TUI entry points use one copy.

**Files:**
- Modify: `dashboard/loader.py` (add `resolve_inputs`)
- Modify: `dashboard/__main__.py` (delete local `_resolve_inputs`, call `loader.resolve_inputs`, drop now-unused `Path` import)
- Test: `dashboard/tests/test_loader.py` (append two tests)

**Interfaces:**
- Produces: `loader.resolve_inputs(args) -> tuple[list[Path], Path, list[Path]]` — given an `argparse.Namespace` with attributes `mock: bool`, `results: list[str] | None`, `verdicts: str | None`, `traces: str | None`, returns `(results_paths, verdicts_path, trace_paths)`. When `args.mock` or no `args.results`, returns `loader.bundled_fixture_paths()`. A missing `--verdicts` yields `Path("/nonexistent")` (loader treats it as the optional-absent sidecar).

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests/test_loader.py`:

```python
import argparse

from dashboard import loader


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest tests/test_loader.py -k resolve_inputs -v`
Expected: FAIL with `AttributeError: module 'dashboard.loader' has no attribute 'resolve_inputs'`

- [ ] **Step 3: Add `resolve_inputs` to `loader.py`**

Append to `dashboard/loader.py` (it already imports `Path`):

```python
def resolve_inputs(args):
    """Map parsed CLI args to (results_paths, verdicts_path, trace_paths).

    Shared by the static (--render) and interactive (TUI) entry points. Falls
    back to the bundled --mock fixtures when no explicit results are given.
    """
    if args.mock or not args.results:
        return bundled_fixture_paths()
    results = [Path(p) for p in args.results]
    verdicts = Path(args.verdicts) if args.verdicts else Path("/nonexistent")  # optional
    traces: list[Path] = []
    if args.traces:
        tp = Path(args.traces)
        traces = sorted(tp.glob("*.json")) if tp.is_dir() else [tp]
    return results, verdicts, traces
```

- [ ] **Step 4: Point `__main__.py` at the shared helper**

In `dashboard/__main__.py`, delete the entire local `_resolve_inputs` function and remove the now-unused `from pathlib import Path` import line. Change the first line of `run_static` from:

```python
    results_paths, verdicts_path, trace_paths = _resolve_inputs(args)
```

to:

```python
    results_paths, verdicts_path, trace_paths = loader.resolve_inputs(args)
```

- [ ] **Step 5: Run loader + main-path tests to verify they pass**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest tests/test_loader.py -v && .venv/bin/python -m dashboard --render --mock | head -3`
Expected: all loader tests PASS; the static render still prints the `LOOPHOLE · Loop-Auditor Dashboard` banner (proves `__main__` still resolves inputs).

- [ ] **Step 6: Commit**

```bash
cd ~/LoopHole && git add dashboard/loader.py dashboard/__main__.py dashboard/tests/test_loader.py
git commit -m "Share dashboard input resolution via loader.resolve_inputs"
```

---

### Task 2: Align render colors to the palette

Shift the shared Rich style constants and the base/trained series colors to the exact palette hexes so the static render and the TUI look identical and tell one base=red / trained=green story. Text-fact render tests are unaffected (they assert on text, not styles).

**Files:**
- Modify: `dashboard/render.py:18-20` (the `_GOOD`/`_BAD`/`_DIM` constants), `dashboard/render.py:64` (`token_chart` series colors), `dashboard/render.py:127` (`verdict_panel` column styles)
- Test: `dashboard/tests/test_render.py` (append one constants test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `render._GOOD == "bold #22C55E"`, `render._BAD == "bold #EF4444"`, `render._DIM == "#94A3B8"` (relied on by the TUI's visual consistency, not imported elsewhere).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_render.py`:

```python
def test_style_constants_use_palette_hexes():
    # base=red / trained=green money-shot palette, shared with the TUI.
    assert render._GOOD == "bold #22C55E"
    assert render._BAD == "bold #EF4444"
    assert render._DIM == "#94A3B8"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest tests/test_render.py::test_style_constants_use_palette_hexes -v`
Expected: FAIL with `assert 'bold green' == 'bold #22C55E'`

- [ ] **Step 3: Update the constants and series colors in `render.py`**

Replace lines 18-20:

```python
_GOOD = "bold #22C55E"
_BAD = "bold #EF4444"
_DIM = "#94A3B8"
```

In `token_chart`, change the series row tuple (line ~64) from:

```python
    for label, agg, style in (("base", base, "yellow"), ("trained", trained, "green")):
```

to:

```python
    for label, agg, style in (("base", base, "#EF4444"), ("trained", trained, "#22C55E")):
```

In `verdict_panel`, change the column styles (line ~127) from:

```python
    t.add_column("base", style="yellow", ratio=1); t.add_column("trained", style="green", ratio=1)
```

to:

```python
    t.add_column("base", style="#EF4444", ratio=1); t.add_column("trained", style="#22C55E", ratio=1)
```

- [ ] **Step 4: Run the render tests to verify they pass**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest tests/test_render.py -v`
Expected: all render tests PASS (text-fact assertions unaffected by color changes).

- [ ] **Step 5: Commit**

```bash
cd ~/LoopHole && git add dashboard/render.py dashboard/tests/test_render.py
git commit -m "Align dashboard render colors to the slate base=red/trained=green palette"
```

---

### Task 3: Build the interactive Textual app

Create `dashboard/interactive.py`: the `LoopholeTUI` app plus the `run_interactive(args)` entry point that `__main__.py` already imports lazily.

**Files:**
- Create: `dashboard/interactive.py`
- Test: `dashboard/tests/test_interactive.py`

**Interfaces:**
- Consumes: `loader.resolve_inputs`, `loader.load_eval_results`, `loader.load_verdicts`, `loader.load_traces`, `loader.bundled_fixture_paths` (Task 1); `model.split_by_model`, `model.aggregate`, `model.Aggregate`; `render.summary_table`, `render.token_chart`, `render.trace_replay`, `render.verdict_panel`, `render._verdict_correct`.
- Produces:
  - `LoopholeTUI(base: model.Aggregate, trained: model.Aggregate, traces: dict[str, dict], verdicts: dict) -> textual.app.App` — sidebar `ListView` (id `sidebar`) with a `Summary` row plus one row per sorted `run_id`; detail `Static` (id `detail`) inside a `VerticalScroll` (id `detail-scroll`). Highlighting the `Summary` row shows the money-shot; highlighting a trace row shows that trace's replay + verdict panel.
  - `run_interactive(args) -> int` — loads inputs (same as static), returns `1` on load error without launching, else runs the app and returns `0`.

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/test_interactive.py`:

```python
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
```

- [ ] **Step 2: Ensure Textual is installed in the dev venv, then run the tests to verify they fail**

Run: `cd ~/LoopHole/dashboard && .venv/bin/pip install -q "textual>=0.60" && .venv/bin/python -m pytest tests/test_interactive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard.interactive'`

- [ ] **Step 3: Create `dashboard/interactive.py`**

```python
"""Interactive Textual TUI — the live/recorded demo surface.

A thin navigation shell over the existing pure layers: it reuses render.py's
Rich renderables verbatim inside a Textual Static, so the static and interactive
surfaces stay identical. Textual is an optional dependency; __main__ falls back
to the static render when it is absent or stdout is not a TTY.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Label, ListItem, ListView

from . import loader, model as model_mod, render

# Dark slate "Developer Tool / IDE" palette (see the design spec).
_BG = "#0F172A"
_CARD = "#1B2336"
_BORDER = "#475569"
_ACCENT = "#22C55E"

_CSS = f"""
Screen {{ background: {_BG}; }}
#sidebar {{ width: 30; border-right: solid {_BORDER}; background: {_BG}; }}
#sidebar > ListItem {{ color: #F8FAFC; padding: 0 1; }}
#sidebar > ListItem.--highlight {{ background: {_CARD}; }}
#sidebar:focus > ListItem.--highlight {{ background: {_ACCENT}; color: {_BG}; }}
#detail-scroll {{ background: {_BG}; }}
#detail {{ padding: 1 2; background: {_BG}; }}
"""


class LoopholeTUI(App):
    """Base-vs-trained auditor dashboard, navigable by keyboard."""

    CSS = _CSS
    TITLE = "LOOPHOLE · Loop-Auditor"
    BINDINGS = [
        Binding("s", "summary", "summary"),
        Binding("enter", "scroll_top", "open"),
        Binding("j", "cursor_down", "down", show=False),
        Binding("k", "cursor_up", "up", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, base, trained, traces, verdicts) -> None:
        super().__init__()
        self._base = base
        self._trained = trained
        self._traces = traces
        self._verdicts = verdicts
        self._run_ids = sorted(traces)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="sidebar")
            with VerticalScroll(id="detail-scroll"):
                yield Label("", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        lv = self.query_one("#sidebar", ListView)
        lv.append(ListItem(Label("▸ Summary")))
        for rid in self._run_ids:
            lv.append(ListItem(Label(f"{self._trained_mark(rid)} {rid}")))
        lv.index = 0
        lv.focus()
        self._show_summary()

    # --- selection -> detail ------------------------------------------------
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = self.query_one("#sidebar", ListView).index
        if idx is None or idx == 0:
            self._show_summary()
        else:
            self._show_trace(self._run_ids[idx - 1])

    def _detail(self) -> Label:
        return self.query_one("#detail", Label)

    def _show_summary(self) -> None:
        self._detail().update(
            Group(
                render.summary_table(self._base, self._trained),
                render.token_chart(self._base, self._trained),
            )
        )

    def _show_trace(self, run_id: str) -> None:
        trace = self._traces[run_id]
        parts = [render.trace_replay(trace, self._verdicts)]
        panel = render.verdict_panel(trace, self._verdicts)
        parts.append(panel if panel is not None
                     else Text("no verdict sidecar for this trace", style="#94A3B8"))
        self._detail().update(Group(*parts))

    def _trained_mark(self, run_id: str) -> str:
        v = self._verdicts.get((run_id, "trained"))
        if not v:
            return "·"
        return "✓" if render._verdict_correct(self._traces[run_id], v) else "✗"

    # --- actions ------------------------------------------------------------
    def action_summary(self) -> None:
        self.query_one("#sidebar", ListView).index = 0

    def action_scroll_top(self) -> None:
        self.query_one("#detail-scroll", VerticalScroll).scroll_home(animate=False)

    def action_cursor_down(self) -> None:
        self.query_one("#sidebar", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#sidebar", ListView).action_cursor_up()


def run_interactive(args) -> int:
    """Load inputs (same as the static path) and launch the TUI."""
    console = Console()
    results_paths, verdicts_path, trace_paths = loader.resolve_inputs(args)
    try:
        records = loader.load_eval_results(results_paths)
        verdicts = loader.load_verdicts(verdicts_path)
        traces = loader.load_traces(trace_paths)
    except (loader.ValidationError, FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Failed to load dashboard inputs:[/] {exc}")
        return 1
    by = model_mod.split_by_model(records)
    base = model_mod.aggregate(by.get("base", []))
    trained = model_mod.aggregate(by.get("trained", []))
    LoopholeTUI(base, trained, traces, verdicts).run()
    return 0
```

Note on the detail widget: a `Label` accepts any Rich renderable via `.update()` and is the simplest container for the reused panels. If the installed Textual version styles the highlighted list row under a different class than `.--highlight`, that selector is purely cosmetic — the tests assert behavior, not the highlight color.

- [ ] **Step 4: Run the interactive tests to verify they pass**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest tests/test_interactive.py -v`
Expected: all four tests PASS.

- [ ] **Step 5: Run the full dashboard test suite (no regressions)**

Run: `cd ~/LoopHole/dashboard && .venv/bin/python -m pytest -q`
Expected: all tests PASS (loader, model, render, interactive).

- [ ] **Step 6: Smoke-launch the TUI manually (optional but recommended)**

Run: `cd ~/LoopHole && dashboard/.venv/bin/python -m dashboard` (in a real terminal)
Expected: the TUI opens on the Summary money-shot; `↑/↓` move between traces, `s` returns to Summary, `q` quits. (Skip if not in an interactive terminal — it will fall back to the static render.)

- [ ] **Step 7: Commit**

```bash
cd ~/LoopHole && git add dashboard/interactive.py dashboard/tests/test_interactive.py
git commit -m "Add interactive Textual TUI wrapping the Rich dashboard widgets"
```

---

### Task 4: Wire up the demo launch and document it

Add a `--tui` mode to the demo script and document the interactive launch. The `interactive` extra already exists in `pyproject.toml`, so no packaging change is required.

**Files:**
- Modify: `scripts/run_demo.sh` (add a `--tui` case)
- Modify: `dashboard/README.md` (document the interactive launch)

**Interfaces:**
- Consumes: `python -m dashboard` (no `--render`) launches the TUI when stdout is a TTY and Textual is installed.
- Produces: `./scripts/run_demo.sh --tui` launches the interactive dashboard on the bundled fixtures.

- [ ] **Step 1: Add the `--tui` case to `run_demo.sh`**

In `scripts/run_demo.sh`, add this function next to `render_mock`:

```bash
render_tui() {
  echo ">> [tui] launching interactive dashboard on bundled fixtures"
  # No --render -> __main__ launches the Textual TUI (needs a real terminal;
  # falls back to the static render if Textual is absent or stdout isn't a TTY).
  "$DASH_PY" -m dashboard --mock
}
```

And add `--tui` to the `case "$MODE"` block:

```bash
case "$MODE" in
  --mock|"") render_mock ;;
  --tui)     render_tui ;;
  --real)    render_real ;;
  *) echo "usage: $0 [--mock|--tui|--real]" >&2; exit 2 ;;
esac
```

- [ ] **Step 2: Document the interactive launch in `dashboard/README.md`**

Under the `## Run` section (after the mock render block), add:

````markdown
### Interactive TUI (demo surface)

Needs a real terminal (not visible inside a CLI agent pane). Install the extra,
then launch with no `--render` flag:

```bash
dashboard/.venv/bin/pip install -e '.[interactive]'   # or: pip install 'textual>=0.60'
dashboard/.venv/bin/python -m dashboard               # opens the TUI on bundled fixtures
# or:
./scripts/run_demo.sh --tui
```

Keys: `↑/↓` (or `j`/`k`) move between Summary and traces · `s` jump to Summary ·
`enter` scroll the detail pane to top · `q` quit. The TUI reuses the exact same
Rich panels as the static render, so the two surfaces look identical.
````

- [ ] **Step 3: Verify the script and docs**

Run: `cd ~/LoopHole && bash scripts/run_demo.sh --tui < /dev/null | head -3`
Expected: with stdin not a TTY it falls back to the static render and prints the `LOOPHOLE · Loop-Auditor Dashboard` banner (proves the `--tui` path is wired and the fallback works). In a real terminal the TUI opens instead.

- [ ] **Step 4: Commit**

```bash
cd ~/LoopHole && git add scripts/run_demo.sh dashboard/README.md
git commit -m "Wire --tui demo launch and document the interactive dashboard"
```

---

## Self-Review

**Spec coverage:**
- Architecture / `run_interactive` hook → Task 3. ✓
- `loader.resolve_inputs` refactor → Task 1. ✓
- Components & layout (sidebar ListView + Summary row + detail Static) → Task 3. ✓
- Data flow (load like static, return 1 on error without launching) → Task 3 `run_interactive`. ✓
- Keybindings (↑↓/jk, s, enter, q) → Task 3 BINDINGS + actions. ✓
- Error handling: Textual absent / not a TTY → existing `__main__` fallback (verified in Task 4 Step 3); no sidecar → `_show_trace` dim note (Task 3); empty traces → Summary-only (sidebar built from `self._run_ids`). ✓
- Styling & palette → Task 2 (render constants) + Task 3 (`_CSS`). ✓
- Visual hierarchy: Summary is default view on launch → Task 3 `on_mount` + `test_summary_is_default_view`. ✓
- Testing (pilot tests, skip if Textual absent) → Task 3. ✓
- Wiring (pyproject extra already present; run_demo.sh `--tui`; README) → Task 4. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. ✓

**Type consistency:** `LoopholeTUI(base, trained, traces, verdicts)` constructor signature matches its use in both `run_interactive` and `test_interactive._build_app`. Widget ids (`sidebar`, `detail`, `detail-scroll`) are consistent between `compose`, `on_mount`, the action handlers, and the tests. `loader.resolve_inputs` signature/return matches its callers in `__main__.run_static` and `run_interactive`. ✓
