"""Trace -> compact, prompt-friendly summaries.

OWNER: Codex. Pure + deterministic (stable ordering, no timestamps/randomness).
Conforms to schemas/trace.json.
"""

from __future__ import annotations

import json
from typing import Any


_TRUNCATE_AT = 120


def _compact(value: Any, limit: int = _TRUNCATE_AT) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def _step_descriptor(step: dict) -> str:
    parts = [step["action_type"]]
    tool_name = step.get("tool_name")
    if tool_name:
        parts.append(f"tool={tool_name}")
    status = step.get("status")
    if status and status != "ok":
        parts.append(f"status={status}")

    input_text = _compact(step.get("input"), 48)
    output_text = _compact(step.get("output"), 64)
    if input_text:
        parts.append(f"in={input_text}")
    if output_text:
        parts.append(f"out={output_text}")
    return " ".join(parts)


def summarize_trace(trace: dict) -> str:
    """Return a compact, deterministic summary of a LoopRun.

    List each iteration and, within it, each ActionSpan with its VERBATIM
    `step_id` and a short action descriptor (action_type, tool_name, truncated
    input/output, status). The auditor reads this to decide which steps to
    inspect, so `step_id`s MUST appear exactly (localization is exact-match).

    Do NOT include `planted_failure` (env.py strips it before calling).
    """
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    iterations = trace.get("iterations")
    if not isinstance(iterations, list):
        raise TypeError("trace.iterations must be a list")

    lines = [f"run {trace.get('run_id', '<missing-run_id>')}: {_compact(trace.get('task', ''))}"]
    for iteration in iterations:
        lines.append(summarize_iteration(iteration))
    return "\n".join(lines)


def summarize_iteration(iteration: dict) -> str:
    """One-iteration summary block (used by summarize_trace and tools.get_iteration)."""
    if not isinstance(iteration, dict):
        raise TypeError("iteration must be a dict")
    steps = iteration.get("steps")
    if not isinstance(steps, list):
        raise TypeError("iteration.steps must be a list")

    thought = _compact(iteration.get("thought", ""), 96)
    header = f"iteration {iteration.get('index', '<missing-index>')}"
    if thought:
        header = f"{header}: {thought}"

    lines = [header]
    lines.extend(f"  {summarize_step(step)}" for step in steps)
    return "\n".join(lines)


def summarize_step(step: dict) -> str:
    """One ActionSpan summary line, including the verbatim step_id."""
    if not isinstance(step, dict):
        raise TypeError("step must be a dict")
    if "step_id" not in step:
        raise KeyError("step is missing step_id")
    if "action_type" not in step:
        raise KeyError("step is missing action_type")
    return f"{step['step_id']}: {_step_descriptor(step)}"
