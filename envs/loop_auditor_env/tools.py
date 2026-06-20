"""Pure inspection functions over a trace dict.

OWNER: Codex. These are wrapped as HUD ``@mcp.tool()``s in env.py (Claude).
Keep them pure: no HUD imports, no network, deterministic.

Error convention (pinned so env.py can wrap consistently): RAISE on bad input.
env.py converts the exception into a tool-friendly error message for the agent.
"""

from __future__ import annotations


def get_trace_summary(trace: dict) -> str:
    """Compact whole-trace summary (delegate to serialize.summarize_trace)."""
    raise NotImplementedError


def get_iteration(trace: dict, index: int) -> dict:
    """Return the full LoopIteration at ``index``. Raise IndexError if out of range."""
    raise NotImplementedError


def get_step(trace: dict, step_id: str) -> dict:
    """Return the ActionSpan whose ``step_id`` == step_id. Raise KeyError if none."""
    raise NotImplementedError
