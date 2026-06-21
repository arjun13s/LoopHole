"""Pure inspection functions over a trace dict.

OWNER: Codex. These are wrapped as HUD ``@mcp.tool()``s in env.py (Claude).
Keep them pure: no HUD imports, no network, deterministic.

Error convention (pinned so env.py can wrap consistently): RAISE on bad input.
env.py converts the exception into a tool-friendly error message for the agent.
"""

from __future__ import annotations

try:  # package (pytest) | flat (hud `env:env`)
    from .serialize import summarize_trace
except ImportError:
    from serialize import summarize_trace


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


import json as _json


def _iter_steps(trace: dict):
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    for iteration in trace.get("iterations", []) or []:
        if isinstance(iteration, dict):
            for step in iteration.get("steps", []) or []:
                if isinstance(step, dict):
                    yield step


def _haystack(step: dict) -> str:
    parts = []
    for key in ("tool_name", "input", "output"):
        v = step.get(key)
        if v is None:
            continue
        parts.append(v if isinstance(v, str) else _json.dumps(v, default=str))
    return " ".join(parts).lower()


def search_steps(trace: dict, query: str) -> list:
    """Steps whose tool_name/input/output contains `query` (case-insensitive)."""
    q = str(query).lower()
    return [s for s in _iter_steps(trace) if q in _haystack(s)]


def get_errors(trace: dict) -> list:
    """Steps with status in {error, timeout} (often near the fault)."""
    return [s for s in _iter_steps(trace) if s.get("status") in ("error", "timeout")]


def get_step_io(trace: dict, step_id: str) -> dict:
    """Untruncated input/output for a step. Raises KeyError if not found."""
    s = get_step(trace, step_id)
    return {"step_id": s["step_id"], "input": s.get("input"), "output": s.get("output")}


def get_reference_solution(trace: dict) -> "str | None":
    """Task reference solution if the trace carries one (Person 1 may add it)."""
    ref = (trace or {}).get("reference_solution")
    return ref if isinstance(ref, str) and ref.strip() else None
