# Contract: HUD eval output → dashboard (base-vs-trained money-shot)

Person 3 ↔ Person 2. The dashboard renders the real base-vs-trained comparison
from **two `eval_result` JSONL files** — nothing else is strictly required. This
documents the minimal contract and the optional bonuses.

## What Person 2 runs (HUD)

`envs/loop_auditor_env/eval_harness.run_eval(split, model_tag)` already emits the
frozen `schemas/eval_result.json` records (its `build_eval_record` / `aggregate`
are byte-identical to Person 3's base path — the comparison is fair). Run it once
per model over the **rich held-out split**:

```bash
# base auditor (un-trained fork)
LOOP_AUDITOR_MODEL=<base-slug>    LOOP_AUDITOR_DATASET=rich_heldout \
  python -c "from envs.loop_auditor_env import eval_harness as e; e.run_eval(split='rich_heldout', model_tag='base')"
cp envs/loop_auditor_env/eval_results.jsonl results/eval_results.base.jsonl

# trained auditor (GRPO fork)
LOOP_AUDITOR_MODEL=<trained-slug> LOOP_AUDITOR_DATASET=rich_heldout \
  python -c "from envs.loop_auditor_env import eval_harness as e; e.run_eval(split='rich_heldout', model_tag='trained')"
cp envs/loop_auditor_env/eval_results.jsonl results/eval_results.trained.jsonl
```

`run_eval(split)` raises unless the env was served with the matching
`LOOP_AUDITOR_DATASET` — hence both vars are set together above.

> `scripts/run_demo.sh --real` automates exactly this (set `LOOP_AUDITOR_BASE_MODEL`
> + `LOOP_AUDITOR_TRAINED_MODEL`; override the split with `LOOP_AUDITOR_SPLIT`).

## What Person 3 needs (minimal)

Two files in a results dir:

```
results/eval_results.base.jsonl
results/eval_results.trained.jsonl
```

Render (no HUD on the dashboard side):

```bash
./scripts/run_demo.sh --from results          # decoupled: render whatever's in the dir
# or directly:
python -m dashboard --render \
  --results results/eval_results.base.jsonl results/eval_results.trained.jsonl
```

That's the full money-shot: metric table (localization / failure-type / reward / Δ)
+ auditor-token cost chart + total trace tokens audited.

## Optional bonuses (the dashboard degrades gracefully without them)

1. **Verdict drill-down** — emit `results/verdicts.<tag>.jsonl`, one record per
   trace per the envelope in [CONTRACT_verdict_sidecar.md](CONTRACT_verdict_sidecar.md):
   `{run_id, model, fault_present, predicted_step_id, failure_type, explanation, proposed_fix}`.
   `run_eval` currently parses the verdict internally and discards it; persisting the
   raw verdict alongside each record unlocks the per-trace verdict view. Missing file → skipped.

2. **Trace replay** — point `--traces <dir>` at the frozen-schema trace `.json` files
   for the audited split (step-by-step replay with the planted step highlighted).
   Missing → the comparison still renders, just without replay.

## Status / gaps

- Schema: shared + frozen; verified identical between `eval_harness` and the dashboard. ✅
- Filename: `run_eval` writes a single untagged `eval_results.jsonl` — copy it to a
  per-tag name (above). The dashboard reads `eval_results.<tag>.jsonl` (or `<tag>.jsonl`). ⚠️
- Verdict sidecar: not yet emitted by `run_eval` (optional; bonus #1). ⚠️
