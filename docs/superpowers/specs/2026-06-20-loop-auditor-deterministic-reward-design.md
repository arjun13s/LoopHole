# Loop-Auditor: Deterministic Reward + Selective ml-triage Ports — Design

**Date:** 2026-06-20
**Owner:** Person 2 (Claude + Codex two-agent build)
**Status:** Approved (design); implementation in progress.

## Goal

Make the loop-auditor reward **deterministic and judge-free in the GRPO hot loop**
(fix-by-comparison), demote the LLM judge to an **eval-time diagnostic**, port
ml-triage-tasks' **anti-fake citation gate** (adapted to trace step-id references),
add an **N-up reward-spread eval tool**, and adopt ml-triage's **template-host repo
shape** for curated hard cases — all without modifying the frozen §1.4 reward or
the JSON schemas.

## Why (the moat)

`hud-evals/ml-triage-tasks` *evaluates* audit agents; our differentiator is that we
*train* one (GRPO). A live LLM judge in the reward path explodes token cost across
thousands of rollouts, so the **training reward must be deterministic and cheap**.
The work sequences: a working deterministic reward → prove GRPO trains on it →
then polish eval robustness. Building only the eval half would be "ml-triage plus a
gate," not the trainable auditor that is the pitch.

## Frozen contracts (hard invariant)

- `reward.py:compute_reward`, `verdict.py`, `schemas/*.json` — **byte-for-byte unchanged.**
- The eval-result record shape (Person 3's dashboard) — unchanged except an *additive*,
  optional `judge_quality` diagnostic column.
- Every change layers *around* these: it only changes **how the injected
  `explanation_score` is computed** and adds a post-filter. The §1.4 formula
  (`1.0·loc + 0.3·ftype + 0.5·explanation_score`, clean-trace = 1.0 iff no fault)
  is never touched. `explanation_score` being caller-computed was always part of the
  contract — judge today, fix-by-comparison tomorrow.

## Reward model (corrected)

`explanation_score` (the 0.5 term) is computed deterministically per rollout:

```python
score = fix_grader.grade_fix(verdict, ground_truth, trace_view, config.BASE_TRACES_DIR)
if not citation_gate.check(verdict, trace_view)["passed"]:
    score = 0.0     # fabricated step-id reference in the prose -> zero the explanation term
reward = compute_reward(verdict, ground_truth, score)   # §1.4 unchanged
```

- **Buggy trace:** `grade_fix` scores `proposed_fix` against the *known correct fix*
  (the deterministic inverse of the planted mutation, grounded in the base clean trace).
- **Clean trace:** `ground_truth is None` → §1.4's clean-case handles it; `grade_fix`
  returns 0.0 (unused).
- **Citation gate severity:** fabrication zeroes only the explanation term; the
  deterministically-verified localization + failure_type credit is preserved.
- **The LLM scaled judge is NOT in this path.** It runs only at eval time as a
  `judge_quality` diagnostic, never feeding reward — so **training reward == primary
  eval reward** (clean base-vs-trained comparison).

## New pure modules (Codex — branch `person2/codex-fix-gate`)

`fix_grader.py` and `citation_gate.py` — pure, deterministic, no network/HUD/LLM.
Public APIs (the integration seam Claude wires against):

- `fix_grader.grade_fix(verdict, ground_truth, trace, base_traces_dir) -> float` (0..1)
- `fix_grader.load_base_trace(run_id, base_traces_dir) -> dict | None`
  (resolves `<base>/<run_id.split("__")[0]>.json`, **and** retries with a leading
  `base_` stripped — see Risks)
- `fix_grader.expected_correction(trace, ground_truth, base_trace) -> dict` (pure)
- `citation_gate.check(verdict, trace) -> {"passed": bool, "checked": [...], "fabricated": [...]}`
  (scoped to **step-id** references only; tool-name absence is a valid audit claim).

`grade_fix` scores by concept-group coverage over `proposed_fix`+`explanation`,
grounded in the clean trace's corrected-action token where derivable. It is a
deterministic *proxy* for fix correctness, not semantic equivalence — intentional
(cheap, GRPO-safe). Nuanced quality is the eval-time judge diagnostic's job.

## Integration (Claude)

- `config.BASE_TRACES_DIR` — resolver (repo-root `tasks/base_traces/`, vendored
  fallback), mirroring `_resolve_taskset_dir`.
- `env.score_verdict` — replace the judge call with `grade_fix` + `citation_gate` (above).
- `eval_harness.build_eval_record` — identical reward path; add an optional eval-time
  `judge_quality` diagnostic column (off by default / flag-gated, so it never runs in training).
- `judge.py` — code unchanged; simply no longer called from the reward path.
- `tools/run_many.py` — N-up `Task.run(group=N)`; reports per-run reward + mean/
  median/min/max + **spread** (the GRPO pre-flight: zero spread → zero advantage).
- `train.py` — H4 gate: assert reward spread > 0 across a group, one `trainer.step`
  succeeds, checkpoint advances (Phase 2).

## Hybrid task structure (Phase 3)

- Keep `scenarios.py` auto-enumeration for the bulk 50-trace dataset.
- Add `tasks/<slug>/task.py` for curated hard cases + `_template/trace_audit/` starter;
  `tasks.py` merges auto-enumerated tasks + curated rows.

## Ownership

- **Person 2 (us):** the full HUD experience — env, reward, GRPO rollout loop
  (`train.py`), connectors.
- **Person 3:** Modal compute + checkpoint. Seam = compute config + checkpoint pull.

## Sequencing

1. **Phase 1 — deterministic floor reward:** `fix_grader` + `citation_gate` wired into
   `score_verdict` + `eval_harness`; cheap re-baseline (no judge cost).
2. **Phase 2 — prove training (the moat):** `run_many` spread check; `train.py` one real
   `trainer.step` on the deterministic reward; H4 gate; trained > base delta.
3. **Phase 3 — robustness + structure:** eval-time judge diagnostic; hybrid `tasks/` +
   `_template/` + one worked curated case; richer re-baseline.

## Testing

- Codex units (per its work package).
- Claude: `score_verdict` integration (fix score feeds reward; fabrication zeroes the
  explanation term but keeps localization + failure_type; clean trace unaffected);
  `eval_harness` reward parity with the env path; `run_many` stats helper; **all 76
  existing tests stay green** (frozen contracts untouched).

## Risks / dependencies

- **Base-naming inconsistency (Person 1):** csv-derived train run_ids prefix
  `base_clean_csv_001`, but the base file is `clean_csv_001.json`. `load_base_trace`
  must also try stripping a leading `base_`. Flag to Person 1 to normalize. Without
  grounding, csv `resource_misuse` falls back to concept-groups (still scores [0,1]).
- **I2 low diversity (Person 1):** all heldout buggy traces derive from
  `clean_slugify_001`; eval numbers reflect ~1 base task. More base tasks are Person 1's lane.
- **Honest score drift:** the gate + deterministic fix grading make the eval harder;
  mean reward may fall from the 0.952 judge-stub baseline. Re-baseline expected — this
  is a more trustworthy number.
