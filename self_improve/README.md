# `self_improve/` — Loop-Auditor self-improvement loop

Turns each eval into an **actionable worklist**: classify every defective auditor run into one
failure bucket, name the deterministic evidence, and recommend the lever that fixes it.

**Eval-time only. Never touches the GRPO reward.** Delete this package and not a single rollout
changes.

## Pipeline

```
eval_harness.run_eval ─┬─► eval_results.jsonl   (frozen 8-field schema)
                       └─► verdicts.jsonl        (schemas/verdict_sidecar.json — has .signals)
                                  │  join on (run_id, model)
                                  ▼
              self_improve.analyzer.classify ──► improvement_records.jsonl
                                  │                (schemas/improvement_record.json)
                                  ▼
                         report  (group by bucket × fix_type, rank by severity)
```

## Ownership split (do not overlap)

| Component | Owner | Status |
|---|---|---|
| Taxonomy, precedence rules, fix interpretation, prompt/rubric | **Claude** | ✅ design note + this contract |
| `schemas/verdict_sidecar.json`, `schemas/improvement_record.json` | **Claude** | ✅ committed |
| Signal producer `loop_auditor_env/diagnostics.py` + `verdicts.jsonl` emit | **Claude** | ✅ committed + tested (154 green) |
| Golden acceptance fixture `fixtures/improvement_cases.jsonl` | **Claude** | ✅ 16 cases, all 10 buckets + None-path |
| `analyzer.py` — `classify` / `analyze` | **Codex** | ⬜ to build |
| `__main__.py` — CLI | **Codex** | ⬜ to build |
| `tests/` — unit tests over the golden fixture | **Codex** | ⬜ to build |

## What Codex builds

`analyzer.py`, a **pure** module (no `loop_auditor_env` import, no LLM, no I/O beyond reading the
two JSONLs):

```python
def classify(eval_result: dict, sidecar: dict | None) -> dict | None:
    """One improvement_record (schemas/improvement_record.json), or None for a healthy run.
    Reads ONLY sidecar['signals'] (+ eval_result for run_id/model). Pure + deterministic."""

def analyze(eval_results: list[dict], sidecars: dict[tuple[str, str], dict]) -> list[dict]:
    """classify() over all runs; drop Nones. sidecars keyed by (run_id, model)."""
```

The **complete, unambiguous spec** is the design note §5 (precedence tree), §6 (fix_type +
`_suggested_alias` + `_weak_fix` + the two cross-cutting predicates + `_confidence`/`_severity`):
`docs/superpowers/specs/2026-06-21-loop-auditor-self-improvement-taxonomy.md`.

`__main__.py` CLI:

```
python -m self_improve --results eval_results.jsonl --verdicts verdicts.jsonl \
    [--out improvement_records.jsonl] [--report]
```

## Test oracle (already provided)

`fixtures/improvement_cases.jsonl` — 16 rows, each:

```json
{"id": "...", "note": "...", "eval_result": {...}, "sidecar": {...}, "expect": {...} | null}
```

`eval_result` + `sidecar` are produced by the **real** reward path + producer (not hand-faked).
Your test: for every row, `classify(row.eval_result, row.sidecar)` equals `row.expect` (or `None`
when `expect` is `null`). Compare `contributing_factors` order-insensitively (sort both).

Regenerate after a taxonomy/producer change (Claude owns this):

```
PYTHONPATH=envs .venv/bin/python self_improve/fixtures/generate_golden.py
```

The rows already round-trip: all 16 match the precedence tree, all `eval_result`/`sidecar` validate
against the frozen schemas, and all 10 buckets + the None-path are covered.

## Coordination

Need another signal or a new golden case? **Ping Claude** — the producer (`diagnostics.py`) is the
single place signals are computed, so it gets added there, not re-derived in `analyzer.py`. Claude
will not build the analyzer/CLI; Codex will not edit the producer, the schemas, the prompts, or the
reward.
