# Schemas — FROZEN CONTRACTS (read-only by convention)

These four JSON Schemas are the contracts every module builds against. Per `PLAN.md` §1 they are
**frozen at H0 and read-only afterward** — no unilateral field changes. If a field must change, it is a
whole-team decision.

| File | What it describes | PLAN.md ref |
|---|---|---|
| `trace.json` | `LoopRun → LoopIteration[] → ActionSpan[]` + `planted_failure` | §1.1 |
| `verdict.json` | What the auditor emits | §1.2 |
| `eval_result.json` | One record per trace/model — what the dashboard reads | §1.3 |
| `reward_spec.json` | The GRPO scalar reward (machine-readable) | §1.4 |

> Derived from `PLAN.md` §1. §1.1 says to adopt the team `ARCHITECTURE.md` §3 trace shape as-is — if that
> doc differs from `trace.json` here, reconcile **once** at H0 and then freeze.

Key invariants:
- `ActionSpan.step_id` is a stable, canonical, unique string. **Localization is exact-match on it.**
- Clean traces have `planted_failure: null`; the auditor signals "no fault" with
  `predicted_step_id = "NONE"` (see `config.NO_FAULT_STEP_ID`).
- Every planted fault: exactly one, **symptom == cause** (locally identifiable at its `step_id`).
