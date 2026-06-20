"""HUD ``LoopAuditorEnv`` + the audit task.

OWNER: Claude. Implement against the VERIFIED HUD SDK API (Step 0).

Shape (per the approved plan):
  - Load a trace; strip ``planted_failure`` before the auditor sees anything.
  - First yield: a compact summary prompt (serialize.summarize_trace) + instructions
    (copy step_ids verbatim; use "NONE" if clean; finish with submit_verdict).
  - Expose inspection tools wrapping tools.get_trace_summary / get_iteration /
    get_step, plus a terminal ``submit_verdict`` tool.
  - Second yield: reward = compute_reward(verdict, ground_truth, judge_score),
    where judge_score = judge.score_explanation(...) only if localization correct.
"""

from __future__ import annotations

from . import config, reward, serialize, tools, verdict, judge  # noqa: F401


def build_env():
    """Construct and return the HUD Environment with the audit template registered."""
    raise NotImplementedError
