"""Pure GRPO reward (PLAN.md §1.4 / schemas/reward_spec.json).

OWNER: Codex. PURE: no judge/model/network calls. The ``explanation_score`` is
INJECTED by the caller; in the live path it is computed DETERMINISTICALLY by
fix_grader.grade_fix (fix-by-comparison) and zeroed by citation_gate on a
fabricated step reference — the LLM judge (judge.py) is an eval-time-only
diagnostic and is NOT part of the reward.
"""

from __future__ import annotations

try:  # package (pytest) | flat (hud `env:env`)
    from . import config
except ImportError:
    import config


def compute_reward(
    verdict: dict,
    ground_truth: "dict | None",
    explanation_score: float = 0.0,
) -> float:
    """Scalar reward.

    Buggy trace (``ground_truth`` is the planted_failure dict)::

        loc   = verdict["predicted_step_id"] == ground_truth["step_id"]
        ftype = verdict["failure_type"]      == ground_truth["failure_type"]
        reward = config.W_LOCALIZATION * loc
               + config.W_FAILURE_TYPE * ftype
               + (config.W_EXPLANATION * explanation_score if loc else 0.0)

    Clean trace (``ground_truth is None``)::

        reward = 1.0 if verdict["fault_present"] is False else 0.0
    """
    if not isinstance(verdict, dict):
        raise TypeError("verdict must be a dict")

    if ground_truth is None:
        return 1.0 if verdict.get("fault_present") is False else 0.0
    if not isinstance(ground_truth, dict):
        raise TypeError("ground_truth must be a dict or None")
    if verdict.get("fault_present") is False:
        return 0.0

    localization_correct = verdict["predicted_step_id"] == ground_truth["step_id"]
    failure_type_correct = verdict["failure_type"] == ground_truth["failure_type"]

    reward = config.W_LOCALIZATION * float(localization_correct)
    reward += config.W_FAILURE_TYPE * float(failure_type_correct)
    if localization_correct:
        reward += config.W_EXPLANATION * float(explanation_score)
    return reward


def compute_gate_reward(
    decision: str,
    stop_iteration: "int | None",
    fault_iteration: "int | None",
    tokens_spent: int,
    flagged_failure_type: "str | None" = None,
    planted_failure_type: "str | None" = None,
    lambda_tokens: "float | None" = None,
) -> float:
    """Design Y reward. decision in {'flag','stop','completed'}.

    Buggy (fault_iteration is not None): caught = flagged at/after the fault ->
        1.0 + 0.3*(flagged_failure_type == planted_failure_type) - lambda*tokens.
    Clean (fault_iteration is None): completed with no flag/stop -> 1.0 - lambda*tokens,
        else 0.0 - lambda*tokens (false abort).
    """
    lam = config.LAMBDA_TOKENS if lambda_tokens is None else lambda_tokens
    penalty = lam * max(0, int(tokens_spent))

    if fault_iteration is None:  # clean trace
        base = 1.0 if decision == "completed" else 0.0
        return base - penalty

    caught = (
        decision == "flag"
        and stop_iteration is not None
        and stop_iteration >= fault_iteration
    )
    base = 1.0 if caught else 0.0
    if caught and flagged_failure_type is not None and flagged_failure_type == planted_failure_type:
        base += 0.3
    return base - penalty
