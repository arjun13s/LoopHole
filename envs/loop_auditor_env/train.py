"""GRPO rollout loop in HUD -- the H4 CORE DE-RISK.

OWNER: Claude. HUD-native path (TrainingClient routes the optimizer to the
provider backend):
    Job.start(MODEL, group=GROUP_SIZE) -> taskset.run(agent, job=...) over the
    fixtures -> trainer.step(batch, group_size=GROUP_SIZE, learning_rate=LR).

H4 gate: a group of rollouts is sampled, rewards are NON-DEGENERATE (spread > 0),
one trainer.step() returns without error, and the checkpoint ref advances.

!!! VERIFY @ Step 0: every hud.* symbol + whether the calls are async. The
research showed `await Job.start(...)`, `await taskset.run(...)`,
`await trainer.step(...)`, so this is written async.
"""

from __future__ import annotations

import asyncio

from . import agent as agent_mod
from . import config
from . import env as env_mod


def _reward_of(run) -> float:
    """Pull the scalar reward off a HUD run. VERIFY the real field path."""
    grade = getattr(run, "grade", None)
    if grade is not None and hasattr(grade, "reward"):
        return float(grade.reward)
    if isinstance(run, dict):
        return float(run.get("reward", run.get("grade", {}).get("reward", 0.0)))
    return float(getattr(run, "reward", 0.0))


async def _run() -> None:
    auditor = agent_mod.build_auditor_agent(config.MODEL)
    taskset = env_mod.build_taskset()  # VERIFY taskset shape

    from hud import Job, TrainingClient  # VERIFY names/locations

    trainer = TrainingClient(config.MODEL)  # VERIFY
    session = await Job.start(config.MODEL, group=config.GROUP_SIZE)  # VERIFY

    start = len(session.runs)
    await taskset.run(auditor, job=session)  # VERIFY run signature
    batch = session.runs[start:]

    rewards = [_reward_of(r) for r in batch]
    spread = (max(rewards) - min(rewards)) if rewards else 0.0
    print(f"[H4] group_size={len(batch)} rewards={rewards} spread={spread:.3f}")
    assert spread > 0.0, (
        "DEGENERATE reward: every rollout scored the same, so GRPO advantage is 0. "
        "Vary fixture difficulty until the base model is partially right."
    )

    result = await trainer.step(
        batch, group_size=config.GROUP_SIZE, learning_rate=config.LR
    )  # VERIFY signature
    print(f"[H4] trainer.step OK -> {result}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
