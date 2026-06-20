"""Loop-Auditor HUD RL environment (Person 2).

Package layout (owner in parens):
  config.py        (Claude)  contract constants + knobs — imported read-only by all
  serialize.py     (Codex)   trace -> compact summaries
  tools.py         (Codex)   pure inspection fns (wrapped as HUD tools in env.py)
  verdict.py       (Codex)   parse + validate auditor output
  reward.py        (Codex)   pure GRPO reward (judge score injected)
  judge.py         (Claude)  Claude explanation-rubric judge
  env.py           (Claude)  HUD LoopAuditorEnv + audit task
  agent.py         (Claude)  auditor agent factory
  eval_harness.py  (Claude)  base/trained eval -> eval-result JSONL
  train.py         (Claude)  GRPO rollout loop (H4 de-risk)
"""
