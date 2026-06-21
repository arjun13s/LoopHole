# Loop-Auditor: Self-Improvement Failure Taxonomy + Analyzer Contract

**Date:** 2026-06-21
**Owner:** Person 2 — Claude (semantic taxonomy, report usefulness, prompt/rubric) + Codex (analyzer module, CLI, tests)
**Status:** Design approved by Claude; analyzer implementation handed to Codex.
**Reward invariant:** Nothing here touches the §1.4 GRPO reward. The whole loop is an
**eval-time, additive** diagnostic. `reward.py`, `verdict.py`, `fix_grader.py`,
`citation_gate.py`, and `schemas/{verdict,eval_result,trace,reward_spec}.json` stay byte-frozen.

---

## 1. Purpose

Train-eval produces, per trace, one frozen `eval_result` record (correctness booleans +
token counts) and one `verdict_sidecar` record (the raw + parsed verdict and a block of
deterministic **signals**). The **self-improvement loop** reads those, classifies every
**low-score / defective** run into a single **failure bucket**, and emits an
`improvement_record` that says *what kind of mistake it was, why we know, and which lever
fixes it* (prompt, tool, grader alias, dataset repair, new training example, or nothing).

The point is to convert a flat "mean reward fell to 0.74" into an actionable worklist:
*"9 of the 13 misses are `false_positive_clean` on rich cases → add hard clean negatives;
4 are `bad_failure_type` where the model said `test_failure` → add a grader alias."*

### Lanes

| Lane | Owner | Artifacts |
|---|---|---|
| Semantic taxonomy, fix interpretation, report usefulness, prompt/rubric | **Claude** | this note; `schemas/verdict_sidecar.json`; `schemas/improvement_record.json`; the **signal producer** `envs/loop_auditor_env/diagnostics.py` + the `verdicts.jsonl` emit in `eval_harness.py`; the golden acceptance fixture |
| Pure analyzer module + CLI + unit tests | **Codex** | `self_improve/analyzer.py` (signals → `improvement_record`), `self_improve/__main__.py` CLI, `self_improve/tests/` |

The split is deliberate: **all signal extraction that needs a trace, ground truth, or the
reward stack happens in the producer (Claude's lane)**, so Codex's analyzer is a pure
function over flat fields — no `loop_auditor_env` import, trivially testable against a
golden table.

---

## 2. Architecture

```
eval_harness.run_eval
   ├─ build_eval_record(...)          → eval_results.jsonl   (FROZEN 8-field schema, unchanged)
   └─ diagnostics.build_sidecar(...)  → verdicts.jsonl       (schemas/verdict_sidecar.json, NEW, additive)
                                            │  .signals = deterministic detection inputs
                                            ▼
                          self_improve.analyzer.classify(eval_result, sidecar)   ← Codex, PURE
                                            │
                                            ▼
                                  improvement_records.jsonl   (schemas/improvement_record.json)
                                            │
                                            ▼
                          report (group by bucket × fix_type, rank by severity)   ← Codex CLI / Person 3 dash
```

### Why a sidecar, not new `eval_result` fields

`schemas/eval_result.json` is `additionalProperties: false` and **FROZEN** — Person 3's
dashboard validates against it. It carries correctness booleans + token counts but **not the
verdict text** and **none of the signals** needed to tell *why* a run scored low. So the
diagnostic data rides in a **separate, optional** `verdicts.jsonl`, which the dashboard
loader already tolerates (it validates only the verdict *core* + envelope and ignores extra
keys — verified in `dashboard/loader.py:load_verdicts`). The producer extends that sidecar
with a namespaced `signals` object. No frozen contract changes.

### Why precompute signals in the producer

The analyzer must be deterministic and testable in isolation. If it re-derived citation
checks, fix-concept coverage, artifact availability, etc. from raw traces, it would import
the whole env/reward stack and drift from it. Instead the producer — which already holds
`(verdict, trace_view, ground_truth)` together inside `build_eval_record` — computes every
signal **once, with the same code paths the reward uses**, and writes them flat. Codex's
analyzer then applies a precedence tree over booleans/numbers.

---

## 3. Signal catalog (`verdict_sidecar.signals`)

Every signal is deterministic given `(raw_verdict, trace_view, ground_truth)`. Source =
`diagnostics.py`. Full types in `schemas/verdict_sidecar.json`.

| Signal | Type | Meaning / source |
|---|---|---|
| `verdict_parsed` | bool | `parse_verdict`+`validate_verdict` succeeded |
| `raw_present` | bool | raw output non-empty after strip |
| `raw_char_len` | int | length of raw verdict text |
| `failure_type_raw` | str\|null | model's original `failure_type` *before* normalization |
| `type_out_of_enum` | bool | normalized `failure_type` non-null and ∉ `FAILURE_TYPES` |
| `pred_fault_present` | bool | the auditor's `fault_present` (mirrored from the verdict core) |
| `gt_fault_present` | bool | trace is buggy (has planted fault) |
| `gt_step_id` / `gt_failure_type` | str\|null | ground-truth fault |
| `localization_correct` | bool | buggy: `pred_fault_present && predicted_step_id == gt_step_id`; **clean: mirrors `pred_fault_present == false`** (eval_harness). The analyzer must NOT read it as a step match on clean traces — use the fault-presence rules there. |
| `failure_type_correct` | bool | `failure_type == gt_failure_type` |
| `explanation_score` | 0..1 | deterministic 0.5-term (`fix_grader`, citation-gated) |
| `reward` | num | §1.4 scalar |
| `citation_passed` | bool | `citation_gate.check` passed |
| `fabricated_step_refs` | [str] | cited step_ids not in trace |
| `fix_grounded` | bool | structured `fix` OR linked base trace exists |
| `fix_concept_total` / `fix_concept_matched` | int | `fix_grader.expected_correction` group coverage |
| `gt_step_in_trace` | bool | planted `step_id` exists in the trace |
| `is_rich_case` | bool | `artifacts.resolve_case_dir` found a case dir |
| `artifact_count` | int | # public artifacts available |
| `artifact_tool_calls` | int\|null | # `list/read/search_artifacts` calls (null = unknown) |
| `inspection_tool_calls` | int\|null | # step/iteration inspection calls (null = unknown) |
| `proposed_fix_contains_code` | bool | proposed_fix looks like code (fence / `def`/`class`/`import` / diff hunk) |
| `explanation_empty` | bool | fault claimed but explanation blank |
| `references_path_token` | bool | explanation/fix names a file path/filename |

---

## 4. The taxonomy

Ten buckets. Eight are **primary** (assigned by the precedence tree §5); two
(`artifact_miss`, `prompt_confusion`) are **cross-cutting factors** that usually attach to a
primary but can be promoted to primary when nothing higher fired.

For each: **definition · deterministic detection · evidence shown · fix type · example diagnosis.**

> The §4 detection clauses are **descriptive**; §5's first-match `elif` chain is **authoritative**.
> Where a §4 clause restates earlier conjuncts (e.g. §4.4 re-asserting fault-presence + citation),
> §5 reaches that bucket purely as the residue after the higher rules already failed — implement
> from §5. All clauses use the signal name `pred_fault_present` (the verdict core, mirrored into
> `signals`).

### 4.1 `parse_failure`
- **Definition.** The auditor's final message did not yield a schema-valid verdict (empty,
  truncated mid-JSON, prose-only, wrong shape, or a clean/fault structural violation).
- **Detection.** `signals.verdict_parsed == false`.
- **Evidence.** `raw_present`, `raw_char_len`, first 200 chars of raw text.
- **Fix type.** `prompt_change` (reinforce "emit ONLY the JSON object"); if `raw_char_len`
  is at the output cap, the real lever is the token cap (`LOOP_AUDITOR_*_MAX_TOKENS` /
  disable `think`) — call that out in `suggested_action` but keep `fix_type=prompt_change`.
- **Example.** *"Run buggy-routing-002 (base) produced no parseable verdict (raw 2048 chars,
  unterminated JSON) — likely a truncated `<think>` ramble; tighten output or raise the cap."*

### 4.2 `false_positive_clean`
- **Definition.** The trace is **clean** but the auditor flagged a fault — over-flagging
  healthy self-correction. This is the single most damaging behavioral error: a clean trace
  scores 1.0 only if `fault_present` is false, so a false positive is a hard 0.
- **Detection.** `gt_fault_present == false AND pred_fault_present == true`.
- **Evidence.** `predicted_step_id`, `failure_type`, `explanation`; whether it also fabricated
  (`citation_passed`).
- **Fix type.** `new_training_example` (more hard clean negatives / recovered-fault traces);
  `prompt_change` as secondary (sharpen the "self-correction is CLEAN" rule).
- **Example.** *"Clean run clean-003 (base) was flagged `tool_misuse` at iter0.step1 — the
  auditor read a benign docstring edit as a fault; add recovered-fault clean negatives."*

### 4.3 `false_negative_buggy`
- **Definition.** The trace has a planted fault but the auditor called it clean — a miss.
- **Detection.** `gt_fault_present == true AND pred_fault_present == false`.
- **Evidence.** `gt_step_id`, `gt_failure_type`, `is_rich_case`, `artifact_tool_calls`.
- **Fix type.** `new_training_example` (more positives of this fault type); if it's a rich
  case the auditor never inspected (`artifact_miss` factor), `prompt_change`/`tool_change`.
- **Example.** *"Buggy run csv_header__routing (trained) was called clean — the skipped
  run_tests step at a004 was missed; it never opened the command logs (0 artifact calls)."*

### 4.4 `bad_localization`
- **Definition.** Right call that *a* fault exists, but blamed the wrong (real) step.
- **Detection.** `gt_fault_present && pred_fault_present && citation_passed && !localization_correct`.
  (Citation must pass — a cited step that doesn't exist is `fabricated_step_ref`, §4.7.)
- **Evidence.** `predicted_step_id` vs `gt_step_id`; `is_rich_case`, `artifact_tool_calls`.
- **Fix type.** `prompt_change` when `artifact_miss` co-fires (tell it to read the artifact
  before blaming a step); else `new_training_example` (localization is the core skill).
- **Example.** *"Buggy run config_bool__wrong_file_edit (base) blamed a007 but the planted
  fault is a003 — it guessed from the summary without reading the patch."*

### 4.5 `bad_failure_type`
- **Definition.** Step localized correctly, but the failure category is wrong.
- **Detection.** `localization_correct && !failure_type_correct`.
- **Evidence.** `failure_type` (normalized), `failure_type_raw`, `gt_failure_type`,
  `type_out_of_enum`, and a computed `suggested_alias` when applicable.
- **Fix type — branches deterministically:**
  - `type_out_of_enum == true` **and** the raw key isn't already an alias → **`grader_alias_change`**:
    recommend adding `{normalize_key(failure_type_raw): gt_failure_type}` to
    `config.FAILURE_TYPE_ALIASES`. Cheapest possible fix, no retrain.
  - else (model picked a *valid but wrong* enum, e.g. said `routing`, truth `tool_misuse`) →
    **`prompt_change`** / `new_training_example` (genuine category confusion).
- **Example (alias).** *"config_bool__tool_misuse (base) localized a008 correctly but typed it
  `test_failure` — a symptom name; add alias `test_failure → tool_misuse`."*
- **Example (confusion).** *"csv_header__routing (trained) localized a004 but typed it
  `tool_misuse`; routing vs tool_misuse are being conflated — clarify the rubric / add examples."*

### 4.6 `weak_fix`
- **Definition.** Localized + typed correctly, but the `proposed_fix` is too vague to cover
  the expected corrective concepts — the 0.5 explanation term stayed low.
- **Detection.** `localization_correct && failure_type_correct && explanation_score < 0.5`
  (and `citation_passed`).
- **Evidence.** `proposed_fix`, `fix_concept_matched` / `fix_concept_total`, the
  `expected_correction` groups it missed.
- **Fix type.** `prompt_change` (the rubric should ask the fix to name the corrective process
  action + the target); `new_training_example` as secondary.
- **Example.** *"config_bool__resource_misuse (trained) found a007 and typed it right but the
  fix ('clean it up') matched 0/2 expected concepts — it never said to read only the targeted
  file; rubric should require naming the corrective action."*

### 4.7 `fabricated_step_ref`
- **Definition.** The verdict prose cites a `step_id` that is not in the trace — a hallucinated
  reference. Already zeroes the explanation term in the reward; surfaced here because the fix
  (stop inventing ids) is distinct and prompt-addressable.
- **Detection.** `pred_fault_present && !citation_passed`. (Ranked above `bad_localization` so a
  fabricated blame is diagnosed as fabrication, not a wrong-but-real guess.)
- **Evidence.** `fabricated_step_refs`, `predicted_step_id`.
- **Fix type.** `prompt_change` (reinforce "copy step_ids VERBATIM from the trace; never cite
  an id you have not seen").
- **Example.** *"buggy-resource-001 (base) cited a99 in its explanation — no such step exists;
  the auditor invented an id. Reinforce verbatim step-id copying."*

### 4.8 `artifact_miss` *(cross-cutting factor; promotable to primary)*
- **Definition.** The case shipped real artifacts (repo/test logs/patches) the auditor could
  have read, it read none, and it got the call wrong — it guessed from the summary instead of
  inspecting evidence.
- **Detection (high confidence).** `is_rich_case && artifact_count > 0 && artifact_tool_calls == 0`
  (the auditor demonstrably read nothing).
- **Detection (candidate, when `artifact_tool_calls` is null/unknown).** `is_rich_case &&
  artifact_count > 0 && references_path_token`. Emit with `confidence=candidate` and **`log` the
  cap** (tool-call data was unavailable, so "read nothing" is inferred, not observed).
- **Role.** Computed independently and attached as a `contributing_factor` to whatever primary
  fired (typically `false_negative_buggy` or `bad_localization`); promoted to primary only when no
  §4.1–4.6 bucket fired (a low-severity "won the case without ever looking" advisory).
- **Evidence.** `artifact_count`, `artifact_tool_calls`, `is_rich_case`.
- **Fix type.** `prompt_change` ("on a rich case, list_artifacts + read the patch/log before
  asserting file contents"); `tool_change` if the tool surface is the blocker.
- **Example.** *"config_bool__wrong_file_edit (base): 14 artifacts available, the auditor
  opened 0 and mislocalized — it never read the patch it was judging."*

### 4.9 `prompt_confusion` *(cross-cutting factor; promotable to primary)*
- **Definition.** The model behaved in a way the **instructions** should have prevented:
  proposed CODE (the prompt says "the corrective PROCESS action, never code"), left the
  explanation blank, or invented an out-of-enum failure type. Signals the prompt/rubric needs
  a targeted clarification (or a grader alias).
- **Detection.** `proposed_fix_contains_code || explanation_empty || (type_out_of_enum && !failure_type_correct)`.
- **Role.** `contributing_factor` by default; primary only when no higher bucket fired (e.g.
  full-credit run that nonetheless proposed code → a low-severity advisory).
- **Evidence.** which sub-signal fired; `failure_type_raw` if out-of-enum.
- **Fix type.** `prompt_change`; `grader_alias_change` when it's purely an out-of-enum synonym
  that should be aliased rather than re-prompted.
- **Example.** *"config_bool__safety (base) proposed a code patch in `proposed_fix` despite the
  process-only instruction — tighten the 'never code' line / add a worked counter-example."*

### 4.10 `dataset_issue`
- **Definition.** The ground truth / case is itself broken or **structurally ungradeable** — the
  model is not at fault and **must not be blamed**. Two deterministic cases: (a) the planted
  `step_id` isn't in the trace; (b) the 0.5 fix term has *no way* to be graded — `fix_concept_total
  == 0`, which happens only when the planted `failure_type` is not one of the five enum values
  (so `expected_correction` yields no groups) or a structured `fix` is empty.
- **Not a dataset_issue:** a buggy trace that merely lacks a linked base clean trace
  (`fix_grounded == false`) is still gradeable via the concept-group fallback — that's a
  Person-1 *linking-health* signal, surfaced as evidence, **not** a reason to discard the run.
  (Over-triggering here would mask real model errors.)
- **Detection.** `gt_fault_present && (!gt_step_in_trace || fix_concept_total == 0)`. **Highest precedence.**
- **Evidence.** `gt_step_id`, `gt_step_in_trace`, `gt_failure_type`, `fix_concept_total`,
  `fix_grounded` (informational), `run_id`.
- **Fix type.** `dataset_repair` (fix the planted step/label; relink the base trace; flag to Person 1).
- **Example.** *"buggy run csv_header__routing has planted step a004 absent from the trace — the
  ground truth points at a step that isn't there; repair the label before counting this run."*

---

### 4.11 Acknowledged out-of-scope (deliberately NOT buckets)

These are real but either undetectable deterministically or a different problem; calling them out
keeps the worklist honest rather than silently mis-bucketing them.

- **GATE / Design-Y mode.** This loop covers **AUDIT-mode verdicts only**. Gate rollouts
  (`reward.py:compute_gate_reward`; decisions `flag`/`stop`/`completed`, `stop_iteration` vs
  `fault_iteration`, a token-cost term) have a structurally different failure surface
  (false-abort-on-clean, missed-catch, flagged-before-the-fault, wrong gate type) that none of the
  10 buckets model. **Structural guard:** `eval_harness.run_eval` emits the sidecar only for
  `mode == "audit"` scenarios, so gate runs never reach `classify`. A future gate taxonomy is its
  own work item — do not feed gate `eval_result`s here.
- **Correct-but-unsupported (right answer, wrong reasoning).** A run can be localized + typed
  correctly with a citation-clean explanation that scores ≥ 0.5 by *concept-keyword overlap* while
  the reasoning is actually bogus. The deterministic signals **cannot** catch this (the 0.5 term is
  a proxy, not a correctness oracle). It is routed to the **eval-time judge** (`judge.py`
  `specificity`/`causal_soundness`) surfaced in the §9 report next to full-credit runs — never
  claimed as deterministically "healthy."
- **Cost / inefficiency.** A correct-but-expensive run (near `AUDITOR_EVAL_MAX_TOKENS`, hit the
  step cap, or heavy tool churn) is not a *correctness* failure, so it is not a bucket. The
  producer already carries `auditor_tokens` (eval_result) + `inspection_tool_calls` — the §9 report
  shows an **efficiency view** over those; a dedicated `inefficient_run` advisory is a future add.

## 5. Precedence decision tree (the deterministic core for Codex)

A run gets **at most one primary `bucket`**. Apply top-to-bottom; **first match wins** —
this guarantees mutual exclusivity. `s` = `sidecar.signals`. Constants: `EXPL_OK = 0.5`.

```
def classify(eval_result, sidecar) -> ImprovementRecord | None:
    s = sidecar.signals

    # ---- compute the two cross-cutting factor predicates up front ----
    artifact_miss   = _artifact_miss(s)        # (definition §4.8) -> (matched: bool, confidence)
    prompt_confusion = _prompt_confusion(s)    # (definition §4.9) -> bool

    primary = None
    # 1. DATASET INTEGRITY — never blame the model on broken ground truth.
    #    (fix_grounded==false alone is NOT enough — concept fallback still grades it.)
    if s.gt_fault_present and (not s.gt_step_in_trace or s.fix_concept_total == 0):
        primary = "dataset_issue"
    # 2. PARSE — no verdict to judge
    elif not s.verdict_parsed:
        primary = "parse_failure"
    # 3. FAULT-PRESENCE DISAGREEMENT  (pred_fault_present mirrors the verdict core)
    elif (not s.gt_fault_present) and s.pred_fault_present:
        primary = "false_positive_clean"
    elif s.gt_fault_present and (not s.pred_fault_present):
        primary = "false_negative_buggy"
    # ---- from here: gt buggy, model claimed a fault ----
    # 4. FABRICATION (cited a non-existent step)
    elif not s.citation_passed:
        primary = "fabricated_step_ref"
    # 5. LOCALIZATION
    elif not s.localization_correct:
        primary = "bad_localization"
    # 6. FAILURE TYPE
    elif not s.failure_type_correct:
        primary = "bad_failure_type"
    # 7. WEAK FIX  (a GRADEABLE, citation-clean fix that under-covered)
    elif _weak_fix(s):
        primary = "weak_fix"
    # 8/9. CROSS-CUTTING PROMOTED TO PRIMARY (nothing above fired)
    elif artifact_miss.matched:
        primary = "artifact_miss"
    elif prompt_confusion:
        primary = "prompt_confusion"
    else:
        return None                      # healthy run, no record

    # ---- contributing factors: every other predicate that fired ----
    factors = []
    if artifact_miss.matched and primary != "artifact_miss":     factors.append("artifact_miss")
    if prompt_confusion       and primary != "prompt_confusion": factors.append("prompt_confusion")
    if (not s.citation_passed) and primary != "fabricated_step_ref": factors.append("fabricated_step_ref")
    # NB: weak_fix is PRIMARY-ONLY — whenever _weak_fix(s) holds, the elif chain
    # has already reached rule 7 (no earlier rule can fire), so it is never a factor.

    # suggested_alias only drives bad_failure_type (else {}). It is structurally
    # unreachable on a prompt_confusion primary — that requires failure_type_correct,
    # which contradicts _suggested_alias's type_out_of_enum requirement.
    alias = _suggested_alias(s) if primary == "bad_failure_type" else {}

    return ImprovementRecord(
        run_id=eval_result.run_id, model=eval_result.model, reward=s.reward,
        bucket=primary, contributing_factors=factors,
        fix_type=_fix_type(primary, s, factors, alias),           # §6
        confidence=_confidence(primary, artifact_miss),           # high unless candidate artifact_miss
        severity=_severity(s.reward, primary),                    # 0 -> high; partial -> medium; full+flag -> low
        evidence=_evidence(primary, s),                          # bucket-specific
        suggested_alias=alias,
        diagnosis=_diagnosis(primary, s), suggested_action=_action(primary, s, factors),
    )

# _weak_fix: a fix that is gradeable (concept groups exist), citation-clean (its
# low score is NOT a fabrication artifact), localized + typed right, yet still
# under-covered the expected corrective concepts.
def _weak_fix(s):
    return (s.localization_correct and s.failure_type_correct and s.citation_passed
            and s.fix_concept_total > 0 and s.explanation_score < EXPL_OK)
```

**Defective gate.** The tree only returns a record when something is wrong. A run that is
parsed, agrees on fault presence, localizes + types correctly, passes citation, has
`explanation_score ≥ 0.5`, and trips no cross-cutting factor → `None`. (So a full-reward run
that *also* proposed code still surfaces as a low-severity `prompt_confusion` advisory — by
design, to catch latent drift before it costs reward.)

### Worked precedence cases (these become the golden table)

| Scenario | primary | factors |
|---|---|---|
| clean trace, flagged fault, cited fake id | `false_positive_clean` | `fabricated_step_ref` |
| buggy, said clean, rich case, 0 artifact reads | `false_negative_buggy` | `artifact_miss` |
| buggy, blamed wrong **real** step, 0 artifact reads | `bad_localization` | `artifact_miss` |
| buggy, blamed a **fake** step id | `fabricated_step_ref` | — |
| right step, typed `test_failure` (out-of-enum) | `bad_failure_type` | `prompt_confusion` |
| right step+type, fix matched 0/2 concepts | `weak_fix` | — |
| planted step_id absent from trace | `dataset_issue` | — |
| empty/truncated output | `parse_failure` | — |
| full credit but proposed a code block | `prompt_confusion` | — |

---

## 6. `fix_type` decision rules (deterministic)

```
def _fix_type(primary, s, factors, alias):    # alias = the gated _suggested_alias (may be {})
    if primary == "dataset_issue":          return "dataset_repair"
    if primary == "parse_failure":          return "prompt_change"   # note token-cap in action text
    # cheapest lever first: a structural cause (fabrication/code) is prompt-addressable;
    # only fall back to retraining when the clean trace genuinely lacks hard negatives.
    if primary == "false_positive_clean":   return "prompt_change" if ({"fabricated_step_ref","prompt_confusion"} & set(factors)) else "new_training_example"
    if primary == "false_negative_buggy":   return "prompt_change" if "artifact_miss" in factors else "new_training_example"
    if primary == "fabricated_step_ref":    return "prompt_change"
    if primary == "bad_localization":       return "prompt_change" if "artifact_miss" in factors else "new_training_example"
    if primary == "bad_failure_type":       return "grader_alias_change" if alias else "prompt_change"
    if primary == "weak_fix":               return "prompt_change"
    if primary == "artifact_miss":          return "prompt_change"
    if primary == "prompt_confusion":       return "prompt_change"   # alias is structurally unreachable here (see §6 note)
```

### `suggested_alias` (the cheap win)

```
FAILURE_TYPES = ("resource_misuse","tool_misuse","routing","safety","wrong_file_edit")

def _normalize_key(t):                 # mirrors config.normalize_failure_type's key step
    return "_".join(t.strip().lower().replace("-", " ").split())

def _suggested_alias(s):
    # the model named an out-of-enum type, the truth IS a real enum value, and the
    # alias is non-degenerate (key != value). Guards against aliasing toward a
    # clean/None gt or toward another invalid type (a dataset_issue, not an alias).
    if (s.type_out_of_enum and s.failure_type_raw
            and s.gt_failure_type in FAILURE_TYPES):
        key = _normalize_key(s.failure_type_raw)
        if key != s.gt_failure_type:
            return {key: s.gt_failure_type}
    return {}
```

`grader_alias_change` is the only fix the loop can *propose as a one-line code edit*: add the
mapping to `config.FAILURE_TYPE_ALIASES`. (A human still applies + re-baselines it; the loop
never edits config itself.)

### The two cross-cutting predicates

```
class _Match:                 # tiny carrier: did it fire, and at what confidence
    matched: bool; confidence: str   # confidence ∈ {"high","candidate"}

def _artifact_miss(s) -> _Match:
    if not (s.is_rich_case and s.artifact_count > 0):
        return _Match(False, "high")
    if s.artifact_tool_calls is not None:                 # observed
        return _Match(s.artifact_tool_calls == 0, "high")
    return _Match(s.references_path_token, "candidate")   # inferred (tool data unavailable)

def _prompt_confusion(s) -> bool:
    # only meaningful on a PARSED verdict; the type-confusion clause needs a real
    # fault to mis-categorize (skip it on clean traces, where there's no gt type).
    if not s.verdict_parsed:
        return False
    return (s.proposed_fix_contains_code
            or s.explanation_empty
            or (s.type_out_of_enum and not s.failure_type_correct and s.gt_fault_present))
```

`_confidence(primary, am)` = `"candidate"` iff `primary == "artifact_miss"` and `am.confidence ==
"candidate"`; else `"high"`. Whenever `artifact_miss` appears (primary **or** factor), record
`evidence.artifact_miss_confidence = am.confidence` and `evidence.artifact_tool_calls`
(`None` ⇒ inferred, not observed), so the report can tell an *observed* zero-read miss from an
*inferred* one even when the record-level `confidence` is `"high"` (driven by the primary).

`_severity(reward, primary)`:
- `primary == "dataset_issue"` → `"high"` — a broken-ground-truth row is data-severity (fix the
  data first), NOT model-severity; its `reward` is meaningless, so it must not be graded by it.
- else `"high"` if `reward <= 0`; `"low"` if `primary in {"artifact_miss","prompt_confusion"}`
  (promoted factors only fire on otherwise-full-credit runs); else `"medium"`.

---

## 7. Eval-output gap analysis → minimal extra fields

**Before:** `eval_results.jsonl` (8 frozen fields) is enough to *count* misses, not to
*classify* them. None of the 10 buckets is decidable from it alone:

| Bucket | Missing signal in `eval_result` |
|---|---|
| parse_failure | whether the verdict parsed |
| false_positive_clean / false_negative_buggy | `gt_fault_present` vs `fault_present` |
| bad_localization | nothing extra (derivable) — but needs to be split from fabrication |
| bad_failure_type | `failure_type_raw`, `type_out_of_enum` for the alias branch |
| weak_fix | `fix_concept_matched/total` |
| fabricated_step_ref | `citation_passed`, `fabricated_step_refs` |
| artifact_miss | `is_rich_case`, `artifact_count`, `artifact_tool_calls` |
| prompt_confusion | `proposed_fix_contains_code`, `explanation_empty`, `type_out_of_enum` |
| dataset_issue | `gt_step_in_trace`, `fix_concept_total` |

**After:** all of it lands in `verdict_sidecar.signals` (§3), produced by `diagnostics.py` and
emitted by `eval_harness.run_eval` as `verdicts.jsonl`. **No change to `eval_result`; no change
to the reward.** This is the "minimal extra fields" answer: one optional sidecar, one `signals`
object, computed with the reward stack's own helpers.

### Honest caps (logged, not hidden)
- `artifact_tool_calls` / `inspection_tool_calls` come from walking the HUD trace; on a HUD
  version where the step shape differs they are `null` (**unknown**, not 0). `artifact_miss`
  then degrades to a `candidate` heuristic — the analyzer must not treat unknown as "read none."
- `proposed_fix_contains_code` is a conservative lexical check (fences / `def`/`class`/`import`
  / diff hunks). It can miss cleverly-disguised code; it should not false-positive on prose that
  merely names `run_tests` or a path.

---

## 8. Prompt / rubric recommendations (gated — not auto-applied)

The env `INSTRUCTIONS` are already process-focused and explicit; do **not** churn them. These
are *targeted* clarifications, each tied to a bucket, to apply **only after a re-baseline shows
the bucket is frequent** (a prompt change alters every rollout):

1. **`fabricated_step_ref` ↑** → after the verbatim-id line add:
   *"If you are unsure a step_id exists, call get_step to confirm it before citing it. Never
   cite a step_id you have not seen in the summary or a tool result."*
2. **`weak_fix` ↑** → in the JSON spec, annotate `proposed_fix`:
   *"name the corrective PROCESS action AND the target it should act on (e.g. 'run the focused
   tests before submitting', 'edit src/config.py instead of config_helpers.py')."*
3. **`artifact_miss` ↑ on rich cases** → add:
   *"When list_artifacts shows files, READ the patch/log/test-output you are judging before
   asserting what it contains."*
4. **`prompt_confusion` (code in fix) ↑** → strengthen the existing clause to a hard negative:
   *"proposed_fix is a PROCESS instruction in prose. Do NOT include code, diffs, or commands."*

**Rubric note (report-facing only, not the GRPO reward):** the eval-time judge in `judge.py`
already scores `specificity`; surface its per-dim scores next to `weak_fix` records so a human
can see *vague vs wrong*. The judge stays out of the reward path.

`bad_failure_type` driven by an out-of-enum synonym is **not** a prompt change — it's a
`grader_alias_change` (§6), which is strictly cheaper and safer than re-prompting.

---

## 9. Report usefulness (what the loop should show)

The improvement report is the actual deliverable a human reads each eval. Suggested layout
(Codex CLI `--report`, or Person 3 dashboard panel):

1. **Reward-leak summary** — for `base` and `trained`: count of records by `bucket`, and the
   reward recovered if each bucket were fixed (Σ of `(max_reward − reward)` per bucket). Sorted
   so the biggest lever is on top. **Exclude from this ranking:** `dataset_issue` (not the model's
   fault) and any `confidence == "candidate"` primary (e.g. inferred `artifact_miss` on a
   full-credit run — it carries `(max_reward − reward) == 0`, so it adds rows but no recoverable
   reward). List both in a separate "advisories / data-repairs" section.
2. **Fix worklist** — group by `fix_type`; within each, the runs + one-line `suggested_action`.
   `grader_alias_change` rows show the exact `{raw: canonical}` to add (one-line, copy-paste).
   `dataset_repair` rows are separated and **excluded from model-quality stats** (not the
   model's fault).
3. **Per-run drill-down** — `run_id`, `bucket`, `contributing_factors`, `evidence`, `diagnosis`,
   the base-vs-trained verdicts side by side (the existing sidecar core).
4. **Regression guard** — a **per-`run_id` paired diff**, not a bucket-count delta (aggregate
   counts can stay flat while individual runs flip — a Simpson's-paradox trap). For each `run_id`
   present under both `base` and `trained` (same dataset/split, so ids align), flag the ids whose
   `trained` bucket is strictly worse or whose `reward` dropped, and list those ids. This is the
   single most useful training signal.
5. **Efficiency view** — over `auditor_tokens` (eval_result) + `inspection_tool_calls` /
   `artifact_tool_calls` (sidecar): correct-but-expensive runs (near `AUDITOR_EVAL_MAX_TOKENS` or
   high tool churn). Informational (cost, not correctness — see §4.11), but it's where the §8
   "read the artifact" / "confirm the step" prompt edits get re-baselined for cost, not just bucket
   frequency.

Determinism makes this trustworthy: same eval inputs → byte-identical report.

---

## 10. Coordination with Codex

**Module home (proposed):** `self_improve/` at repo root.
- `self_improve/analyzer.py` — `classify(eval_result: dict, sidecar: dict | None) -> dict | None`
  and `analyze(eval_results: list, sidecars: dict) -> list[dict]`. **Pure.** No
  `loop_auditor_env` import. Reads `schemas/improvement_record.json` for nothing at runtime —
  it just constructs conforming dicts; tests validate against the schema.
- `self_improve/__main__.py` — CLI: `python -m self_improve --results eval_results.jsonl
  --verdicts verdicts.jsonl [--report]` → writes `improvement_records.jsonl` (+ optional report).
- `self_improve/tests/` — unit tests over the **golden acceptance fixture** (below).

**Import boundary.** The analyzer depends only on: the two JSONL inputs, and a tiny local
`_normalize_key` (4 lines, §6). It does **not** import the env, reward, fix_grader, citation_gate,
or HUD. All trace/gt-derived truth arrives precomputed in `signals`.

**Producer is mine (Claude), ready for you to consume:**
- `envs/loop_auditor_env/diagnostics.py` → `build_sidecar_record(run_id, model_tag, raw_verdict,
  trace_view, ground_truth) -> dict` conforming to `schemas/verdict_sidecar.json`.
- `eval_harness.run_eval` writes `verdicts.jsonl` next to `eval_results.jsonl`.

**Golden acceptance fixture (mine → your test oracle):**
`self_improve/fixtures/improvement_cases.jsonl` — each line is
`{"eval_result": {...}, "sidecar": {...}, "expect": {"bucket": ..., "fix_type": ...,
"contributing_factors": [...], "confidence": ..., "suggested_alias": {...}}}`. Your tests assert
`classify(case.eval_result, case.sidecar)` matches `case.expect`. I own keeping this table in
sync with this note; you own the analyzer that passes it. **If you want me to add/clarify a
signal or a case, ping in the handoff and I'll extend the producer — don't re-derive it in the
analyzer.**

**Do-not-overlap.** I will not build the analyzer/CLI. You will not edit the producer, the
schemas, the prompts, or the reward. Shared contract = these two schemas + this note.

---

## 11. Determinism & testability guarantees

- Every signal is a pure function of `(raw_verdict, trace_view, ground_truth)`; the producer
  uses the **same** `verdict.py` / `citation_gate.py` / `fix_grader.expected_correction` /
  `artifacts.resolve_case_dir` the reward path uses → no drift.
- The analyzer is a pure function of flat signals → first-match precedence → one record. No
  clocks, no randomness, no I/O beyond reading the two JSONLs.
- Mutual exclusivity of `bucket` is structural (first-match `elif` chain), not a convention.
- The golden table pins the full mapping; `improvement_record.json` pins the shape. CI green =
  taxonomy honored.
- **Reward untouched:** the loop reads eval artifacts and writes diagnostics. It can be deleted
  without changing a single rollout.
```
