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


class _DetailLabel(Label):
    """Label subclass that exposes a ``renderable`` property.

    Textual >= 0.60 stores the content as ``Static.content`` rather than
    ``Static.renderable``.  The test suite (and the brief's API) references
    ``.renderable``; this thin wrapper re-exports it so the tests work
    regardless of which attribute the installed version uses.
    """

    @property
    def renderable(self):  # type: ignore[override]
        return self.content

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
                yield _DetailLabel("", id="detail")
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

    def _detail(self) -> _DetailLabel:
        return self.query_one("#detail", _DetailLabel)

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
