"""Pure aggregation + base-vs-trained delta layer — the analytical core.

No Rich/Textual, no I/O, no loop_auditor_env. Records are plain dicts already
validated against schemas/eval_result.json by the loader, so this layer trusts
its inputs and stays trivially testable.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Record key names (mirror schemas/eval_result.json §1.3).
MODELS = ("base", "trained")


@dataclass(frozen=True)
class Aggregate:
    """Per-model rollup over eval-result records (immutable)."""

    n: int
    localization_accuracy: float
    failure_type_accuracy: float
    mean_explanation_score: float
    mean_reward: float
    total_trace_tokens: int
    total_auditor_tokens: int


@dataclass(frozen=True)
class Delta:
    """trained - base, field by field. Positive = trained improved.

    For token totals, negative means trained spent FEWER tokens (an honest saving).
    """

    localization_accuracy: float
    failure_type_accuracy: float
    mean_explanation_score: float
    mean_reward: float
    total_trace_tokens: int
    total_auditor_tokens: int


def split_by_model(records: list[dict]) -> dict[str, list[dict]]:
    """Group eval-result records by their ``model`` tag (e.g. base/trained)."""
    out: dict[str, list[dict]] = {}
    for r in records:
        out.setdefault(r["model"], []).append(r)
    return out


def aggregate(records: list[dict]) -> Aggregate:
    """Reduce a list of eval-result records to a single immutable rollup.

    Empty input is safe and yields all-zero fields (so an absent model never
    crashes the dashboard).
    """
    n = len(records)
    if n == 0:
        return Aggregate(0, 0.0, 0.0, 0.0, 0.0, 0, 0)
    return Aggregate(
        n=n,
        localization_accuracy=sum(bool(r["localization_correct"]) for r in records) / n,
        failure_type_accuracy=sum(bool(r["failure_type_correct"]) for r in records) / n,
        mean_explanation_score=statistics.fmean(float(r["explanation_score"]) for r in records),
        mean_reward=statistics.fmean(float(r["reward"]) for r in records),
        total_trace_tokens=sum(int(r["trace_tokens"]) for r in records),
        total_auditor_tokens=sum(int(r["auditor_tokens"]) for r in records),
    )


def delta(base: Aggregate, trained: Aggregate) -> Delta:
    """Compute trained-minus-base across every aggregate field."""
    return Delta(
        localization_accuracy=trained.localization_accuracy - base.localization_accuracy,
        failure_type_accuracy=trained.failure_type_accuracy - base.failure_type_accuracy,
        mean_explanation_score=trained.mean_explanation_score - base.mean_explanation_score,
        mean_reward=trained.mean_reward - base.mean_reward,
        total_trace_tokens=trained.total_trace_tokens - base.total_trace_tokens,
        total_auditor_tokens=trained.total_auditor_tokens - base.total_auditor_tokens,
    )


def planted_step_id(trace: dict) -> str | None:
    """The ground-truth faulty step_id for a trace, or None for a clean trace."""
    pf = trace.get("planted_failure")
    if not pf:
        return None
    return pf.get("step_id")


def fault_type(trace: dict) -> str:
    """The trace's ground-truth fault type, or 'clean' when no fault is planted."""
    pf = trace.get("planted_failure")
    return pf.get("failure_type", "clean") if pf else "clean"


@dataclass(frozen=True)
class FaultRow:
    """Per-fault-type base-vs-trained localization rollup (immutable)."""

    fault_type: str
    n: int                       # distinct traces of this fault type
    base_localization: float
    trained_localization: float
    base_n: int = 0              # base records for this fault (0 => base side pending)
    trained_n: int = 0           # trained records for this fault (0 => trained pending)

    @property
    def delta(self) -> float:
        return self.trained_localization - self.base_localization


# 'clean' sorts last; faults keep a stable, demo-legible order.
_FAULT_ORDER = ("routing", "resource_misuse", "tool_misuse", "wrong_file_edit", "safety", "clean")
_KNOWN_FAULTS = frozenset(_FAULT_ORDER)


def _fault_type_for(run_id: str, trace: dict | None) -> str | None:
    """Fault type for a record: the trace's ground truth when present, else the
    `<task>__<fault>` run_id convention (so the real HUD eval — which ships no
    traces — still groups). Returns None when neither yields a known fault type."""
    if trace is not None:
        return fault_type(trace)
    if "__" in run_id:
        suffix = run_id.rsplit("__", 1)[1]
        if suffix in _KNOWN_FAULTS:
            return suffix
    return None


def per_fault_breakdown(records: list[dict], traces: dict[str, dict]) -> list[FaultRow]:
    """Group localization accuracy by ground-truth fault type, base vs trained.

    Fault type per record comes from its trace's planted_failure when available,
    else the `<task>__<fault>` run_id convention (real HUD eval ships no traces).
    Records whose fault type can't be determined are skipped; returns [] when none
    can be grouped (the dashboard then omits the per-fault table).
    """
    # fault_type -> model -> [correct_bools]
    buckets: dict[str, dict[str, list[bool]]] = {}
    for r in records:
        ft = _fault_type_for(r["run_id"], traces.get(r["run_id"]))
        if ft is None:
            continue
        buckets.setdefault(ft, {}).setdefault(r["model"], []).append(bool(r["localization_correct"]))

    def _acc(hits: list[bool]) -> float:
        return sum(hits) / len(hits) if hits else 0.0

    rows: list[FaultRow] = []
    for ft in sorted(buckets, key=lambda f: (_FAULT_ORDER.index(f) if f in _FAULT_ORDER else len(_FAULT_ORDER), f)):
        per_model = buckets[ft]
        base, trained = per_model.get("base", []), per_model.get("trained", [])
        n = max(len(base), len(trained))
        rows.append(FaultRow(ft, n, _acc(base), _acc(trained), base_n=len(base), trained_n=len(trained)))
    return rows
