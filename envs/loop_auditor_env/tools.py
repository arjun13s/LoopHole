"""Pure inspection functions over a trace dict.

OWNER: Codex. These are wrapped as HUD ``@mcp.tool()``s in env.py (Claude).
Keep them pure: no HUD imports, no network, deterministic.

Error convention (pinned so env.py can wrap consistently): RAISE on bad input.
env.py converts the exception into a tool-friendly error message for the agent.
"""

from __future__ import annotations

from .serialize import summarize_trace


def get_trace_summary(trace: dict) -> str:
    """Compact whole-trace summary (delegate to serialize.summarize_trace)."""
    return summarize_trace(trace)


def get_iteration(trace: dict, index: int) -> dict:
    """Return the full LoopIteration at ``index``. Raise IndexError if out of range."""
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    iterations = trace.get("iterations")
    if not isinstance(iterations, list):
        raise TypeError("trace.iterations must be a list")
    try:
        return iterations[index]
    except IndexError as exc:
        raise IndexError(f"iteration index out of range: {index}") from exc


def get_step(trace: dict, step_id: str) -> dict:
    """Return the ActionSpan whose ``step_id`` == step_id. Raise KeyError if none."""
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    iterations = trace.get("iterations")
    if not isinstance(iterations, list):
        raise TypeError("trace.iterations must be a list")

    for iteration in iterations:
        if not isinstance(iteration, dict):
            continue
        steps = iteration.get("steps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict) and step.get("step_id") == step_id:
                return step
    raise KeyError(f"step_id not found: {step_id}")
