"""Tasks for the loop-auditor env — one task per scenario (audit + gate).

Run:  hud eval tasks.py claude --gateway        (single)
      hud eval tasks.py claude --gateway --group 8   (GRPO-style)
"""

import env as env_mod  # flat hud entry; re-exported for tests
from env import audit_trace, env, gate_trace  # noqa: F401

tasks = []
for _sc in env_mod._SCENARIOS.values():
    _template = audit_trace if _sc.mode == "audit" else gate_trace
    _task = _template(scenario_id=_sc.id)
    _task.slug = _sc.id
    tasks.append(_task)
