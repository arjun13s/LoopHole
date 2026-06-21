# envs/loop_auditor_env/scenarios.py
"""Scenario definitions: which trace, which mode (audit/gate), which tools.

OWNER: Claude. Pure, no hud/network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # package (pytest) | flat (hud)
    from . import config
except ImportError:
    import config


def _include_gate() -> bool:
    """Gate (Design-Y) scenarios are OPT-IN. Training and the audit eval never use
    gate mode, so by default we don't enumerate gate__ scenarios — that keeps the
    served taskset audit-only (no failing gate tasks). Set LOOP_AUDITOR_GATE=1 to
    re-enable gate work."""
    return os.environ.get("LOOP_AUDITOR_GATE", "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Scenario:
    id: str
    trace_id: str
    mode: str  # "audit" | "gate"
    enabled_tools: frozenset = field(default_factory=frozenset)
    lambda_tokens: float = 0.0
    token_budget: "int | None" = None
    turn_limit: "int | None" = None


def fault_iteration(trace: dict) -> "int | None":
    """Iteration index containing the planted fault, or None for a clean trace."""
    pf = (trace or {}).get("planted_failure")
    if not pf:
        return None
    sid = pf["step_id"]
    for it in trace.get("iterations", []) or []:
        if any(s.get("step_id") == sid for s in it.get("steps", []) or []):
            return it["index"]
    return None


def enumerate_scenarios(traces, solution_ablation: bool = False) -> "list[Scenario]":
    """One audit scenario per trace; a gate scenario too only when LOOP_AUDITOR_GATE
    is set (gate mode is opt-in — see _include_gate). Optional get_solution ablation."""
    include_gate = _include_gate()
    out = []
    for t in traces:
        rid = t["run_id"]
        out.append(Scenario(id=f"audit__{rid}", trace_id=rid, mode="audit",
                            enabled_tools=config.DEFAULT_ENABLED_TOOLS, lambda_tokens=config.LAMBDA_X))
        if include_gate:
            out.append(Scenario(id=f"gate__{rid}", trace_id=rid, mode="gate",
                                enabled_tools=config.DEFAULT_ENABLED_TOOLS,
                                lambda_tokens=config.LAMBDA_TOKENS, turn_limit=config.GATE_TURN_LIMIT))
        if solution_ablation:
            out.append(Scenario(id=f"audit__{rid}__solution_on", trace_id=rid, mode="audit",
                                enabled_tools=config.DEFAULT_ENABLED_TOOLS | {"get_solution"},
                                lambda_tokens=config.LAMBDA_X))
    return out
