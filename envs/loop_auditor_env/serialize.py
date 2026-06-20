"""Trace -> compact, prompt-friendly summaries.

OWNER: Codex. Pure + deterministic (stable ordering, no timestamps/randomness).
Conforms to schemas/trace.json.
"""

from __future__ import annotations


def summarize_trace(trace: dict) -> str:
    """Return a compact, deterministic summary of a LoopRun.

    List each iteration and, within it, each ActionSpan with its VERBATIM
    `step_id` and a short action descriptor (action_type, tool_name, truncated
    input/output, status). The auditor reads this to decide which steps to
    inspect, so `step_id`s MUST appear exactly (localization is exact-match).

    Do NOT include `planted_failure` (env.py strips it before calling).
    """
    raise NotImplementedError


def summarize_iteration(iteration: dict) -> str:
    """One-iteration summary block (used by summarize_trace and tools.get_iteration)."""
    raise NotImplementedError


def summarize_step(step: dict) -> str:
    """One ActionSpan summary line, including the verbatim step_id."""
    raise NotImplementedError
