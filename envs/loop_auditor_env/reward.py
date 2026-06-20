"""Pure GRPO reward (PLAN.md §1.4 / schemas/reward_spec.json).

OWNER: Codex. PURE: no judge/model/network calls. The explanation score is
computed by judge.py (Claude) and INJECTED via ``explanation_score``.
"""

from __future__ import annotations

from . import config


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

        reward = 1.0 if verdict["predicted_step_id"] == config.NO_FAULT_STEP_ID else 0.0
    """
    raise NotImplementedError
