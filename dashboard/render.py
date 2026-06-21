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

_GOOD = "bold #22C55E"
_BAD = "bold #EF4444"
_DIM = "#94A3B8"


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


_PENDING = Text("— pending", style=_DIM)


def _missing(agg: model_mod.Aggregate) -> bool:
    """A side with no records — render it as "pending", never a fake 0% column."""
    return agg.n == 0


def _trained_buggy_localization(trained: model_mod.Aggregate, fault_rows: list) -> float:
    """Trained localization over BUGGY traces only (drives the 'every fault' claim)."""
    buggy = [r for r in fault_rows if r.fault_type != "clean"]
    bn = sum(r.n for r in buggy)
    return sum(r.trained_localization * r.n for r in buggy) / bn if bn else trained.localization_accuracy


def summary_table(base: model_mod.Aggregate, trained: model_mod.Aggregate) -> Table:
    """The money-shot: base vs trained vs Δ across every metric.

    Either side may be absent (n == 0) — e.g. a real trained-only run before the
    base baseline lands, or vice versa. An absent side's column (and the Δ) read
    "pending" instead of a misleading 0% / huge delta.
    """
    base_missing, trained_missing = _missing(base), _missing(trained)
    d = model_mod.delta(base, trained)
    t = Table(title="Base vs Trained Auditor  (held-out traces)", box=box.ROUNDED, title_style="bold")
    t.add_column("Metric"); t.add_column("Base", justify="right")
    t.add_column("Trained", justify="right"); t.add_column("Δ", justify="right")

    def row(label, base_str, trained_str, delta_cell):
        t.add_row(
            label,
            _PENDING if base_missing else base_str,
            _PENDING if trained_missing else trained_str,
            _PENDING if (base_missing or trained_missing) else delta_cell,
        )

    row("Localization accuracy", _pct(base.localization_accuracy), _pct(trained.localization_accuracy), _signed(d.localization_accuracy))
    row("Failure-type accuracy", _pct(base.failure_type_accuracy), _pct(trained.failure_type_accuracy), _signed(d.failure_type_accuracy))
    row("Mean explanation score", f"{base.mean_explanation_score:.2f}", f"{trained.mean_explanation_score:.2f}", _signed(d.mean_explanation_score))
    row("Mean reward", f"{base.mean_reward:.2f}", f"{trained.mean_reward:.2f}", _signed(d.mean_reward))
    row("Auditor tokens (total)", str(base.total_auditor_tokens), str(trained.total_auditor_tokens), _signed_tokens(d.total_auditor_tokens))
    return t


def headline(base: model_mod.Aggregate, trained: model_mod.Aggregate, fault_rows: list) -> Panel:
    """One-line takeaway banner — the conclusion before the detail.

    Honest framing: states only measured numbers. The "catches every planted fault"
    phrasing is used only when trained localization on BUGGY traces is actually 100%,
    and the "cheaper" claim only when a base baseline exists to compare against.
    """
    base_missing, trained_missing = _missing(base), _missing(trained)

    if base_missing and trained_missing:
        return Panel(Text("No eval records loaded.", style="bold"), box=box.HEAVY, border_style=_DIM)

    if trained_missing:  # base-only baseline, trained not yet run
        line1 = Text("Base auditor baseline — trained run pending", style="bold")
        line2 = Text(
            f"Localization {base.localization_accuracy:.0%} · reward {base.mean_reward:.2f} · "
            f"auditor tokens {base.total_auditor_tokens}",
            style=_DIM,
        )
        return Panel(Group(line1, line2), box=box.HEAVY, border_style=_DIM)

    trained_buggy = _trained_buggy_localization(trained, fault_rows)
    verdict = "catches every planted fault" if trained_buggy >= 0.999 else f"localizes {trained_buggy:.0%} of planted faults"

    if base_missing:  # trained-only real eval, base baseline not yet run
        line1 = Text("Trained auditor ", style="bold") + Text(verdict, style=_GOOD)
        line2 = Text(
            f"Localization {trained.localization_accuracy:.0%} · failure-type {trained.failure_type_accuracy:.0%} · "
            f"reward {trained.mean_reward:.2f} · base baseline pending",
            style=_DIM,
        )
        return Panel(Group(line1, line2), box=box.HEAVY, border_style=_GOOD)

    saving = (base.total_auditor_tokens - trained.total_auditor_tokens) / base.total_auditor_tokens if base.total_auditor_tokens else 0.0
    line1 = Text("Trained auditor ", style="bold") + Text(verdict, style=_GOOD)
    if saving > 0:
        line1 += Text(f" — and audits {saving:.0%} cheaper.", style="bold")
    d = trained.localization_accuracy - base.localization_accuracy
    line2 = Text(
        f"Localization {base.localization_accuracy:.0%}→{trained.localization_accuracy:.0%} "
        f"({'+' if d >= 0 else ''}{d * 100:.0f}pp) · reward {base.mean_reward:.2f}→{trained.mean_reward:.2f} · "
        f"auditor tokens −{saving:.0%}",
        style=_DIM,
    )
    return Panel(Group(line1, line2), box=box.HEAVY, border_style=_GOOD)


def per_fault_table(fault_rows: list) -> Table | None:
    """Localization accuracy broken out by ground-truth fault type (base vs trained).

    Returns None when no fault rows are available (no traces) so the caller can omit it.
    """
    if not fault_rows:
        return None
    t = Table(title="Localization by fault type", box=box.ROUNDED, title_style="bold")
    t.add_column("Fault type"); t.add_column("n", justify="right")
    t.add_column("Base", justify="right"); t.add_column("Trained", justify="right"); t.add_column("Δ", justify="right")
    for r in fault_rows:
        base_cell = _PENDING if r.base_n == 0 else _pct(r.base_localization)
        trained_cell = _PENDING if r.trained_n == 0 else _pct(r.trained_localization)
        delta_cell = _PENDING if (r.base_n == 0 or r.trained_n == 0) else _signed(r.delta)
        t.add_row(r.fault_type, str(r.n), base_cell, trained_cell, delta_cell)
    return t


def token_chart(base: model_mod.Aggregate, trained: model_mod.Aggregate) -> Panel:
    """Honest audit-cost chart: auditor tokens spent (lower = cheaper audit).

    NOT framed as 'tokens saved' — there is no live-loop saving in the floor; the
    dramatic framing is reserved for the Design-Y gate head if it ever lands.
    """
    width = 34
    peak = max(base.total_auditor_tokens, trained.total_auditor_tokens, 1)
    rows = []
    for label, agg, style in (("base", base, "#EF4444"), ("trained", trained, "#22C55E")):
        if _missing(agg):  # absent side: don't draw a zero-length "0" bar
            rows.append(Text(f"{label:>8}  ") + _PENDING)
            continue
        filled = round(width * agg.total_auditor_tokens / peak)
        bar = Text("█" * filled, style=style) + Text("░" * (width - filled), style=_DIM)
        rows.append(Text(f"{label:>8}  ") + bar + Text(f"  {agg.total_auditor_tokens}"))
    # Same traces audited by both models; report the cost basis once (whichever side
    # we have). The HUD eval doesn't attribute per-step tokens, so 0 reads as "n/a".
    audited = trained.total_trace_tokens or base.total_trace_tokens
    rows.append(Text(f"\nTrace tokens audited (held-out set): {audited or 'n/a'}", style=_DIM))
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
    t.add_column("base", style="#EF4444", ratio=1); t.add_column("trained", style="#22C55E", ratio=1)
    t.add_row(
        (base_v or {}).get("explanation", "—"),
        (trained_v or {}).get("explanation", "—"),
    )
    t.add_row(
        Text("fix: " + ((base_v or {}).get("proposed_fix") or "—"), style=_DIM),
        Text("fix: " + ((trained_v or {}).get("proposed_fix") or "—"), style=_DIM),
    )
    return Panel(t, title=f"Verdict drill-down · {trace['run_id']}", box=box.ROUNDED)


def _header(source_label: str | None) -> Panel:
    title = Text("LOOPHOLE · Loop-Auditor Dashboard", style="bold magenta")
    body = title if not source_label else Group(title, Text(source_label, style=_DIM))
    return Panel(body, box=box.DOUBLE)


def dashboard(eval_records: list[dict], verdicts: dict, traces: dict, source_label: str | None = None) -> RenderableType:
    """Assemble the full static report as one renderable.

    Money-shot first: header → headline takeaway → summary → per-fault breakdown →
    token cost, then the supporting per-trace replay/verdict detail. ``source_label``
    is an optional provenance subtitle (e.g. illustrative-fixtures vs real eval).
    """
    by = model_mod.split_by_model(eval_records)
    base = model_mod.aggregate(by.get("base", []))
    trained = model_mod.aggregate(by.get("trained", []))
    fault_rows = model_mod.per_fault_breakdown(eval_records, traces)
    blocks: list[RenderableType] = [
        _header(source_label),
        headline(base, trained, fault_rows),
        summary_table(base, trained),
    ]
    pf = per_fault_table(fault_rows)
    if pf is not None:
        blocks.append(pf)
    blocks.append(token_chart(base, trained))
    for run_id in sorted(traces):
        trace = traces[run_id]
        blocks.append(trace_replay(trace, verdicts))
        vp = verdict_panel(trace, verdicts)
        if vp is not None:
            blocks.append(vp)
    return Group(*blocks)
