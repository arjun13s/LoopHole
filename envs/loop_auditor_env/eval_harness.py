"""Base/trained eval over a taskset -> eval-result JSONL.

OWNER: Claude. Runs the auditor across the env's audit scenarios, emits one
record per trace conforming to schemas/eval_result.json (§1.3), aggregates, and
writes config.EVAL_OUTPUT for Person 3's dashboard.

The record-building + aggregation helpers (build_eval_record, count_trace_tokens,
aggregate, write_jsonl) are pure and independently testable. ``run_eval`` /
``_run_auditor_once`` are HUD-coupled: they drive each audit Task through
``Task.run(agent)`` (hud 0.6.x), read the auditor's final verdict off the run's
Trace, and sum the agent turns' token usage. The trace source is the env's
loaded dataset (``config.DATASET`` -> ``env._SCENARIOS``), so the eval runs the
same tasks the env serves; to eval the held-out split, serve the env with
``LOOP_AUDITOR_DATASET=heldout``.
"""

from __future__ import annotations

import asyncio
import json
import os
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
    """Build one §1.3 eval-result record (pure). Mirrors env.score_verdict logic.

    A malformed/empty verdict (a real model can emit either) yields a zero
    record instead of crashing the eval -- the same forgiveness env.score_verdict
    applies during a live rollout.
    """
    try:
        v = verdict_mod.validate_verdict(verdict_mod.parse_verdict(raw_verdict))
    except (ValueError, TypeError):
        return {
            "run_id": run_id,
            "model": model_tag,
            "localization_correct": False,
            "failure_type_correct": False,
            "explanation_score": 0.0,
            "reward": 0.0,
            "trace_tokens": int(trace_tokens),
            "auditor_tokens": int(auditor_tokens),
        }
    if ground_truth is None:
        localization_correct = v.get("fault_present") is False
        failure_type_correct = v.get("failure_type") is None
        explanation_score = 0.0
    else:
        localization_correct = (
            v.get("fault_present") is True
            and v["predicted_step_id"] == ground_truth["step_id"]
        )
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


def _final_verdict_text(trace) -> str:
    """The newest agent turn that produced non-empty assistant text (the verdict).

    A trailing turn may be a tool call with no content; ``Trace.final`` walks
    newest-first and skips ``None``, so we map empty content to ``None`` to get
    the last turn that actually spoke.
    """
    from hud.agents.types import AgentStep

    text = trace.final(
        lambda s: s.content if isinstance(s, AgentStep) and s.content else None
    )
    return text or ""


def _auditor_tokens(trace) -> int:
    """Sum prompt+completion tokens over the auditor's agent turns (Usage)."""
    from hud.agents.types import AgentStep

    def per_step(s):
        if isinstance(s, AgentStep) and s.usage is not None:
            return (s.usage.prompt_tokens or 0) + (s.usage.completion_tokens or 0)
        return None

    return sum(trace.collect(per_step))


async def _run_auditor_once(auditor, task):
    """Run the auditor over one audit Task via HUD; return (raw_verdict, auditor_tokens).

    Drives the task through ``Task.run(agent)`` (hud 0.6.x): the env serves the
    trace summary + inspection tools, the agent investigates and emits its verdict
    as the final assistant message. We read that message back off the run's Trace
    and sum the agent turns' token usage. A run that never produced text (failed
    or empty) yields ("", 0), which build_eval_record scores as 0.
    """
    job = await task.run(auditor)
    runs = getattr(job, "runs", None) or []
    if not runs:
        return "", 0
    trace = runs[0].trace
    return _final_verdict_text(trace), _auditor_tokens(trace)


async def run_eval(split: "str | None" = None, model_tag: str = "base") -> dict:
    """Run the eval over the env's audit scenarios, write JSONL, return aggregates.

    ``model_tag`` is one of {"base", "trained"} (eval_result.json enum). The trace
    source is whatever the env loaded (``config.DATASET``); ``split`` defaults to
    that and, if given, must match it -- the env can only run tasks it has loaded.
    """
    split = split or config.DATASET
    if split != config.DATASET:
        raise ValueError(
            f"env loaded DATASET={config.DATASET!r} but eval requested split={split!r}; "
            f"serve the env with LOOP_AUDITOR_DATASET={split} so its tasks match"
        )
    auditor = agent_mod.build_auditor_agent()
    audit_scenarios = [s for s in env_mod._SCENARIOS.values() if s.mode == "audit"]
    records = []
    for sc in audit_scenarios:
        task = env_mod.audit_trace(scenario_id=sc.id)
        task.slug = sc.id
        raw_verdict, auditor_tokens = await _run_auditor_once(auditor, task)
        trace = env_mod._TRACES[sc.trace_id]
        trace_view, gt = env_mod.strip_ground_truth(trace)
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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default=None, help="defaults to the env's LOOP_AUDITOR_DATASET")
    parser.add_argument("--model-tag", default="base", choices=("base", "trained"))
    parser.add_argument(
        "--mock-judge",
        type=float,
        help="Use a fixed explanation score in [0,1] instead of the live/stub judge.",
    )
    args = parser.parse_args()
    if args.mock_judge is not None:
        os.environ["LOOP_AUDITOR_MOCK_JUDGE_SCORE"] = str(args.mock_judge)
    print(asyncio.run(run_eval(split=args.split, model_tag=args.model_tag)))


if __name__ == "__main__":
    main()
