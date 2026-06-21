# `self_improve/` — Loop-Auditor self-improvement loop (Claude's side)

Turns each eval into an **actionable worklist**: classify every defective auditor run, name the
deterministic evidence, and recommend the lever that reduces future low-score runs.

**Eval-time only. Never touches the GRPO reward.** Delete this and not a single rollout changes.

> **Reconciled (meet-in-the-middle).** Codex shipped the analyzer at
> `envs/loop_auditor_env/self_improve.py` (+ CLI + 9 tests) in parallel, before these contracts
> landed. We keep BOTH the producer-fed `signals` AND Codex's multi-label `buckets`/markdown report
> in one merged record. See **[RECONCILE.md](RECONCILE.md)** and taxonomy note **§12**.

## Pipeline

```
eval_harness.run_eval ─┬─► eval_results.jsonl   (frozen 8-field schema)
                       └─► verdicts.jsonl        (schemas/verdict_sidecar.json — has .signals)
                                  │  join on (run_id, model)
                                  ▼
        loop_auditor_env.self_improve.analyze_eval_records   ← Codex, reads .signals
                                  │
                                  ▼   improvement_records.jsonl + markdown report
                                      (schemas/improvement_record.json, merged)
```

## Ownership

| Component | Owner | Status |
|---|---|---|
| Taxonomy, precedence, fix interpretation, prompt/rubric, report design | **Claude** | ✅ design note §1–§12 |
| `schemas/verdict_sidecar.json`, `schemas/improvement_record.json` (merged) | **Claude** | ✅ committed |
| Producer `loop_auditor_env/diagnostics.py` + `verdicts.jsonl` emit | **Claude** | ✅ committed + tested (160 green) |
| Golden oracle `fixtures/improvement_cases.jsonl` | **Claude** | ✅ 17 cases: 10 buckets + multi-label + None-path |
| Analyzer `loop_auditor_env/self_improve.py` (exists) | **Codex** | 🔁 reconcile per [RECONCILE.md](RECONCILE.md) |
| CLI `loop_auditor_env/scripts/analyze_eval_failures.py` (exists) | **Codex** | 🔁 key by (run_id, model) |
| Analyzer tests → target the golden oracle | **Codex** | 🔁 |

## What changes (the analyzer already exists, 9 tests green)

Codex's `self_improve.py` keeps its CLI, `read_jsonl`/`write_jsonl`, `summarize_improvements`,
`format_markdown_summary`. The classification core changes to read `sidecar["signals"]` (no
raw-trace re-derivation, no drift), join by `(run_id, model)`, add `prompt_confusion`, and emit the
merged record. The exact 6-step change-list: **[RECONCILE.md](RECONCILE.md)**. Full predicate spec:
taxonomy note §5 (precedence → `bucket`), §6 (`fix_type`/severity/confidence/alias), §12.1
(multi-label `buckets`), §12.2 (fix-vocabulary map).

## Test oracle (provided)

`fixtures/improvement_cases.jsonl` — 17 rows, each:

```json
{"id": "...", "note": "...", "eval_result": {...}, "sidecar": {...}, "expect": {...} | null}
```

`eval_result` + `sidecar` come from the **real** reward path + producer (not hand-faked). For every
row, the analyzer's record must match `expect` on
`{bucket, buckets, fix_type, recommended_fix_type, confidence, severity, suggested_alias}` (a
PARTIAL oracle — `evidence`/`diagnosis`/`notes` are free-text; see `fixtures/README.md`). Compare
`buckets`/`contributing_factors` order-insensitively. `expect == null` ⇒ `classify` returns no
record. Regenerate (Claude owns this):

```
PYTHONPATH=envs .venv/bin/python self_improve/fixtures/generate_golden.py
```

All 17 rows round-trip against the spec, validate against the frozen schemas, and the dashboard's
`load_verdicts` loads every producer sidecar without error.

## Coordination

Need another signal or golden case? **Ping Claude** — signals are computed once in `diagnostics.py`,
never re-derived in the analyzer. Claude won't edit the analyzer/CLI; Codex won't edit the producer,
the schemas, the prompts, or the reward.
