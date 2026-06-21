"""Rich static-render layer — the primary, CLI-agent-visible surface.

Every function returns a Rich renderable (never prints), so the same widgets can
later be embedded in a Textual app (the stretch interactive layer) without rework.
"""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from . import model as model_mod

_GOOD = "bold green"
_BAD = "bold red"
_DIM = "dim"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _signed(x: float, suffix: str = "") -> Text:
    """Signed delta with green/red coloring (positive = improvement)."""
    style = _GOOD if x > 0 else _BAD if x < 0 else _DIM
    sign = "+" if x > 0 else ""
    return Text(f"{sign}{x:.2f}{suffix}", style=style)


def _signed_tokens(delta: int) -> Text:
    """Token delta where FEWER is better (negative = cheaper = green)."""
    style = _GOOD if delta < 0 else _BAD if delta > 0 else _DIM
    sign = "+" if delta > 0 else ""
    return Text(f"{sign}{delta}", style=style)


def summary_table(base: model_mod.Aggregate, trained: model_mod.Aggregate) -> Table:
    """The money-shot: base vs trained vs Δ across every metric."""
    d = model_mod.delta(base, trained)
    t = Table(title="Base vs Trained Auditor  (held-out traces)", box=box.ROUNDED, title_style="bold")
    t.add_column("Metric"); t.add_column("Base", justify="right")
    t.add_column("Trained", justify="right"); t.add_column("Δ", justify="right")
    t.add_row("Localization accuracy", _pct(base.localization_accuracy), _pct(trained.localization_accuracy), _signed(d.localization_accuracy))
    t.add_row("Failure-type accuracy", _pct(base.failure_type_accuracy), _pct(trained.failure_type_accuracy), _signed(d.failure_type_accuracy))
    t.add_row("Mean explanation score", f"{base.mean_explanation_score:.2f}", f"{trained.mean_explanation_score:.2f}", _signed(d.mean_explanation_score))
    t.add_row("Mean reward", f"{base.mean_reward:.2f}", f"{trained.mean_reward:.2f}", _signed(d.mean_reward))
    t.add_row("Auditor tokens (total)", str(base.total_auditor_tokens), str(trained.total_auditor_tokens), _signed_tokens(d.total_auditor_tokens))
    return t


def token_chart(base: model_mod.Aggregate, trained: model_mod.Aggregate) -> Panel:
    """Honest audit-cost chart: auditor tokens spent (lower = cheaper audit).

    NOT framed as 'tokens saved' — there is no live-loop saving in the floor; the
    dramatic framing is reserved for the Design-Y gate head if it ever lands.
    """
    width = 34
    peak = max(base.total_auditor_tokens, trained.total_auditor_tokens, 1)
    rows = []
    for label, agg, style in (("base", base, "yellow"), ("trained", trained, "green")):
        filled = round(width * agg.total_auditor_tokens / peak)
        bar = Text("█" * filled, style=style) + Text("░" * (width - filled), style=_DIM)
        rows.append(Text(f"{label:>8}  ") + bar + Text(f"  {agg.total_auditor_tokens}"))
    audited = trained.total_trace_tokens  # same traces both models; report once
    rows.append(Text(f"\nTrace tokens audited (held-out set): {audited}", style=_DIM))
    return Panel(Group(*rows), title="Auditor token cost  (lower = cheaper audit)", box=box.ROUNDED)


def _verdict_correct(trace: dict, verdict: dict) -> bool:
    planted = model_mod.planted_step_id(trace)
    if planted is None:
        # Clean trace: correct iff the auditor reports no fault (schemas/verdict.json).
        return verdict.get("fault_present") is False
    return verdict.get("predicted_step_id") == planted


def _verdict_desc(verdict: dict) -> str:
    """Readable one-line summary of an auditor verdict (handles clean = nulls)."""
    if verdict.get("fault_present") is False:
        return "no fault"
    return f"{verdict.get('predicted_step_id')}  ({verdict.get('failure_type')})"


def trace_replay(trace: dict, verdicts: dict) -> Panel:
    """Trace replay with the planted-failure step highlighted, plus per-model calls."""
    planted = model_mod.planted_step_id(trace)
    tree = Tree(Text(f"{trace['run_id']}  ", style="bold") + Text(trace.get("task", ""), style=_DIM))
    for it in trace.get("iterations", []):
        branch = tree.add(Text(f"iteration {it['index']}", style="cyan"))
        for step in it.get("steps", []):
            sid = step["step_id"]
            label = Text(f"{sid}  ", style="bold")
            label.append(step["action_type"], style=_DIM)
            if step.get("tool_name"):
                label.append(f" · {step['tool_name']}", style=_DIM)
            if sid == planted:
                pf = trace["planted_failure"]
                label = Text("◆ ", style=_BAD) + label
                label.append(f"  ⟵ PLANTED FAULT: {pf['failure_type']}", style=_BAD)
            branch.add(label)
    if planted is None:
        tree.add(Text("✓ clean trace — no planted fault", style=_GOOD))
    # Per-model auditor calls for this trace.
    calls = []
    for tag in model_mod.MODELS:
        v = verdicts.get((trace["run_id"], tag))
        if not v:
            continue
        ok = _verdict_correct(trace, v)
        mark = Text("✓", style=_GOOD) if ok else Text("✗", style=_BAD)
        calls.append(mark + Text(f" {tag:>7}: ", style="bold") + Text(_verdict_desc(v)))
    body = [tree] + ([Text("")] + calls if calls else [])
    return Panel(Group(*body), box=box.ROUNDED)


def verdict_panel(trace: dict, verdicts: dict) -> Panel | None:
    """Side-by-side base vs trained explanation/fix for one trace (if sidecar present)."""
    base_v = verdicts.get((trace["run_id"], "base"))
    trained_v = verdicts.get((trace["run_id"], "trained"))
    if not base_v and not trained_v:
        return None
    t = Table(box=box.MINIMAL, show_header=True, expand=True)
    t.add_column("base", style="yellow", ratio=1); t.add_column("trained", style="green", ratio=1)
    t.add_row(
        (base_v or {}).get("explanation", "—"),
        (trained_v or {}).get("explanation", "—"),
    )
    t.add_row(
        Text("fix: " + ((base_v or {}).get("proposed_fix") or "—"), style=_DIM),
        Text("fix: " + ((trained_v or {}).get("proposed_fix") or "—"), style=_DIM),
    )
    return Panel(t, title=f"Verdict drill-down · {trace['run_id']}", box=box.ROUNDED)


def dashboard(eval_records: list[dict], verdicts: dict, traces: dict) -> RenderableType:
    """Assemble the full static report as one renderable."""
    by = model_mod.split_by_model(eval_records)
    base = model_mod.aggregate(by.get("base", []))
    trained = model_mod.aggregate(by.get("trained", []))
    blocks: list[RenderableType] = [
        Panel(Text("LOOPHOLE · Loop-Auditor Dashboard", style="bold magenta"), box=box.DOUBLE),
        summary_table(base, trained),
        token_chart(base, trained),
    ]
    for run_id in sorted(traces):
        trace = traces[run_id]
        blocks.append(trace_replay(trace, verdicts))
        vp = verdict_panel(trace, verdicts)
        if vp is not None:
            blocks.append(vp)
    return Group(*blocks)
