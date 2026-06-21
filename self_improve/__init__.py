"""Loop-Auditor self-improvement loop.

Reads eval artifacts (``eval_results.jsonl`` + the ``verdicts.jsonl`` sidecar),
classifies each defective auditor run into a taxonomy bucket, and emits
``improvement_records.jsonl`` — an actionable worklist for reducing future
low-score runs. EVAL-TIME ONLY: never part of the GRPO reward.

Ownership: Claude owns the taxonomy + schemas + the signal producer
(``loop_auditor_env.diagnostics`` → ``verdicts.jsonl``) + the golden fixture.
Codex owns ``analyzer.py`` (signals → improvement_record), the CLI, and tests.

Contract: ``docs/superpowers/specs/2026-06-21-loop-auditor-self-improvement-taxonomy.md``,
``schemas/verdict_sidecar.json``, ``schemas/improvement_record.json``.
"""
