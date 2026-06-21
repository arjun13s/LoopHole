"""Run one scenario N-up and report the reward spread (GRPO pre-flight check).

Zero reward spread across a group -> zero GRPO advantage, so this is the check to
run before committing compute to a training run. Mirrors ml-triage-tasks'
tools/run_many.py, adapted to our in-process MCP env (no DockerRuntime needed —
only inference is remote). Lives in scripts/ because tools.py is the pure
inspection-function module.

Usage:
    python envs/loop_auditor_env/scripts/run_many.py --scenario audit__<run_id> --n 8 --model claude

``summarize`` is pure and unit-tested; only ``main`` touches HUD + the gateway.
"""

from __future__ import annotations

import statistics


def summarize(rewards: list) -> dict:
    """Pure spread stats over a list of per-run rewards (None entries dropped)."""
    vals = [float(r) for r in rewards if r is not None]
    if not vals:
        return {"n": len(rewards), "got": 0, "mean": None, "median": None,
                "min": None, "max": None, "spread": None}
    return {
        "n": len(rewards),
        "got": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
        "spread": max(vals) - min(vals),
    }


async def _run() -> None:
    import argparse
    import sys
    from pathlib import Path

    env_root = Path(__file__).resolve().parent.parent
    if str(env_root) not in sys.path:
        sys.path.insert(0, str(env_root))
    import config  # noqa: F401  (kept for parity / future knobs)
    import env as env_mod
    from hud.agents import create_agent

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default=None, help="scenario id; default: first audit scenario")
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--model", default="claude")
    parser.add_argument("--max-steps", type=int, default=64)
    args = parser.parse_args()

    scenarios = env_mod._SCENARIOS
    sid = args.scenario or next(s for s in scenarios if s.startswith("audit__"))
    if sid not in scenarios:
        raise SystemExit(f"unknown scenario {sid!r}; available: {sorted(scenarios)[:8]}...")
    sc = scenarios[sid]
    template = env_mod.audit_trace if sc.mode == "audit" else env_mod.gate_trace
    task = template(scenario_id=sid)
    task.slug = sid

    agent = create_agent(args.model, max_steps=args.max_steps)
    print(f"=== {sid} | model={args.model} | n={args.n} ===")
    job = await task.run(agent, group=args.n, max_concurrent=args.n)
    rewards = [getattr(r, "reward", None) for r in job.runs]
    for i, r in enumerate(rewards, 1):
        print(f"[{i}/{args.n}] reward={r!r}")

    s = summarize(rewards)
    print(
        f"\nsummary: got={s['got']}/{s['n']} mean={s['mean']} median={s['median']} "
        f"min={s['min']} max={s['max']} spread={s['spread']}"
    )
    if s["spread"] == 0.0:
        print(
            "WARNING: zero reward spread -> zero GRPO advantage. Increase task "
            "difficulty/diversity or check the reward before training."
        )


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
