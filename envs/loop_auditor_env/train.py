"""GRPO rollout loop in HUD -- the H4 CORE DE-RISK.

Written against verified hud-python 0.6.x signatures:
  Taskset.run(agent, *, group=..., runtime=...) -> Job          (async)
  Job.runs[i].reward                                            (per-rollout reward)
  TrainingClient(model).step(runs, *, learning_rate=, group_size=, loss_fn=...)  (async)

A grouped rollout scores each trajectory with our @env.template reward
(PLAN.md §1.4); TrainingClient.step turns the within-group reward spread into a
GRPO-style update (group_size -> group-relative advantages).

H4 gate: a group of rollouts is sampled, rewards are NON-DEGENERATE (spread > 0),
and one trainer.step() returns without error.

Run:  python -m envs.loop_auditor_env.train
Needs: HUD_API_KEY, LOOP_AUDITOR_MODEL set to a trainable gateway slug
(`hud models fork ...`), and ANTHROPIC_API_KEY for the live judge (else stubbed).
Still to confirm on first real run: the runtime choice and the GRPO loss_fn name
(`TrainingClient.available_losses()`; default 'importance_sampling').
"""

from __future__ import annotations

import asyncio

try:  # package (pytest) | flat (hud `env:env`)
    from . import agent as agent_mod
    from . import config
    from . import env as env_mod
except ImportError:
    import agent as agent_mod
    import config
    import env as env_mod


async def _run() -> None:
    from hud import LocalRuntime, Taskset, TrainingClient

    auditor = agent_mod.build_auditor_agent(config.MODEL)
    taskset = Taskset(name="loop-auditor", tasks=env_mod.build_taskset())
    trainer = TrainingClient(config.MODEL)

    # Grouped rollouts; each scored by the @env.template reward.
    job = await taskset.run(auditor, group=config.GROUP_SIZE, runtime=LocalRuntime())
    rewards = [r.reward for r in job.runs]
    spread = (max(rewards) - min(rewards)) if rewards else 0.0
    print(f"[H4] rollouts={len(job.runs)} rewards={rewards} spread={spread:.3f}")
    assert spread > 0.0, (
        "DEGENERATE reward: every rollout scored the same -> GRPO advantage is 0. "
        "Vary fixture difficulty until the base model is partially right."
    )

    # One GRPO-style optimizer step.
    result = await trainer.step(
        job.runs, learning_rate=config.LR, group_size=config.GROUP_SIZE
    )
    print(f"[H4] trainer.step OK -> {result}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
