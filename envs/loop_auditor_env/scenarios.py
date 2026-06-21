# envs/loop_auditor_env/scenarios.py
"""Scenario definitions: which trace, which mode (audit/gate), which tools.

OWNER: Claude. Pure, no hud/network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:  # package (pytest) | flat (hud)
    from . import config
except ImportError:
    import config


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


def enumerate_scenarios(traces, solution_ablation: bool = False) -> list:
    """One audit + one gate scenario per trace; optional get_solution ablation."""
    out = []
    for t in traces:
        rid = t["run_id"]
        out.append(Scenario(id=f"audit__{rid}", trace_id=rid, mode="audit",
                            enabled_tools=config.DEFAULT_ENABLED_TOOLS, lambda_tokens=config.LAMBDA_X))
        out.append(Scenario(id=f"gate__{rid}", trace_id=rid, mode="gate",
                            enabled_tools=config.DEFAULT_ENABLED_TOOLS,
                            lambda_tokens=config.LAMBDA_TOKENS, turn_limit=config.GATE_TURN_LIMIT))
        if solution_ablation:
            out.append(Scenario(id=f"audit__{rid}__solution_on", trace_id=rid, mode="audit",
                                enabled_tools=config.DEFAULT_ENABLED_TOOLS | {"get_solution"},
                                lambda_tokens=config.LAMBDA_X))
    return out
