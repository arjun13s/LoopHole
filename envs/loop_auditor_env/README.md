# `loop_auditor_env` — HUD RL environment (Person 2)

The auditor agent reads a serialized agent **loop trace**, localizes a deterministically-planted bug to
the right step, classifies it, and explains/fixes it. Trained with **GRPO inside HUD**.

## Ownership (two-agent build)
- **Codex:** `serialize.py`, `tools.py`, `verdict.py`, `reward.py`, `fixtures/`, `tests/` — pure,
  deterministic, no HUD/network. Import `config` read-only; do not edit it.
- **Claude:** `config.py`, `judge.py`, `env.py`, `agent.py`, `eval_harness.py`, `train.py` — HUD-coupled
  + the Claude judge.

The pure/injected reward seam: `reward.compute_reward(...)` never calls the judge; `env.py` calls
`judge.score_explanation(...)` and passes the score in.

## Setup (Step 0 — verify the HUD API before trusting signatures)
```bash
uv add hud-python anthropic jsonschema      # materializes pyproject deps
uv run hud --help                           # confirm CLI
uv run python -c "import hud; print(hud.__version__)"
export HUD_API_KEY=...                       # or: uv run hud set HUD_API_KEY=...
export ANTHROPIC_API_KEY=...                 # judge
# model-agnostic: pick the model at H0
export LOOP_AUDITOR_MODEL="Qwen/Qwen2.5-7B-Instruct"   # or a `hud models fork` slug
```

## Run
```bash
uv run python -m envs.loop_auditor_env.train          # H4: one GRPO step on fixtures
uv run python -m envs.loop_auditor_env.eval_harness   # base/trained eval -> eval_results.jsonl
uv run pytest                                          # Codex unit tests (pythonpath=envs)
```

> Imports use the package name `loop_auditor_env` (root `pyproject.toml` sets `pythonpath = ["envs"]`),
> e.g. `from loop_auditor_env import reward`.
