"""Base-eval baseline: run the auditor over traces and emit dashboard-ready output.

Produces the `base` baseline (`eval_results.<tag>.jsonl` + `verdicts.<tag>.jsonl`)
independently of HUD, by driving any `InferenceBackend` (DummyBackend for tests,
ModalBackend for the real base Qwen). Records are validated against the frozen
schemas/eval_result.json before they're written — the same trust boundary the
dashboard enforces on read.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import prompt as prompt_mod
from . import scoring

PKG_DIR = Path(__file__).resolve().parent
SCHEMAS_DIR = PKG_DIR.parent / "schemas"
VERDICT_KEYS = ("fault_present", "predicted_step_id", "failure_type", "explanation", "proposed_fix")


def _eval_result_validator():
    from jsonschema import Draft202012Validator

    return Draft202012Validator(json.loads((SCHEMAS_DIR / "eval_result.json").read_text()))


def aggregate(records: list[dict]) -> dict:
    """Dashboard-facing aggregates over eval-result records."""
    n = len(records) or 1
    return {
        "n": len(records),
        "localization_accuracy": sum(r["localization_correct"] for r in records) / n,
        "failure_type_accuracy": sum(r["failure_type_correct"] for r in records) / n,
        "mean_explanation_score": statistics.fmean(r["explanation_score"] for r in records) if records else 0.0,
        "mean_reward": statistics.fmean(r["reward"] for r in records) if records else 0.0,
        "total_trace_tokens": sum(r["trace_tokens"] for r in records),
        "total_auditor_tokens": sum(r["auditor_tokens"] for r in records),
    }


def _write_jsonl(rows: list[dict], path: Path) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _sidecar(run_id: str, model_tag: str, verdict: dict) -> dict:
    return {"run_id": run_id, "model": model_tag, **{k: verdict.get(k) for k in VERDICT_KEYS}}


def deterministic_explanation_scorer(base_traces_dir=None):
    """Default explanation scorer: DETERMINISTIC fix-by-comparison + citation gate.

    Reuses Person 2's PURE modules (`fix_grader`, `citation_gate`) so the base
    baseline is scored byte-identically to the trained side (`eval_harness`) — the
    only way base-vs-trained is a fair comparison. No LLM judge in the loop (cost).
    Importing loop_auditor_env needs `envs/` on the path (root pyproject sets it).
    """
    from loop_auditor_env import citation_gate, fix_grader
    from loop_auditor_env import config as la_config

    base_dir = base_traces_dir or la_config.BASE_TRACES_DIR

    def score(verdict: dict, ground_truth: dict, view: dict) -> float:
        s = fix_grader.grade_fix(verdict, ground_truth, view, base_dir)
        # Conservative anti-hallucination: a fabricated step ref zeros the score.
        if not citation_gate.check(verdict, view)["passed"]:
            return 0.0
        return float(s)

    return score


def run_base_eval(
    traces: list[dict],
    backend,
    *,
    model_tag: str = "base",
    explanation_scorer=None,
    serialize_fn=None,
    out_dir=None,
    max_tokens: int = 512,
    validate: bool = True,
) -> dict:
    """Run the auditor over `traces`, write JSONL (if `out_dir`), return aggregates.

    `explanation_scorer(verdict, ground_truth, view) -> float` is called ONLY when the
    auditor localizes a real fault correctly. Defaults to the deterministic scorer
    (identical to the trained side); pass an LLM-judge scorer only for eval-time
    refinement, never in a GRPO loop.
    """
    build = serialize_fn or prompt_mod.build_messages
    validator = _eval_result_validator() if validate else None
    scorer = explanation_scorer
    records: list[dict] = []
    verdicts: list[dict] = []

    for trace in traces:
        view, gt = scoring.strip_ground_truth(trace)
        text, auditor_tokens = backend.complete(build(view), max_tokens=max_tokens)
        try:
            verdict = scoring.parse_verdict(text)
        except ValueError:
            # A base model that fails to emit JSON => wrong verdict, reward 0 (no crash).
            verdict = {"fault_present": None, "predicted_step_id": None, "failure_type": None,
                       "explanation": str(text)[:300], "proposed_fix": None}

        explanation_score = 0.0
        if gt is not None and verdict.get("predicted_step_id") == gt["step_id"]:
            if scorer is None:  # lazy default: only imports loop_auditor_env when needed
                scorer = deterministic_explanation_scorer()
            explanation_score = float(scorer(verdict, gt, view))

        record = scoring.score_record(
            trace["run_id"], model_tag, verdict, gt,
            scoring.count_trace_tokens(trace), auditor_tokens, explanation_score,
        )
        if validator is not None:
            validator.validate(record)
        records.append(record)
        verdicts.append(_sidecar(trace["run_id"], model_tag, verdict))

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write_jsonl(records, out / f"eval_results.{model_tag}.jsonl")
        _write_jsonl(verdicts, out / f"verdicts.{model_tag}.jsonl")
    return aggregate(records)
