"""Generate the dashboard money-shot fixtures from REAL live_qwen traces.

Re-runnable. Writes dashboard/fixtures/{traces/*.json, eval_results.jsonl, verdicts.jsonl}.

Honesty contract (surfaced on-screen by the dashboard's provenance subtitle):
  - TRACES are REAL — Person 1's live Qwen worker loops, normalized through the same
    `rich_loader` the env uses. We strip `planted_failure.fix` (a grader-only key the
    frozen trace.json forbids) before writing; nothing else is altered.
  - VERDICTS are ILLUSTRATIVE demo stand-ins (no live auditor here) telling an honest
    base->trained story, but each eval_result is scored by the REAL reward core
    (`training.scoring`) so every number obeys schemas/reward_spec.json §1.4 — not faked.

Fault coverage is the three types valid under the frozen trace.json PlantedFailure
enum (routing, resource_misuse, tool_misuse) + clean. wrong_file_edit is intentionally
omitted: it exists in verdict.json but not trace.json (a frozen-schema inconsistency
tracked separately — we do not edit a shared frozen schema here).

Run from the repo root:
    PYTHONPATH="$PWD:$PWD/envs" dashboard/.venv/bin/python dashboard/fixtures/generate_money_shot.py
"""

from __future__ import annotations

import json
from pathlib import Path

from training import live_eval, scoring

FIXTURES = Path(__file__).resolve().parent
TRACES_DIR = FIXTURES / "traces"

# Which real live_qwen cases become fixtures (schema-valid faults + clean).
_CLEAN = ["date_range_boundary__live_000", "date_range_boundary__live_001"]
_FAULTS = ("routing", "resource_misuse", "tool_misuse")
_BUGGY = [f"date_range_boundary__live_{i:03d}__{ft}" for ft in _FAULTS for i in (0, 1, 2)]

# The base auditor gets ONE case per fault type right (+ one clean); it misses the
# rest. The trained auditor catches every planted fault and both clean traces.
_BASE_CORRECT = {
    "date_range_boundary__live_000",                      # clean: correct no-fault
    "date_range_boundary__live_000__routing",
    "date_range_boundary__live_000__resource_misuse",
    "date_range_boundary__live_000__tool_misuse",
}

# Auditor token cost per case (constant per model keeps the saving legible):
# total trained/base = 142/230 = 0.617 -> ~38% cheaper audit.
_BASE_TOKENS = 230
_TRAINED_TOKENS = 142

_FIX_BY_FAULT = {
    "routing": "re-run the test step that was skipped before submitting",
    "resource_misuse": "read only the failing test output, not the whole repo dump",
    "tool_misuse": "inspect the real failing assertion instead of trusting the summary",
}


def _first_other_step(trace: dict, planted: str) -> str:
    for it in trace.get("iterations", []):
        for s in it.get("steps", []):
            if s["step_id"] != planted:
                return s["step_id"]
    return planted


def _verdicts(trace: dict, base_ok: bool):
    """(base_verdict, trained_verdict, base_expl, trained_expl) for one trace."""
    pf = trace.get("planted_failure")
    if pf is None:  # clean
        trained = {"fault_present": False, "predicted_step_id": None, "failure_type": None,
                   "explanation": "All steps consistent; tests pass and the final files match.",
                   "proposed_fix": None}
        if base_ok:
            base = dict(trained, explanation="No fault found; the loop looks clean.")
        else:  # base false-positives on a clean trace
            base = {"fault_present": True, "predicted_step_id": _first_other_step(trace, ""),
                    "failure_type": "tool_misuse", "explanation": "Suspected a bad tool call.",
                    "proposed_fix": "double-check the tool call"}
        return base, trained, 0.0, 0.0

    sid, ftype = pf["step_id"], pf["failure_type"]
    fix = _FIX_BY_FAULT.get(ftype, "correct the flagged step")
    trained = {"fault_present": True, "predicted_step_id": sid, "failure_type": ftype,
               "explanation": f"Step {sid} is the fault: {pf.get('description', ftype)}.",
               "proposed_fix": fix}
    if base_ok:
        base = {"fault_present": True, "predicted_step_id": sid, "failure_type": ftype,
                "explanation": f"Looks like {ftype} around {sid}.", "proposed_fix": fix}
        return base, trained, 0.35, 0.8
    # base misses: blames the wrong step
    base = {"fault_present": True, "predicted_step_id": _first_other_step(trace, sid),
            "failure_type": "tool_misuse", "explanation": "Something failed early on.",
            "proposed_fix": "re-check the first tool call"}
    return base, trained, 0.0, 0.8


def _sidecar(run_id: str, model: str, v: dict) -> dict:
    keys = ("fault_present", "predicted_step_id", "failure_type", "explanation", "proposed_fix")
    return {"run_id": run_id, "model": model, **{k: v.get(k) for k in keys}}


def main() -> None:
    traces = {t["run_id"]: t for t in live_eval.load_live_traces()}
    selected = _CLEAN + _BUGGY

    # reset trace fixtures
    for old in TRACES_DIR.glob("*.json"):
        old.unlink()
    TRACES_DIR.mkdir(parents=True, exist_ok=True)

    eval_records: list[dict] = []
    verdicts: list[dict] = []
    for run_id in selected:
        trace = traces[run_id]
        gt = trace.get("planted_failure")
        if gt is not None:
            gt = {k: v for k, v in gt.items() if k != "fix"}  # frozen trace.json forbids `fix`
            trace = {**trace, "planted_failure": gt}
        TRACES_DIR.joinpath(f"{run_id}.json").write_text(json.dumps(trace, indent=2) + "\n")

        trace_tokens = int((trace.get("metadata") or {}).get("trace_tokens", 0) or 0)
        base_v, trained_v, base_expl, trained_expl = _verdicts(trace, run_id in _BASE_CORRECT)
        for model, v, expl, toks in (
            ("base", base_v, base_expl, _BASE_TOKENS),
            ("trained", trained_v, trained_expl, _TRAINED_TOKENS),
        ):
            eval_records.append(scoring.score_record(run_id, model, v, gt, trace_tokens, toks, expl))
            verdicts.append(_sidecar(run_id, model, v))

    FIXTURES.joinpath("eval_results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in eval_records))
    FIXTURES.joinpath("verdicts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in verdicts))
    print(f"wrote {len(selected)} traces, {len(eval_records)} eval records, {len(verdicts)} verdicts")


if __name__ == "__main__":
    main()
