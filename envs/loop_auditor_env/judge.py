"""Explanation-rubric judge (separate Claude model).

OWNER: Claude. Scores an auditor explanation on 3 dims (correctness,
specificity, causal_soundness) -> scalar 0..1. NEVER uses the trained eval
agent (avoids circularity). Shared by the reward path (injected in env.py) and
eval_harness.py.
"""

from __future__ import annotations

from . import config


def score_explanation(trace: dict, ground_truth: dict, explanation: str) -> float:
    """Return a 0..1 explanation score from the Claude judge (config.JUDGE_MODEL).

    Only meaningful when localization is correct (the caller gates this). Applies
    config.EXPLANATION_SCORE_THRESHOLD. Deterministic parse of the judge's
    structured JSON output.
    """
    raise NotImplementedError
