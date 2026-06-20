"""GRPO rollout loop in HUD — the H4 CORE DE-RISK.

OWNER: Claude. HUD-native path: Job.start(MODEL, group=GROUP_SIZE) ->
taskset.run(agent, job=...) over the fixtures -> trainer.step(batch,
group_size=GROUP_SIZE, learning_rate=LR). Logs the per-rollout reward array.

H4 gate: a group of rollouts is sampled, rewards are NON-DEGENERATE (spread > 0),
one trainer.step() returns without error, and the checkpoint ref advances.
"""

from __future__ import annotations

from . import config  # noqa: F401


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
