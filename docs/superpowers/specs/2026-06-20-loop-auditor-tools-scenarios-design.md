# Loop-Auditor — Tools & Scenarios Design

- **Date:** 2026-06-20
- **Owner:** Person 2 (HUD env)
- **Status:** Approved (brainstorming) → ready for implementation plan
- **Scope:** Build out the env's agent-facing **tools** and **scenarios** before any training. Covers
  Design **X** (static audit) and Design **Y** (replay-based gate head). Person 1 owns the trace dataset.

## Context & goals
The Loop-Auditor env trains an auditor agent to inspect agent **loop traces**, localize a
deterministically-planted fault, classify it, and explain/fix it (PLAN.md §1.4 reward). The current env
has one `audit-trace` task and three inspection tools. We are expanding the **action space** (tools) and
the **task surface** (scenarios) so GRPO has a meaningful policy to learn and a cost signal to optimize.

**Scope decision: C** — build both X and Y now.
- **X (static audit):** the auditor reads a *completed* trace, investigates with tools, emits one verdict.
- **Y (gate head):** the auditor controls a loop by **replaying Person 1's recorded traces
  iteration-by-iteration**, deciding `continue`/`stop`/`flag` per iteration to cut tokens without killing
  good runs. Reward adds a `−λ·tokens` term. Replay reuses the exact dataset Person 1 builds — no live
  worker — and is deterministic.

**Hard principle:** X remains a **standalone shippable floor**. Y is layered on top and the floor must
never depend on it.

## Non-goals
- The trace dataset / generator (Person 1's lane).
- A live synthetic/model worker (we replay recorded traces instead).
- Changing the frozen schemas or the §1.4 X-reward contract.
- Deploy/Docker changes (already done).

## Tool surface (10 tools; 6–12 target)
Each stateful tool charges the per-run `TokenMeter`, so every call has a real cost.

| # | Tool | Kind | Purpose |
|---|---|---|---|
| 1 | `get_trace_summary()` | pure | compact whole-trace summary |
| 2 | `get_iteration(index)` | pure | full detail of one iteration |
| 3 | `get_step(step_id)` | pure | full detail of one ActionSpan |
| 4 | `search_steps(query)` | pure | steps whose tool_name/input/output contains `query` |
| 5 | `get_errors()` | pure | steps with `status` in {error, timeout} |
| 6 | `get_step_io(step_id)` | pure | **untruncated** input/output for a step |
| 7 | `get_budget()` | stateful | tokens spent / remaining / λ (lets the policy self-regulate) |
| 8 | `get_solution()` | stateful | task **reference solution / expected outcome** (NOT the fault). **Expensive** (large meter charge). **Toggleable per scenario.** |
| 9 | `observe_next()` | stateful | reveal the next iteration in the replay stream (charges its tokens) |
| 10 | `gate(decision, reason, [step_id], [failure_type])` | stateful | `continue` / `stop` / `flag`; ends the run on stop/flag |

Pure tools (1–6 + `get_reference_solution`) live in `tools.py`. Stateful tools (7–10) live in `env.py`
because they touch the per-run meter / replay pointer / decision log.

`get_solution` returns the task's reference (expected behavior), never "the fault is at step X" — that
would trivialize localization and kill GRPO signal. Combined with its high cost, it becomes a genuine
accuracy↔budget tradeoff the policy learns to make.

## Cost / accounting (`accounting.py`)
A `TokenMeter` per run:
- `charge(amount: int, category: str)`, `spent`, `remaining`, `breakdown: dict`.
- Sources charged: revealed iteration tokens (sum of `ActionSpan.tokens`; estimate if absent),
  tool-output size (≈ `len(text)//4`), and a fixed `SOLUTION_COST` for `get_solution`.
- This is the **single** place "context used / cost per call" is tracked — no separate per-call cost
  tools. `get_budget()` reads it; the reward's λ term reads `meter.spent`.

## The two tasks (HUD v6 `@env.template`, 2-yield; tools drive the work)
- **`audit-trace` (X):** prompt = instructions + trace summary; agent investigates (tool calls charge the
  meter) and returns a verdict JSON; reward = `compute_reward` (§1.4, unchanged).
- **`gate-trace` (Y):** prompt = gate instructions; agent calls `observe_next()` to reveal iterations one
  at a time and `gate(...)` to decide. The template sets module state (current trace, meter, replay
  pointer, decision log) before yielding — same pattern HUD verified with the calculator's `_state`.
  Reward = `compute_gate_reward`.

## Reward
- **X — `compute_reward` (unchanged, §1.4):** `1.0·localization + 0.3·type + 0.5·explanation` (judge,
  gated to localization-correct); clean trace = 1.0 iff "no fault". Optional `LAMBDA_X` knob (default
  **0.0**) to honor the frozen contract.
- **Y — `compute_gate_reward(decisions, fault_iteration | None, tokens_spent, λ)`:**
  - *buggy:* `caught = (flagged at iteration k ≥ fault_iteration)` →
    `1.0·caught + 0.3·type_correct(if flag carries failure_type) − λ·tokens_spent`
  - *clean:* `1.0 if ran to end with no false flag/stop else 0.0` `− λ·tokens_spent`
  - Net: on buggy, flagging **at** the fault is optimal (detect + minimal tokens); on clean, **don't
    abort a good run**. λ is the cost lever.

## Scenarios & toggles (`scenarios.py`)
`Scenario` dataclass: `id`, `trace_id`, `mode ∈ {audit, gate}`, `enabled_tools: set[str]`,
`token_budget: int | None`, `lambda_: float`, `turn_limit: int | None`.
- Each stateful tool checks the current scenario's `enabled_tools` and returns `"tool disabled for this
  scenario"` if off → per-scenario toggling (esp. `get_solution`).
- `enumerate_scenarios(traces, config)` builds, per trace: an `audit` scenario + a `gate` scenario, with
  optional toggle variants (`solution_on` / `solution_off`) for ablations.
- `tasks.py` mints scenarios → HUD tasks with readable slugs (e.g. `audit__buggy-routing-001`,
  `gate__buggy-routing-001__solution_off`).

## Config additions (`config.py`)
`LAMBDA_TOKENS` (Y), `LAMBDA_X` (default 0.0), `SOLUTION_COST`, `DEFAULT_ENABLED_TOOLS`,
`GATE_TURN_LIMIT`. All env-overridable.

## Error handling
- Pure tools raise; env wrappers convert to `"error: ..."` strings (existing convention).
- `observe_next()` past end → `"no more iterations"` and the run auto-concludes.
- `gate()` with an invalid decision → error string.
- `get_solution()` with no reference in the data → `"reference unavailable"` (small/zero charge).
- Malformed verdict → reward 0.0 (existing).

## Testing (keyless; judge in stub mode)
- **Pure:** `search_steps`, `get_errors`, `get_step_io`, `get_reference_solution`.
- **accounting:** charge / remaining / breakdown / solution cost.
- **reward:** `compute_gate_reward` across stop-before/at/after-fault, clean-completed vs false-flag, and
  λ sensitivity.
- **env:** drive `gate-trace` via `gen.asend` (observe → gate); MCP capability serves all enabled tools;
  a `solution_off` scenario disables `get_solution`.

## Dependencies & interfaces out
- **Person 1:** `get_solution` returns real content only once traces carry a reference field
  (e.g. `trace["reference_solution"]`); interface ships now, value lands later. The fault-iteration for Y
  is derived from `planted_failure.step_id` → its iteration index.
- **Person 3:** unchanged — `eval_harness` still emits `eval_results.jsonl` (+ optional `verdicts.jsonl`
  sidecar per their contract). Gate runs can later emit a parallel gate-metrics record if the dashboard
  wants the tokens-saved view.

## Open knobs (defaults, tune later)
`LAMBDA_TOKENS` ≈ 0.001/token (tune so token term is comparable to the detection term on real traces),
`SOLUTION_COST` ≈ a few hundred tokens, `GATE_TURN_LIMIT` = max iterations + small slack.
