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
