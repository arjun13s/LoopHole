"""Tasks for the loop-auditor env — one audit task per fixture trace.

Run locally:   hud eval tasks.py claude --gateway
Group rollouts: hud eval tasks.py claude --gateway --group 8   # GRPO-style
Sync remote:   hud sync tasks loop-auditor

``env`` is re-exported so `hud eval tasks.py` can resolve the Environment.
This file is the flat hud entry point, so imports are flat (not package-relative).
"""

from env import audit_trace, env, load_fixture_traces  # noqa: F401

tasks = []
for _trace in load_fixture_traces():
    _task = audit_trace(scenario_id=f"audit__{_trace['run_id']}")
    _task.slug = _trace["run_id"]
    tasks.append(_task)
