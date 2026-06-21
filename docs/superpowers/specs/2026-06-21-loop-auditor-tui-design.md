# Interactive Loop-Auditor TUI — Design

**Date:** 2026-06-21
**Status:** Approved (brainstorming) → ready for implementation plan
**Surface:** Interactive Textual TUI (first of two demo surfaces; a web UI follows
later). Built for a recorded walkthrough first, then a live demo.

## Goal

Turn the existing static Rich dashboard into a navigable, keyboard-driven terminal
app that is the hero of a recorded demo video (and later a live demo). The narrative
to land is the **money-shot**: a base auditor vs. a trained auditor on held-out
traces — the trained auditor localizes the planted fault, classifies it correctly,
and audits more cheaply.

## Context / what already exists

- `dashboard/loader.py` — schema-validated ingestion (pure, reusable trust boundary).
- `dashboard/model.py` — pure aggregation + base-vs-trained deltas. No I/O, no Rich.
- `dashboard/render.py` — **returns Rich renderables, never prints**, explicitly so
  the same widgets can be embedded in a Textual app without rework
  (`summary_table`, `token_chart`, `trace_replay`, `verdict_panel`, `dashboard`).
- `dashboard/__main__.py` — already contains the plug-in hook:
  `from .interactive import run_interactive`, with a fallback to the static render
  when Textual is absent or stdout is not a TTY.

The TUI is therefore a **navigation shell** over assets that already exist, not a
rewrite. The pure layers (`loader`, `model`) and the Rich widgets (`render`) are
reused unchanged.

## Approach (chosen: "A — Textual shell")

Wrap the existing Rich renderables in a Textual app. Rejected alternatives:
- **B — custom Textual widgets + CSS:** best-looking but ~2–3× the build and
  duplicates the panels `render.py` already draws. Better reserved for the web UI.
- **C — scrollable pager:** trivial but not meaningfully interactive; won't sell a
  live demo.

## Architecture

New module `dashboard/interactive.py` exporting `run_interactive(args) -> int`
(the function `__main__.py` already imports lazily).

One small supporting refactor: promote `_resolve_inputs(args)` out of `__main__.py`
into `loader.py` as public `resolve_inputs(args)`, so the static path and the TUI
path share one copy of the input-resolution logic instead of duplicating CLI
parsing. `__main__.run_static` is updated to call `loader.resolve_inputs`.

Textual becomes an **optional** dependency: an `[interactive]` extra in
`dashboard/pyproject.toml`. The existing fallback-to-static-if-missing in
`__main__.py` is preserved, so nothing breaks when Textual is not installed.

## Components & layout

`LoopholeApp(App)`:

```
┌─ LOOPHOLE · Loop-Auditor ─────────────────────────┐   ← Header
│ Traces         │  Base vs Trained  (held-out)      │
│ ▸ Summary      │  Localization  33% → 100%   +.67  │
│   ✓ resource-001│  Reward        0.50 → 1.47  +.97 │
│   ✓ routing-002 │  Tokens         670 →  410  -260 │
│   ✓ clean-003   │  [token cost bar chart]          │
│   (ListView)   │  (VerticalScroll > Static)        │
├───────────────────────────────────────────────────┤
│ ↑↓/jk nav   ↵ open   s summary   q quit            │   ← Footer
└───────────────────────────────────────────────────┘
```

- `Header` — title bar.
- `Footer` — auto-renders the keybindings (so viewers/judges see the controls on
  camera).
- Horizontal split:
  - **Left** `ListView` (~28 cols): first row `Summary`, then one row per trace
    (sorted `run_id`), each prefixed with the trained auditor's ✓/✗ correctness
    marker.
  - **Right** `VerticalScroll` containing a `Static` whose renderable is swapped on
    selection.
- Detail content (all sourced unchanged from `render.py`):
  - **Summary** selected → `Group(summary_table(base, trained), token_chart(base, trained))`.
  - **Trace** selected → `Group(trace_replay(trace, verdicts), verdict_panel(trace, verdicts))`.
    When `verdict_panel` returns `None` (no sidecar), show a dim
    "no verdict sidecar" note in its place.

## Data flow

`run_interactive(args)`:
1. `results, verdicts_path, traces = loader.resolve_inputs(args)`
2. Load + validate via `loader.load_eval_results / load_verdicts / load_traces`
   (identical to the static path).
3. On load error (`ValidationError | FileNotFoundError | ValueError`): print the
   same red `Failed to load dashboard inputs: …` message and `return 1`
   **without** launching the TUI.
4. Build aggregates (`model.split_by_model` → `model.aggregate` for base/trained),
   pass `traces` (sorted), `verdicts`, and the two aggregates into the app.
5. `app.run()`; `return 0`.

Highlighting a list item swaps the detail renderable via a dict lookup — no
recomputation.

## Keybindings

| Key            | Action                          |
|----------------|---------------------------------|
| `↑` / `↓`, `j` / `k` | move selection             |
| `s`            | jump to Summary                 |
| `enter`        | scroll detail pane to top       |
| `q` / `ctrl+c` | quit                            |

No auto-play / timed advance — the narrator drives the demo.

## Error handling

- **Textual not installed** → `__main__` import fails → existing static fallback.
- **Not a TTY** (piped/captured, e.g. inside a CLI agent) → static render (Textual
  needs a real terminal). Existing `__main__` gate covers this.
- **No verdict sidecar** → `verdict_panel` already returns `None`; show the dim note.
- **Empty trace set** → Summary-only (list has just the Summary row).

## Styling

A small inline CSS string (or `.tcss`): left/right pane widths, panel borders, and
the highlight color for the selected `ListView` row. Kept intentionally minimal —
the visual weight lives in the reused Rich renderables.

## Testing

- New `dashboard/tests/test_interactive.py` using Textual's `App.run_test()` pilot,
  **skipped when Textual is absent** (`pytest.importorskip("textual")`):
  - App mounts on the bundled fixtures; the `ListView` has `Summary` + 3 trace rows.
  - Selecting a trace puts that `run_id` and `PLANTED FAULT` into the detail pane.
  - Pressing `s` brings back `Base vs Trained` in the detail pane.
- Pure layers (`model`, `loader`) and the static render smoke test remain covered by
  existing tests — unchanged.

## Wiring / packaging

- `dashboard/pyproject.toml`: add `[project.optional-dependencies] interactive = ["textual>=0.60"]`
  (pin to a current stable line; finalize exact floor at implementation).
- `scripts/run_demo.sh`: add a `--tui` mode that launches the interactive app on the
  bundled fixtures (`python -m dashboard` with no `--render`).
- `dashboard/README.md`: document the interactive launch and the new extra.

## Out of scope (this spec)

- The web UI (separate, follows this work — shares `loader`/`model`).
- Native custom Textual widgets / animations (approach B).
- Any change to reward semantics, eval harness, or the frozen schemas.
