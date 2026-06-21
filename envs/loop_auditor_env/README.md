# `loop_auditor_env` — HUD v6 RL environment (Person 2)

The auditor agent reads a serialized agent **loop trace**, localizes a deterministically-planted bug to
the right step, classifies it, explains it, and proposes a fix. Trained with **GRPO** through HUD.

Built against the real v6 API (verified against `hud init --preset blank`, hud-python 0.6.x):
- `@env.template(id="audit-trace")` — `answer = yield prompt` (the verdict JSON), then `yield reward` (§1.4).
- An in-process MCP **capability** (FastMCP in `@env.initialize`) serving inspection tools:
  `get_trace_summary`, `get_iteration`, `get_step`.
- `env.py` is the environment; `tasks.py` mints one audit task per fixture.

## Module map
| File | Owner | Role |
|---|---|---|
| `config.py` | Claude | contract constants + knobs (model-agnostic, env-overridable) |
| `serialize.py` / `tools.py` / `verdict.py` / `reward.py` | Codex | pure trace→summary, inspection fns, verdict parse/validate, §1.4 reward |
| `judge.py` | Claude | Claude rubric judge (3 dims → 0..1); offline **stub** when no key |
| `env.py` / `tasks.py` / `agent.py` | Claude | HUD env + audit task + tasks list + agent factory |
| `eval_harness.py` / `train.py` | Claude | base/trained eval → eval-result JSONL; GRPO loop |

Intra-module imports are dual-mode (package for `pytest`, flat for `hud serve env:env`).

## Setup
```bash
# the env needs hud-python >= 0.6 on Python 3.11/3.12 (your global CLI may be older):
uv tool upgrade hud-python          # -> 0.6.x
cd envs/loop_auditor_env
uv sync                             # install hud-python + anthropic into .venv
hud set HUD_API_KEY=...             # or put HUD_API_KEY=... (and ANTHROPIC_API_KEY=...) in .env
```

## Run a local eval (model called through the HUD gateway)
```bash
hud eval tasks.py claude --gateway                 # one task
hud eval tasks.py claude --gateway --full          # every fixture
hud eval tasks.py claude --gateway --group 8       # grouped rollouts (GRPO-style)
```
Pick any task slug (`buggy-resource-misuse-001`, `buggy-routing-001`, `clean-trace-001`), any agent
(`claude`, `openai`, `openai_compatible`, …), any model from `hud models list`.

## Local dev / keyless checks
```bash
hud serve env:env                                  # serve the env locally
python env.py                                      # no-model smoke: boot a task, print the reward
```

## Tests (keyless; judge runs in stub mode)
```bash
# from repo root:
uv run pytest
# or from this dir:
uv run pytest
```
Covers the §1.4 reward (all branches), verdict parse/validate, serialize, tools, the audit template, and
the served MCP capability. No model/gateway/key needed.

## The judge
`judge.py` calls a **separate** Claude model (never the trained auditor). Set `ANTHROPIC_API_KEY` for the
live judge; otherwise (or with `LOOP_AUDITOR_JUDGE_STUB=1`) it uses a deterministic offline stub so the
pipeline runs keyless.

## Still TODO
- **GRPO training** (`train.py`) + **eval rollout** (`eval_harness._run_auditor_once`) use the HUD
  training/run API — still tagged `!!! VERIFY` (confirm `Job`/`TrainingClient` / single-trace rollout
  against 0.6.x). `agent.py`'s `hud.agents` symbols likewise.
- **Deploy** (`hud deploy`): needs a `Dockerfile.hud` that copies all modules + `fixtures/` + the
  `schemas/` (currently read from repo root via `config.SCHEMAS_DIR`). Local eval does not need this.
