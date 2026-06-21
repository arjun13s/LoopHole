"""Explanation-rubric judge (separate Claude model).

OWNER: Claude. Scores an auditor explanation on 3 dims (correctness, specificity,
causal_soundness) -> scalar 0..1. NEVER uses the trained eval agent (avoids
circularity). Shared by the reward path (injected in env.py) and eval_harness.py.

Two modes:
  * STUB  -- deterministic offline heuristic. Used when LOOP_AUDITOR_JUDGE_STUB=1
            or when ANTHROPIC_API_KEY is unset, so env/train/eval run end-to-end
            without a key. NOT a real signal; for plumbing/dev only.
  * LIVE  -- calls the Anthropic API (config.JUDGE_MODEL) for a structured 3-dim
            rubric score. Requires the `anthropic` package + ANTHROPIC_API_KEY.

Pure helpers (_parse_scores, _aggregate, _stub_dims) are deterministic and
unit-testable without network. Only `score_explanation`'s LIVE branch touches the
network — VERIFY the Anthropic call shape if the SDK version differs.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

try:  # package (pytest) | flat (hud `env:env`)
    from . import config
except ImportError:
    import config

RUBRIC_DIMENSIONS = ("correctness", "specificity", "causal_soundness")

_JUDGE_SYSTEM = (
    "You are a strict evaluator of bug-localization explanations for AI agent loop "
    "traces. You are NOT the agent being evaluated. Given the ground-truth planted "
    "fault and an auditor's explanation, score ONLY the explanation's quality. "
    "Respond with ONLY a JSON object, no prose."
)


def _build_prompt(trace: dict, ground_truth: dict, explanation: str) -> str:
    """User prompt for the LIVE judge. Asks for a strict JSON rubric object."""
    gt = {
        "step_id": ground_truth.get("step_id"),
        "failure_type": ground_truth.get("failure_type"),
        "description": ground_truth.get("description"),
    }
    return (
        "Ground-truth planted fault:\n"
        f"{json.dumps(gt, indent=2)}\n\n"
        "Auditor explanation to grade:\n"
        f"{explanation!r}\n\n"
        "Score each dimension in [0.0, 1.0]:\n"
        "- correctness: does it correctly identify the actual fault/cause?\n"
        "- specificity: is it concrete (names the step/tool/mechanism) vs vague?\n"
        "- causal_soundness: is the cause->effect reasoning valid?\n\n"
        'Return EXACTLY: {"correctness": <float>, "specificity": <float>, '
        '"causal_soundness": <float>}'
    )


def _clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _parse_scores(text: str) -> dict:
    """Extract the 3 rubric scores from the judge's output. Tolerant of code
    fences / surrounding prose. Missing or invalid dims -> 0.0; all clamped to [0,1]."""
    obj = None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text or ""):
            if ch == "{":
                try:
                    obj, _ = decoder.raw_decode(text[i:])
                    break
                except json.JSONDecodeError:
                    continue
    if not isinstance(obj, dict):
        return {d: 0.0 for d in RUBRIC_DIMENSIONS}
    return {d: _clamp01(obj.get(d, 0.0)) for d in RUBRIC_DIMENSIONS}


def _aggregate(dims: dict) -> float:
    """Mean of the 3 dims, with config.EXPLANATION_SCORE_THRESHOLD as a floor gate."""
    vals = [_clamp01(dims.get(d, 0.0)) for d in RUBRIC_DIMENSIONS]
    mean = sum(vals) / len(vals)
    thr = config.EXPLANATION_SCORE_THRESHOLD
    if thr > 0.0 and mean < thr:
        return 0.0
    return mean


def _use_stub() -> bool:
    if os.environ.get("LOOP_AUDITOR_JUDGE_STUB") == "1":
        return True
    return not os.environ.get("ANTHROPIC_API_KEY")


def _mock_score() -> "float | None":
    raw = os.environ.get("LOOP_AUDITOR_MOCK_JUDGE_SCORE")
    if raw is None:
        return None
    return _clamp01(raw)


def _stub_dims(trace: dict, ground_truth: dict, explanation: str) -> dict:
    """Deterministic offline heuristic (NOT a real judge). Rewards non-trivial
    explanations that reference the ground-truth fault type / step / keywords."""
    text = (explanation or "").lower()
    words = text.split()
    gt = ground_truth or {}
    ftype = str(gt.get("failure_type", "")).lower()
    step = str(gt.get("step_id", "")).lower()
    desc = str(gt.get("description", "")).lower()

    mentions_type = bool(ftype) and (ftype in text or ftype.replace("_", " ") in text)
    mentions_step = bool(step) and step in text
    correctness = 1.0 if (mentions_type or mentions_step) else 0.3

    specificity = min(1.0, len(words) / 40.0)
    if mentions_step:
        specificity = max(specificity, 0.6)

    desc_kw = set(re.findall(r"[a-z]{4,}", desc))
    expl_kw = set(re.findall(r"[a-z]{4,}", text))
    overlap = len(desc_kw & expl_kw)
    causal = min(1.0, overlap / 5.0) if desc_kw else 0.3

    return {"correctness": correctness, "specificity": specificity, "causal_soundness": causal}


def score_explanation(trace: dict, ground_truth: dict, explanation: str) -> float:
    """Return a 0..1 explanation score. Caller gates this to localization-correct cases."""
    if not explanation or not explanation.strip():
        return 0.0
    mock_score = _mock_score()
    if mock_score is not None:
        return mock_score
    trace_key = json.dumps(trace, sort_keys=True, separators=(",", ":"))
    gt_key = json.dumps(ground_truth, sort_keys=True, separators=(",", ":"))
    return _score_explanation_cached(trace_key, gt_key, explanation)


@lru_cache(maxsize=4096)
def _score_explanation_cached(trace_key: str, gt_key: str, explanation: str) -> float:
    trace = json.loads(trace_key)
    ground_truth = json.loads(gt_key)
    if _use_stub():
        return _aggregate(_stub_dims(trace, ground_truth, explanation))

    # LIVE path -- VERIFY the Anthropic SDK call if the version differs.
    import anthropic  # guarded so this module imports without the package

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    msg = client.messages.create(
        model=config.JUDGE_MODEL,
        max_tokens=256,
        system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(trace, ground_truth, explanation)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return _aggregate(_parse_scores(text))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-judge", type=float, help="Return this fixed 0..1 explanation score.")
    args = parser.parse_args()
    if args.mock_judge is not None:
        os.environ["LOOP_AUDITOR_MOCK_JUDGE_SCORE"] = str(args.mock_judge)
    print(score_explanation({}, {"step_id": "a0", "failure_type": "routing", "description": "fixture"}, "fixture"))


if __name__ == "__main__":
    main()
