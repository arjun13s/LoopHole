"""GRPO rollout loop in HUD -- the H4 CORE DE-RISK.

Verified against installed hud-python 0.6.6 signatures:
  Taskset(name, tasks=...)                                           (ctor)
  Taskset.run(agent, *, group=..., runtime=..., max_concurrent=...) -> Job   (async)
  Job.runs[i].reward / .slug                                         (per-rollout reward + task id)
  TrainingClient(model).step(runs, *, learning_rate=, loss_fn='importance_sampling',
                             group_size=...) -> OptimStepResult      (async)

A grouped rollout scores each trajectory with our @env.template reward (now
DETERMINISTIC: §1.4 localization + failure_type + fix-by-comparison, no LLM
judge in the loop). TrainingClient.step turns the within-group reward spread
into a GRPO update (group_size -> group-relative advantages).

H4 gate: for at least one task group the rewards are NON-DEGENERATE (spread > 0
within the group -> non-zero advantage), and one trainer.step() returns without
error and advances the checkpoint.

Run:  python -m envs.loop_auditor_env.train
Needs: HUD_API_KEY, LOOP_AUDITOR_MODEL set to a TRAINABLE gateway slug
(`hud models fork ...`), and a training runtime. The runtime is Person 3's Modal
compute (passed in / configured there); None lets HUD place the rollout. The
deterministic reward needs no judge key.
"""

from __future__ import annotations

import asyncio
import os
import sys

try:  # package (pytest) | flat (hud `env:env`)
    from . import agent as agent_mod
    from . import config
    from . import env as env_mod
except ImportError:
    import agent as agent_mod
    import config
    import env as env_mod


def spreads_by_group(labeled_rewards) -> dict:
    """Per-group reward spread (max-min) from (group_key, reward) pairs.

    GRPO advantage is computed WITHIN a group, so the spread that matters is
    per-task, not global. None rewards are dropped. Pure / unit-tested.
    """
    groups: dict = {}
    for key, reward in labeled_rewards:
        if reward is None:
            continue
        groups.setdefault(key, []).append(float(reward))
    return {key: (max(vals) - min(vals)) for key, vals in groups.items() if vals}


async def _run(runtime=None, num_steps: "int | None" = None) -> None:
    """Run ``num_steps`` GRPO steps (default LOOP_AUDITOR_TRAIN_STEPS, 1 = H4 gate).

    Each step: sample a grouped rollout over the audit taskset (deterministic §1.4
    reward), compute per-group spread, and — if any group is non-degenerate —
    apply one trainer.step. The promoted checkpoint means the next step samples
    the updated policy, so mean reward should trend up across steps.
    """
    from hud import Taskset, TrainingClient

    num_steps = num_steps if num_steps is not None else int(
        os.environ.get("LOOP_AUDITOR_TRAIN_STEPS", "1")
    )

    # Scope to AUDIT tasks: those carry the deterministic §1.4 reward we train the
    # auditor on (gate tasks have a separate reward scale).
    audit_ids = [sid for sid, sc in env_mod._SCENARIOS.items() if sc.mode == "audit"]
    # Cheap-smoke knob: cap the number of audit tasks (0 = all).
    max_tasks = int(os.environ.get("LOOP_AUDITOR_H4_MAX_TASKS", "0"))
    if max_tasks > 0:
        audit_ids = audit_ids[:max_tasks]
    taskset = Taskset(name="loop-auditor-audit", tasks=env_mod.build_taskset(audit_ids))
    # trainable=True -> rollout records token ids + logprobs (AgentStep.sample),
    # which TrainingClient.forward_backward needs (else "no trainable turns").
    auditor = agent_mod.build_auditor_agent(config.MODEL, trainable=True)
    trainer = TrainingClient(config.MODEL)

    history: list[dict] = []
    for step in range(1, num_steps + 1):
        job = await taskset.run(
            auditor, group=config.GROUP_SIZE, runtime=runtime, max_concurrent=config.GROUP_SIZE
        )
        labeled = [(getattr(r, "slug", None), getattr(r, "reward", None)) for r in job.runs]
        rewards = [r for _, r in labeled if r is not None]
        mean = sum(rewards) / len(rewards) if rewards else 0.0
        spreads = spreads_by_group(labeled)
        nonzero = [k for k, s in spreads.items() if s > 0.0]
        print(
            f"[train] step {step}/{num_steps}: mean_reward={mean:.3f} "
            f"rollouts={len(job.runs)} groups={len(spreads)} non-degenerate={len(nonzero)}"
        )
        if not nonzero:
            # No within-group spread -> zero GRPO advantage; the optimizer step is a
            # no-op. On step 1 that's the H4 gate failing; later it means converged/stuck.
            if step == 1:
                raise SystemExit(
                    "[train] DEGENERATE reward on step 1 (H4 gate): no group has spread -> "
                    "zero GRPO advantage. Increase task difficulty/diversity."
                )
            print(f"[train] step {step}: no non-degenerate group; skipping optimizer step")
            history.append({"step": step, "mean_reward": mean, "stepped": False})
            continue
        result = await trainer.step(
            job.runs, learning_rate=config.LR, group_size=config.GROUP_SIZE
        )
        ckpt = getattr(result, "checkpoint_id", None)
        print(f"[train] step {step}: optimizer OK checkpoint={ckpt}")
        history.append({"step": step, "mean_reward": mean, "stepped": True, "checkpoint": ckpt})

    print("[train] reward trajectory:", [(h["step"], round(h["mean_reward"], 3)) for h in history])
    try:
        print(f"[train] checkpoints -> {await trainer.checkpoints()}")
    except Exception as exc:  # noqa: BLE001 - informational only
        print(f"[train] checkpoints() unavailable here ({type(exc).__name__}: {exc})", file=sys.stderr)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
