"""HUD ``LoopAuditorEnv`` + the audit task.

OWNER: Claude.

The PURE helpers (load_fixture_traces, strip_ground_truth, build_prompt,
score_verdict) are correct and independently testable. The HUD wiring in
build_env / build_taskset is research-derived best-effort:

!!! VERIFY @ Step 0 (against the installed hud SDK):
    - Environment construction + the @env.template() async-generator contract
      (first yield = prompt, second yield = reward scalar).
    - How per-task inspection tools are registered (research: FastMCP @mcp.tool())
      and how the auditor's submitted verdict is returned to the second yield.
    - How a Taskset is assembled from template instances.
hud imports are confined to build_env/build_taskset so this module imports without hud.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config, judge
from . import reward as reward_mod
from . import serialize
from . import verdict as verdict_mod

INSTRUCTIONS = (
    "You are an auditor inspecting an AI agent's loop trace for a single planted "
    "fault.\n"
    "- Use the inspection tools (get_iteration, get_step) to examine suspicious steps.\n"
    "- Copy step_ids VERBATIM from the trace.\n"
    "- Exactly one step is faulty, or the trace is clean.\n"
    f"- If the trace is clean, set predicted_step_id to \"{config.NO_FAULT_STEP_ID}\" "
    f"and failure_type to \"{config.NO_FAULT_TYPE}\".\n"
    "- Finish by calling submit_verdict(predicted_step_id, failure_type, "
    "explanation, proposed_fix).\n"
)


# --- pure helpers (no HUD) ---------------------------------------------------
def load_fixture_traces(fixtures_dir=None) -> list[dict]:
    """Load all *.json traces from the fixtures dir (sorted for determinism)."""
    d = Path(fixtures_dir or config.FIXTURES_DIR)
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]


def strip_ground_truth(trace: dict) -> "tuple[dict, dict | None]":
    """Return (auditor_view_without_planted_failure, ground_truth_or_None).

    The auditor must never see planted_failure. ground_truth is the
    planted_failure dict (buggy) or None (clean).
    """
    gt = trace.get("planted_failure")
    view = {k: v for k, v in trace.items() if k != "planted_failure"}
    return view, gt


def build_prompt(trace_view: dict) -> str:
    """Compact summary prompt the auditor first sees."""
    return INSTRUCTIONS + "\n" + serialize.summarize_trace(trace_view)


def score_verdict(raw_verdict, trace_view: dict, ground_truth) -> float:
    """Parse/validate a verdict and return the §1.4 reward.

    Reuses verdict.py (parse+validate), judge.py (explanation score, gated to
    localization-correct), and reward.py (the pure scalar).
    """
    v = verdict_mod.validate_verdict(verdict_mod.parse_verdict(raw_verdict))
    explanation_score = 0.0
    if ground_truth is not None:
        if v["predicted_step_id"] == ground_truth["step_id"]:
            explanation_score = judge.score_explanation(
                trace_view, ground_truth, v.get("explanation", "")
            )
    return reward_mod.compute_reward(v, ground_truth, explanation_score)


# --- HUD wiring (VERIFY @ Step 0) -------------------------------------------
def build_env(traces=None):
    """Construct the HUD Environment with the audit template + inspection tools.

    !!! VERIFY: every hud.* symbol below against the installed SDK.
    """
    from hud import Environment  # VERIFY

    traces = traces or load_fixture_traces()
    by_id = {t["run_id"]: t for t in traces}

    env = Environment(name="loop-auditor")

    # Per-run trace view, set when a task starts so tools resolve against it.
    # VERIFY: the real mechanism for per-task state (contextvar / task arg / closure).
    state: dict = {"trace_view": None, "verdict": None}

    # --- inspection tools (wrap the pure tools.py) -- VERIFY decorator + registration
    from . import tools as tools_mod

    @env.tool  # VERIFY: real decorator (research suggests FastMCP @mcp.tool())
    def get_iteration(index: int) -> dict:
        return tools_mod.get_iteration(state["trace_view"], index)

    @env.tool  # VERIFY
    def get_step(step_id: str) -> dict:
        return tools_mod.get_step(state["trace_view"], step_id)

    @env.tool  # VERIFY: terminal action capturing the structured verdict
    def submit_verdict(
        predicted_step_id: str, failure_type: str, explanation: str, proposed_fix: str
    ) -> str:
        state["verdict"] = {
            "predicted_step_id": predicted_step_id,
            "failure_type": failure_type,
            "explanation": explanation,
            "proposed_fix": proposed_fix,
        }
        return "verdict recorded"

    @env.template()  # VERIFY: async-generator task contract
    async def audit_trace(run_id: str):
        trace = by_id[run_id]
        trace_view, gt = strip_ground_truth(trace)
        state["trace_view"] = trace_view
        state["verdict"] = None
        # first yield = prompt; the agent acts (calls tools incl. submit_verdict);
        # control resumes here. VERIFY how the submitted verdict reaches us — we
        # read it from state, falling back to whatever the harness returns.
        returned = yield build_prompt(trace_view)
        raw = state["verdict"] if state["verdict"] is not None else returned
        yield score_verdict(raw, trace_view, gt)

    env.audit_trace = audit_trace  # convenience handle for build_taskset
    return env


def build_taskset(traces=None):
    """Assemble a HUD taskset of one audit task per trace.

    !!! VERIFY: how HUD collects template instances into a runnable taskset.
    """
    traces = traces or load_fixture_traces()
    env = build_env(traces)
    return [env.audit_trace(run_id=t["run_id"]) for t in traces]
