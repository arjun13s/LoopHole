# HANDOFF — Person 3 (LoopHole / Loop-Auditor RL env)

> Cold-resume note. Role: **Person 3** — dashboard, demo, Modal/eval compute. Owns `dashboard/`, `scripts/`, `training/`.
> The memory note `loophole-person3-status.md` auto-loads and mirrors this.

## Status (current — all merged to `main`)
- **Floor DONE:** `dashboard/` Rich static-render money-shot (base-vs-trained, trace replay w/ planted step,
  verdict drill-down, honest audit-cost chart). Runs on mocks. Adapted to the `fault_present`/`null` verdict schema.
- **Model-integration DONE:** `training/` — `scoring.py` (deterministic reward), `backends.py`
  (Dummy/Modal), `prompt.py`, `base_eval.py`, `run_base_eval.py` CLI, `modal_infer.py`.
- **Tests green:** dashboard 14, training 16.
- **Key design:** `base_eval` scores explanation **deterministically**, reusing Person 2's PURE
  `loop_auditor_env.fix_grader.grade_fix` + `citation_gate.check` (identical to the trained side — no LLM
  judge in the loop). LLM judge is optional eval-time only.

## ⏸️ THE ONE PENDING TASK — the real base-vs-trained run  (DECISION MADE: HUD path)
Produce real `base` + `trained` `eval_results` JSONL → dashboard money-shot.
**Decision (2026-06-21): BOTH sides via HUD `run_eval` (un-trained fork vs GRPO fork) — identical
harness, zero Modal spend.** My render side is DONE and proven on real data; the eval side is gated on
Person 2's HUD model access + a trained checkpoint (P2's `train.py` still being debugged — no trained
model/eval outputs in the repo yet).

### ✅ DONE today (Person 3 side, all in-lane, no conflicts)
- **Live-trace adapter:** `training/live_eval.py` turns Person 1's REAL Qwen worker traces
  (`generated_traces/live_qwen/`, 20 cases = 16 buggy + 4 clean, w/ ground truth) into the normalized
  Shape-A traces the deterministic grader expects, reusing P2's PURE `rich_loader.normalize_case`.
  Preserves honest audit-cost: `scoring.count_trace_tokens` now falls back to `metadata.trace_tokens`
  (the normalizer strips per-step tokens as an anti-leak measure). 3 new tests on the REAL dataset; **19 training tests green**.
- **Dashboard renders real eval_results** (verified): the base-vs-trained money-shot needs ONLY two
  `eval_results.{base,trained}.jsonl` files — verdict sidecar + trace replay are optional (loader degrades).
- **`scripts/run_demo.sh --from <dir>`** (new): decoupled render of any results dir P2 hands me — no HUD
  on my side. `--real` updated to set `LOOP_AUDITOR_DATASET=rich_heldout` to match the split.
- **`dashboard/CONTRACT_eval_output.md`** (new): paste-ready contract for P2 (what to run, file names, the
  optional verdict-sidecar bonus). Schema verified identical between `eval_harness` and the dashboard.

### ▶️ NEXT (gated on P2): get the two HUD eval_results files, then `run_demo.sh --from results`
P2 runs `run_eval(model_tag=base|trained)` over `rich_heldout` (see CONTRACT_eval_output.md), hands me
`eval_results.base.jsonl` + `eval_results.trained.jsonl`. Drop in a dir → `./scripts/run_demo.sh --from <dir>`.

### Modal (NOT needed for the chosen path — parked, $250 credits intact)
- Old `loophole-base-vllm` vLLM `@modal.web_server` never bound port 8000 (3× fail). **Root cause now known:**
  the team's working `trace_harness/live_modal_worker.py` uses plain `transformers` + `@app.function`
  (`.remote()`), NOT a web_server — that's the proven pattern if Modal inference is ever revived.

## NOT STARTED (stretch / optional)
- Textual interactive dashboard (static Rich is what ships).
- `run_demo.sh --real` exercised end-to-end against actual eval outputs (only `--mock` proven).
- Demo script / 2-min money-shot walkthrough with real numbers.
- Design-Y "tokens-saved" viz (P2 added gate-reward scaffolding; my chart stays honest "audit cost").

## OPEN coordination / watch items
- **Issue #3:** P1's generator traces still diverge from frozen `schemas/trace.json` (`normalize.py` is a stub).
  Gates the real run on P1's held-out set; `run_base_eval` validates traces and will reject divergent ones loudly.
- **`failure_type` enum consistency** — keep it identical across `training/prompt.py`, frozen `schemas/verdict.json`,
  and P2's reward; a mismatch fails verdict validation in the dashboard/scoring.
- Vendored `envs/loop_auditor_env/schemas/` must stay identical to root `schemas/` (dashboard uses root).

## Commands / env
- Dashboard: `dashboard/.venv/bin/python -m dashboard --render --mock` (from repo root; py3.14 venv).
- Dashboard tests: `cd dashboard && .venv/bin/python -m pytest -q`.
- Training tests: `cd training && ../dashboard/.venv/bin/python -m pytest -q` (pyproject pythonpath `["..","../envs"]`).
- Real base eval (once an endpoint exists): `python -m training.run_base_eval --traces <dir|jsonl> --base-url <…/v1> --out results`.
- Modal: `MODAL_PROFILE=loophole training/.venv/bin/modal {deploy training/modal_infer.py | app logs … | app stop … --yes}`.
- HUD: account on **beta** (`api.beta.hud.ai`, gateway `mcp.beta.hud.ai`); key works for SDK/CLI
  (`hud models list`). `hud-python` installed in `/tmp/hud312` (py3.12). `.mcp.json` points to beta.
- **Secrets:** real keys live only in gitignored `.env.local` (HUD+Anthropic) and `~/.modal.toml` — NEVER commit.
- `gh` authed; remote `origin` = `github.com/arjun13s/LoopHole`. Start new work on a branch off `main`.

## Resume in a fresh session
Say "resume the base-vs-trained run" → lead with the **HUD-base pivot** (fastest to the real money-shot).
