# Proposed contract: verdict sidecar (Person 3 → Person 2)

**Why:** `schemas/eval_result.json` is frozen with `additionalProperties: false` and carries
only correctness booleans + token counts — *not* the auditor's actual verdict text. The
dashboard's "auditor verdict" drill-down (predicted vs actual step, explanation, fix) therefore
needs a separate, **optional** sidecar. Without it the dashboard still ships (it degrades to a
booleans-only verdict summary); with it the demo gets the side-by-side base-vs-trained verdicts.

**This file is informational only.** It lives in Person 3's dir and changes nothing of Person 2's.
Adopt it only if convenient.

## Sidecar record (one JSON object per line → `verdicts.jsonl`)

```json
{
  "run_id": "buggy-resource-001",
  "model": "trained",
  "predicted_step_id": "iter0.step1.overwrite-limit",
  "failure_type": "resource_misuse",
  "explanation": "...",
  "proposed_fix": "..."
}
```

`{predicted_step_id, failure_type, explanation, proposed_fix}` is exactly a `schemas/verdict.json`
object; `{run_id, model}` is the routing envelope. The dashboard validates the verdict core
against the frozen schema and keys records by `(run_id, model)`.

## Suggested ~5-line emit (drop into `eval_harness.py`)

`build_eval_record` already parses the verdict (`v = verdict_mod.validate_verdict(...)`). Capture
it alongside the eval record and write a parallel JSONL — no schema change, no behavior change:

```python
def verdict_sidecar_record(run_id: str, model_tag: str, v: dict) -> dict:
    return {"run_id": run_id, "model": model_tag,
            "predicted_step_id": v["predicted_step_id"], "failure_type": v["failure_type"],
            "explanation": v.get("explanation", ""), "proposed_fix": v.get("proposed_fix", "")}

# in run_eval(): collect these and
# write_jsonl(sidecar_records, config.EVAL_OUTPUT.with_name("verdicts.jsonl"))
```

`run_demo.sh --real` already passes `--verdicts results/verdicts.jsonl` when the file exists, so
the dashboard picks it up automatically once emitted.
