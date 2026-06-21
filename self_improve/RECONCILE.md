# Reconciliation: Codex's analyzer ↔ Claude's producer (meet-in-the-middle)

Codex shipped `envs/loop_auditor_env/self_improve.py` (analyzer + CLI + 9 tests) **in parallel,
before** the producer/schemas landed. Decision (confirmed by Arjun): **meet in the middle** — keep
the producer's `verdict_sidecar.signals` as the single source of truth AND keep Codex's multi-label
`buckets` + markdown report. One merged record (`schemas/improvement_record.json`).

## Why a change is needed

Integration test (Codex's analyzer over the producer's `verdicts.jsonl`, no raw traces): it
mislabels clean false-positives as `bad_localization`, can't see `parse_failure`, and misses
`dataset_issue`/`prompt_confusion`/`artifact_miss` — because it **re-derives from raw traces and
ignores the `signals` block**. The producer already computes every fact it needs, deterministically,
with the reward stack's own helpers (no drift).

## The change-list (targeted diffs to `self_improve.py` — not a rewrite)

Full spec + predicate pseudocode + the fix-vocabulary map: **taxonomy note §12**
(`docs/superpowers/specs/2026-06-21-loop-auditor-self-improvement-taxonomy.md`).

1. **Join by `(run_id, model)`**, not `run_id` (don't collapse base vs trained).
2. **Read `sidecar["signals"]`** for the deterministic facts (gt_fault_present, pred_fault_present,
   verdict_parsed, citation_passed, fabricated_step_refs, type_out_of_enum, failure_type_raw,
   is_rich_case, artifact_tool_calls, fix_concept_total/matched, gt_step_in_trace, …) instead of
   re-deriving from raw traces. The `--traces` input becomes legacy/optional.
3. **`buckets`** = the §12.1 multi-label predicate set (keep your multi-label completeness).
   **`bucket`** = the §5 precedence pick (Claude's prioritization headline).
   `contributing_factors = sorted(set(buckets) - {bucket})`.
4. **Add `prompt_confusion`** (bucket) + `prompt_clarity` (category).
5. **Emit the merged record** (`schemas/improvement_record.json`): add `bucket`, `fix_type` (§12.2
   lever), `recommended_fix_type` (§12.2 category), `confidence`, `severity`, `suggested_alias`;
   keep `buckets`, `diagnosis`, `reward`; rename old `evidence`(list) → `notes`, put structured
   values in `evidence`(object). Keep `read_jsonl`/`write_jsonl`/`summarize`/`format_markdown_summary`.
6. **Test against the golden oracle** `self_improve/fixtures/improvement_cases.jsonl` (17 cases, all
   10 buckets + a genuine multi-label case + the None-path). Each `expect` pins
   `{bucket, buckets, fix_type, recommended_fix_type, confidence, severity, suggested_alias}`
   (partial — `evidence`/`diagnosis`/`notes` are free-text). Compare `buckets` order-insensitively.

The golden rows already round-trip 17/17 against this exact spec, validate against the frozen
schemas, and the dashboard's `load_verdicts` loads every producer sidecar without error.

## Boundary

Claude owns: `diagnostics.py` (producer), `schemas/{verdict_sidecar,improvement_record}.json`, the
taxonomy note, the golden fixture. Codex owns: the `self_improve.py` diffs above, the CLI, the
tests. Need another signal or golden case? Ping Claude — it's added in the producer, never
re-derived in the analyzer.
