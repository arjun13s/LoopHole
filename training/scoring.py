"""Pure scoring core for the base-eval baseline.

Independently implements the FROZEN contracts so the training package has **no
dependency on loop_auditor_env / hud / anthropic**:
  - reward: schemas/reward_spec.json (§1.4)
  - verdict clean-trace sentinels: schemas/verdict.json (main = "NONE"/"none")

The explanation score is passed IN (the judge is injected by the caller), keeping
this layer free of network/LLM calls and trivially testable.
"""

from __future__ import annotations

import json

# Frozen verdict clean-trace sentinels (schemas/verdict.json): a clean trace has
# fault_present == False, predicted_step_id == null, failure_type == null.
NO_FAULT_STEP_ID = None
NO_FAULT_TYPE = None

# Frozen reward weights (schemas/reward_spec.json §1.4).
W_LOCALIZATION = 1.0
W_FAILURE_TYPE = 0.3
W_EXPLANATION = 0.5


def strip_ground_truth(trace: dict) -> tuple[dict, dict | None]:
    """Split a trace into (auditor-visible view, ground-truth planted_failure|None)."""
    gt = trace.get("planted_failure")
    view = {k: v for k, v in trace.items() if k != "planted_failure"}
    return view, gt


def count_trace_tokens(trace: dict) -> int:
    """Sum ActionSpan.tokens across the trace (feeds eval_result.trace_tokens).

    Falls back to ``metadata.trace_tokens`` when per-step tokens are absent: the
    normalized live/rich traces strip per-step tokens from the auditor view (a
    per-step count leaks the fault), but the honest total is preserved in metadata.
    """
    total = 0
    for it in trace.get("iterations", []) or []:
        for s in it.get("steps", []) or []:
            total += int(s.get("tokens", 0) or 0)
    if total == 0:
        return int((trace.get("metadata") or {}).get("trace_tokens", 0) or 0)
    return total


def parse_verdict(raw) -> dict:
    """Coerce a model output into a verdict dict.

    Accepts a dict, a JSON string, or noisy text containing a JSON object (the
    common case for an instruct model). Raises ValueError if no object is found.
    """
    if isinstance(raw, dict):
        return raw
    text = str(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"could not parse verdict JSON: {exc}") from exc
    raise ValueError("no JSON object found in verdict output")


def reward(localization_correct: bool, failure_type_correct: bool, explanation_score: float, *, clean: bool) -> float:
    """Scalar GRPO reward per §1.4. Clean traces: 1.0 iff correctly judged no-fault."""
    if clean:
        return 1.0 if localization_correct else 0.0
    return (
        W_LOCALIZATION * float(localization_correct)
        + W_FAILURE_TYPE * float(failure_type_correct)
        + W_EXPLANATION * float(explanation_score)
    )


def score_record(
    run_id: str,
    model_tag: str,
    verdict: dict,
    ground_truth: dict | None,
    trace_tokens: int,
    auditor_tokens: int,
    explanation_score: float,
) -> dict:
    """Build one §1.3 eval-result record. ``explanation_score`` is judge-supplied."""
    clean = ground_truth is None
    if clean:
        # Frozen reward_spec: a clean trace is judged correctly iff fault_present is False.
        no_fault = verdict.get("fault_present") is False
        localization_correct = no_fault
        failure_type_correct = no_fault
        expl = 0.0
    else:
        localization_correct = verdict.get("predicted_step_id") == ground_truth["step_id"]
        failure_type_correct = verdict.get("failure_type") == ground_truth["failure_type"]
        expl = float(explanation_score) if localization_correct else 0.0
    return {
        "run_id": run_id,
        "model": model_tag,
        "localization_correct": bool(localization_correct),
        "failure_type_correct": bool(failure_type_correct),
        "explanation_score": float(expl),
        "reward": float(reward(localization_correct, failure_type_correct, expl, clean=clean)),
        "trace_tokens": int(trace_tokens),
        "auditor_tokens": int(auditor_tokens),
    }
