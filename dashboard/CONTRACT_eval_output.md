# Contract: HUD eval output → dashboard (base-vs-trained money-shot)

Person 3 ↔ Person 2. The dashboard renders the real base-vs-trained comparison
from **two `eval_result` JSONL files** — nothing else is strictly required. This
documents the minimal contract and the optional bonuses.

## What Person 2 runs (HUD) — IMPLEMENTED as `scripts/money_shot_eval.sh`

Person 2 shipped `scripts/money_shot_eval.sh` to this contract — it is the single
source of truth for producing the dashboard inputs. It runs
`eval_harness.run_eval(split, model_tag)` (whose `build_eval_record` / `aggregate`
are byte-identical to Person 3's base path, so the comparison is fair) once per
model over the **rich held-out split**, awaiting the async `run_eval` correctly and
writing the dashboard-named files:

```bash
./scripts/money_shot_eval.sh                       # slugs from gitignored .env
./scripts/money_shot_eval.sh BASE_SLUG             # base only
./scripts/money_shot_eval.sh BASE_SLUG TRAINED_SLUG
# -> results/eval_results.base.jsonl    + results/verdicts.base.jsonl
#    results/eval_results.trained.jsonl + results/verdicts.trained.jsonl (if trained slug set)
```

Trained is OPTIONAL: with no trained slug it produces base-only and the dashboard
renders trained as pending.

> `scripts/run_demo.sh --real [BASE_SLUG] [TRAINED_SLUG]` does both in one step:
> it invokes `money_shot_eval.sh` then renders. `--from <dir>` renders an existing
> results dir without touching HUD.

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

1. **Verdict drill-down** — `results/verdicts.<tag>.jsonl`, one record per trace.
   ✅ NOW EMITTED: `money_shot_eval.sh` writes it, and there is a frozen
   `schemas/verdict_sidecar.json` (producer: `diagnostics.py`). It is a SUPERSET of
   the dashboard envelope — `{run_id, model, <verdict core>}` plus a `signals` block
   the dashboard ignores (read by the self-improvement analyzer). The dashboard
   validates only the verdict core, so it loads these as-is.

2. **Trace replay** — point `--traces <dir>` at the frozen-schema trace `.json` files
   for the audited split (step-by-step replay with the planted step highlighted).
   Missing → the comparison still renders, just without replay.

## Status / gaps

- Schema: shared + frozen; `eval_result.json` + `verdict.json` core identical between
  `eval_harness`/`money_shot_eval.sh` and the dashboard. ✅
- Filenames: `money_shot_eval.sh` writes the per-tag names the dashboard reads. ✅
- Verdict sidecar: emitted (`verdict_sidecar.json`); dashboard reads core, ignores `signals`. ✅
- Open UI item (Person 3): base-only render shows "Trained 0% / −Δ" instead of a
  **"trained pending"** empty-state — to be fixed in the dashboard UI pass. ⚠️
