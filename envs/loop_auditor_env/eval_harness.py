"""Base/trained eval over a taskset -> eval-result JSONL.

OWNER: Claude. Runs the auditor across a taskset, emits one record per trace
conforming to schemas/eval_result.json (§1.3), aggregates, and writes
config.EVAL_OUTPUT for Person 3's dashboard.

The record-building + aggregation helpers (build_eval_record, count_trace_tokens,
aggregate, write_jsonl) are pure and independently testable. Only run_eval's
auditor rollout is HUD-coupled:

!!! VERIFY @ Step 0: _run_auditor_once (run the auditor over one trace via HUD and
capture the verdict + auditor token usage), and the real held-out split source
(Person 1's dataset) instead of the local fixtures.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

try:  # package (pytest) | flat (hud `env:env`)
    from . import agent as agent_mod
    from . import config, judge
    from . import env as env_mod
    from . import reward as reward_mod
    from . import verdict as verdict_mod
except ImportError:
    import agent as agent_mod
    import config
    import judge
    import env as env_mod
    import reward as reward_mod
    import verdict as verdict_mod


def count_trace_tokens(trace: dict) -> int:
    """Sum ActionSpan.tokens across the trace (feeds eval-result trace_tokens)."""
    total = 0
    for it in trace.get("iterations", []) or []:
        for s in it.get("steps", []) or []:
            total += int(s.get("tokens", 0) or 0)
    return total


def build_eval_record(
    run_id: str,
    model_tag: str,
    raw_verdict,
    trace_view: dict,
    ground_truth,
    trace_tokens: int,
    auditor_tokens: int,
) -> dict:
    """Build one §1.3 eval-result record (pure). Mirrors env.score_verdict logic."""
    v = verdict_mod.validate_verdict(verdict_mod.parse_verdict(raw_verdict))
    if ground_truth is None:
        localization_correct = v["predicted_step_id"] == config.NO_FAULT_STEP_ID
        failure_type_correct = v["failure_type"] == config.NO_FAULT_TYPE
        explanation_score = 0.0
    else:
        localization_correct = v["predicted_step_id"] == ground_truth["step_id"]
        failure_type_correct = v["failure_type"] == ground_truth["failure_type"]
        explanation_score = (
            judge.score_explanation(trace_view, ground_truth, v.get("explanation", ""))
            if localization_correct
            else 0.0
        )
    rwd = reward_mod.compute_reward(v, ground_truth, explanation_score)
    return {
        "run_id": run_id,
        "model": model_tag,
        "localization_correct": bool(localization_correct),
        "failure_type_correct": bool(failure_type_correct),
        "explanation_score": float(explanation_score),
        "reward": float(rwd),
        "trace_tokens": int(trace_tokens),
        "auditor_tokens": int(auditor_tokens),
    }


def aggregate(records: list) -> dict:
    """Dashboard-facing aggregates over eval-result records (pure)."""
    n = len(records) or 1
    return {
        "n": len(records),
        "localization_accuracy": sum(r["localization_correct"] for r in records) / n,
        "failure_type_accuracy": sum(r["failure_type_correct"] for r in records) / n,
        "mean_explanation_score": statistics.fmean(r["explanation_score"] for r in records)
        if records
        else 0.0,
        "mean_reward": statistics.fmean(r["reward"] for r in records) if records else 0.0,
        "total_trace_tokens": sum(r["trace_tokens"] for r in records),
        "total_auditor_tokens": sum(r["auditor_tokens"] for r in records),
    }


def write_jsonl(records: list, path=None) -> Path:
    path = Path(path or config.EVAL_OUTPUT)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def _run_auditor_once(auditor, trace_view: dict):
    """Run the auditor over one trace via HUD; return (raw_verdict, auditor_tokens).

    !!! VERIFY @ Step 0 -- HUD-coupled. Placeholder until the SDK run path is confirmed.
    """
    raise NotImplementedError("VERIFY: wire HUD single-trace rollout + token accounting")


def run_eval(split: str = "heldout", model_tag: str = "base") -> dict:
    """Run the eval, write per-record JSONL, return aggregates.

    ``model_tag`` is one of {"base", "trained"} (eval_result.json enum).
    TODO: source ``split`` from Person 1's held-out dataset instead of fixtures.
    """
    traces = env_mod.load_fixture_traces()
    auditor = agent_mod.build_auditor_agent()
    records = []
    for trace in traces:
        trace_view, gt = env_mod.strip_ground_truth(trace)
        raw_verdict, auditor_tokens = _run_auditor_once(auditor, trace_view)  # VERIFY
        records.append(
            build_eval_record(
                trace["run_id"],
                model_tag,
                raw_verdict,
                trace_view,
                gt,
                count_trace_tokens(trace),
                auditor_tokens,
            )
        )
    write_jsonl(records)
    return aggregate(records)


if __name__ == "__main__":
    print(run_eval())
