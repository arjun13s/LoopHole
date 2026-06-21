"""Pure analyzer for Loop-Auditor self-improvement records.

This module consumes frozen eval_result rows plus verdict_sidecar rows emitted by
``loop_auditor_env.diagnostics``. It reads only ``sidecar["signals"]`` and does
not import the env, HUD, network clients, or model judges.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


EXPL_OK = 0.5
FAILURE_TYPES = (
    "resource_misuse",
    "tool_misuse",
    "routing",
    "safety",
    "wrong_file_edit",
)
PRIMARY_ORDER = (
    "dataset_issue",
    "parse_failure",
    "false_positive_clean",
    "false_negative_buggy",
    "fabricated_step_ref",
    "bad_localization",
    "bad_failure_type",
    "weak_fix",
    "artifact_miss",
    "prompt_confusion",
)
RECOMMENDED_FIX_TYPES = {
    "dataset_issue": "dataset_or_sidecar",
    "parse_failure": "verdict_format",
    "false_positive_clean": "clean_trace_calibration",
    "false_negative_buggy": "fault_detection",
    "fabricated_step_ref": "citation_grounding",
    "bad_localization": "localization",
    "bad_failure_type": "failure_type_taxonomy",
    "weak_fix": "fix_quality",
    "artifact_miss": "artifact_inspection",
    "prompt_confusion": "prompt_clarity",
}


class _ArtifactMatch:
    def __init__(self, matched: bool, confidence: str = "high") -> None:
        self.matched = matched
        self.confidence = confidence


def read_jsonl(path: "str | Path") -> list[dict]:
    """Read a JSONL file into object rows."""
    rows = []
    for line_no, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: JSONL row must be an object")
        rows.append(row)
    return rows


def write_jsonl(rows: list[dict], path: "str | Path") -> Path:
    """Write deterministic JSONL."""
    out = Path(path)
    out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return out


def sidecar_index(sidecars: list[dict]) -> dict[tuple[str, str], dict]:
    """Index sidecars by (run_id, model), preserving base vs trained."""
    indexed = {}
    for row in sidecars:
        key = (str(row.get("run_id", "")), str(row.get("model", "")))
        if all(key):
            indexed[key] = row
    return indexed


def classify(eval_result: dict, sidecar: "dict | None") -> "dict | None":
    """Return one improvement record for a defective run, or None if healthy."""
    if sidecar is None or not isinstance(sidecar.get("signals"), dict):
        return _missing_sidecar_record(eval_result)

    s = sidecar["signals"]
    artifact_miss = _artifact_miss(s)
    prompt_confusion = _prompt_confusion(s)
    alias = _suggested_alias(s)

    primary = _primary_bucket(s, artifact_miss, prompt_confusion)
    if primary is None:
        return None

    factors = _contributing_factors(primary, s, artifact_miss, prompt_confusion)
    if primary == "bad_failure_type":
        alias = _suggested_alias(s)
    else:
        alias = {}

    buckets = sorted({primary, *factors})
    record = {
        "run_id": str(eval_result.get("run_id", "")),
        "model": str(eval_result.get("model", "")),
        "reward": _num(s.get("reward", eval_result.get("reward", 0.0))),
        "bucket": primary,
        "buckets": buckets,
        "contributing_factors": sorted(factors),
        "fix_type": _fix_type(primary, s, factors, alias),
        "recommended_fix_type": RECOMMENDED_FIX_TYPES[primary],
        "confidence": _confidence(primary, artifact_miss),
        "severity": _severity(_num(s.get("reward", eval_result.get("reward", 0.0))), primary),
        "suggested_alias": alias,
        "evidence": _evidence(primary, s, artifact_miss),
        "notes": _notes(buckets, s, artifact_miss),
        "diagnosis": _diagnosis(primary, s),
        "suggested_action": _action(primary, s, factors, alias),
    }
    return record


def analyze(eval_results: list[dict], sidecars: dict[tuple[str, str], dict]) -> list[dict]:
    """Classify all eval rows, dropping healthy runs."""
    records = []
    for row in eval_results:
        key = (str(row.get("run_id", "")), str(row.get("model", "")))
        record = classify(row, sidecars.get(key))
        if record is not None:
            records.append(record)
    return records


def summarize(records: list[dict]) -> dict:
    """Aggregate improvement records for reports."""
    buckets = Counter(row.get("bucket") for row in records)
    fix_types = Counter(row.get("fix_type") for row in records)
    severities = Counter(row.get("severity") for row in records)
    rewards = [_num(row.get("reward", 0.0)) for row in records]
    return {
        "n": len(records),
        "bucket_counts": {k: buckets[k] for k in PRIMARY_ORDER if buckets[k]},
        "fix_type_counts": dict(sorted(fix_types.items())),
        "severity_counts": dict(sorted(severities.items())),
        "mean_reward": sum(rewards) / len(rewards) if rewards else 0.0,
    }


def format_markdown_summary(records: list[dict]) -> str:
    """Render a compact markdown worklist for humans and agents."""
    summary = summarize(records)
    lines = [
        "# Loop-Auditor Self-Improvement Report",
        "",
        f"- Records: {summary['n']}",
        f"- Mean reward: {summary['mean_reward']:.3f}",
        "",
        "## Buckets",
    ]
    if summary["bucket_counts"]:
        for bucket, count in summary["bucket_counts"].items():
            lines.append(f"- {bucket}: {count}")
    else:
        lines.append("- none: 0")
    lines.extend(["", "## Fix Types"])
    if summary["fix_type_counts"]:
        for fix_type, count in summary["fix_type_counts"].items():
            lines.append(f"- {fix_type}: {count}")
    else:
        lines.append("- none: 0")
    lines.extend(["", "## Worklist"])
    if not records:
        lines.append("- No defective runs found.")
    for row in sorted(records, key=_report_sort_key):
        factors = row.get("contributing_factors") or []
        factor_text = f" factors={','.join(factors)}" if factors else ""
        lines.append(
            f"- [{row.get('severity')}] {row.get('run_id')} ({row.get('model')}): "
            f"{row.get('bucket')} -> {row.get('fix_type')}{factor_text}; "
            f"reward={_num(row.get('reward', 0.0)):.3f}"
        )
    return "\n".join(lines) + "\n"


def _primary_bucket(s: dict, artifact_miss: _ArtifactMatch, prompt_confusion: bool) -> "str | None":
    if _bool(s, "gt_fault_present") and (not _bool(s, "gt_step_in_trace") or _num(s.get("fix_concept_total")) == 0):
        return "dataset_issue"
    if not _bool(s, "verdict_parsed"):
        return "parse_failure"
    if not _bool(s, "gt_fault_present") and _bool(s, "pred_fault_present"):
        return "false_positive_clean"
    if _bool(s, "gt_fault_present") and not _bool(s, "pred_fault_present"):
        return "false_negative_buggy"
    if not _bool(s, "citation_passed", default=True):
        return "fabricated_step_ref"
    if not _bool(s, "localization_correct"):
        return "bad_localization"
    if not _bool(s, "failure_type_correct"):
        return "bad_failure_type"
    if _weak_fix(s):
        return "weak_fix"
    if artifact_miss.matched:
        return "artifact_miss"
    if prompt_confusion:
        return "prompt_confusion"
    return None


def _contributing_factors(
    primary: str,
    s: dict,
    artifact_miss: _ArtifactMatch,
    prompt_confusion: bool,
) -> list[str]:
    factors = []
    if artifact_miss.matched and primary != "artifact_miss":
        factors.append("artifact_miss")
    if prompt_confusion and primary != "prompt_confusion":
        factors.append("prompt_confusion")
    if not _bool(s, "citation_passed", default=True) and primary != "fabricated_step_ref":
        factors.append("fabricated_step_ref")
    if (
        _bool(s, "gt_fault_present")
        and _bool(s, "pred_fault_present")
        and not _bool(s, "failure_type_correct")
        and primary != "bad_failure_type"
        and primary in {"bad_localization", "fabricated_step_ref"}
    ):
        factors.append("bad_failure_type")
    return sorted(set(factors))


def _artifact_miss(s: dict) -> _ArtifactMatch:
    if not (_bool(s, "is_rich_case") and _num(s.get("artifact_count")) > 0):
        return _ArtifactMatch(False)
    calls = s.get("artifact_tool_calls")
    if calls is not None:
        return _ArtifactMatch(_num(calls) == 0, "high")
    return _ArtifactMatch(_bool(s, "references_path_token"), "candidate")


def _prompt_confusion(s: dict) -> bool:
    if not _bool(s, "verdict_parsed"):
        return False
    return (
        _bool(s, "proposed_fix_contains_code")
        or _bool(s, "explanation_empty")
        or (
            _bool(s, "type_out_of_enum")
            and not _bool(s, "failure_type_correct")
            and _bool(s, "gt_fault_present")
        )
    )


def _weak_fix(s: dict) -> bool:
    return (
        _bool(s, "localization_correct")
        and _bool(s, "failure_type_correct")
        and _bool(s, "citation_passed", default=True)
        and _num(s.get("fix_concept_total")) > 0
        and _num(s.get("explanation_score")) < EXPL_OK
    )


def _suggested_alias(s: dict) -> dict:
    raw = s.get("failure_type_raw")
    gt = s.get("gt_failure_type")
    if _bool(s, "type_out_of_enum") and isinstance(raw, str) and gt in FAILURE_TYPES:
        key = _normalize_key(raw)
        if key and key != gt:
            return {key: gt}
    return {}


def _fix_type(primary: str, s: dict, factors: list[str], alias: dict) -> str:
    factor_set = set(factors)
    if primary == "dataset_issue":
        return "dataset_repair"
    if primary == "parse_failure":
        return "prompt_change"
    if primary == "false_positive_clean":
        return "prompt_change" if {"fabricated_step_ref", "prompt_confusion"} & factor_set else "new_training_example"
    if primary == "false_negative_buggy":
        return "prompt_change" if "artifact_miss" in factor_set else "new_training_example"
    if primary == "fabricated_step_ref":
        return "prompt_change"
    if primary == "bad_localization":
        return "prompt_change" if "artifact_miss" in factor_set else "new_training_example"
    if primary == "bad_failure_type":
        return "grader_alias_change" if alias else "prompt_change"
    return "prompt_change"


def _confidence(primary: str, artifact_miss: _ArtifactMatch) -> str:
    if primary == "artifact_miss" and artifact_miss.confidence == "candidate":
        return "candidate"
    return "high"


def _severity(reward: float, primary: str) -> str:
    if primary == "dataset_issue":
        return "high"
    if reward <= 0:
        return "high"
    if primary in {"artifact_miss", "prompt_confusion"}:
        return "low"
    return "medium"


def _evidence(primary: str, s: dict, artifact_miss: _ArtifactMatch) -> dict:
    data = {
        "reward": _num(s.get("reward")),
        "gt_fault_present": s.get("gt_fault_present"),
        "pred_fault_present": s.get("pred_fault_present"),
    }
    if primary == "dataset_issue":
        data.update({
            "gt_step_id": s.get("gt_step_id"),
            "gt_step_in_trace": s.get("gt_step_in_trace"),
            "gt_failure_type": s.get("gt_failure_type"),
            "fix_concept_total": s.get("fix_concept_total"),
            "fix_grounded": s.get("fix_grounded"),
        })
    elif primary == "parse_failure":
        data.update({
            "raw_present": s.get("raw_present"),
            "raw_char_len": s.get("raw_char_len"),
            "verdict_parsed": s.get("verdict_parsed"),
        })
    elif primary in {"false_positive_clean", "false_negative_buggy", "bad_localization"}:
        data.update({
            "gt_step_id": s.get("gt_step_id"),
            "gt_failure_type": s.get("gt_failure_type"),
            "localization_correct": s.get("localization_correct"),
            "failure_type_correct": s.get("failure_type_correct"),
        })
    elif primary == "bad_failure_type":
        data.update({
            "failure_type_raw": s.get("failure_type_raw"),
            "gt_failure_type": s.get("gt_failure_type"),
            "type_out_of_enum": s.get("type_out_of_enum"),
        })
    elif primary == "weak_fix":
        data.update({
            "explanation_score": s.get("explanation_score"),
            "fix_concept_matched": s.get("fix_concept_matched"),
            "fix_concept_total": s.get("fix_concept_total"),
        })
    elif primary == "fabricated_step_ref":
        data.update({
            "fabricated_step_refs": s.get("fabricated_step_refs") or [],
            "citation_passed": s.get("citation_passed"),
        })
    elif primary == "prompt_confusion":
        data.update({
            "proposed_fix_contains_code": s.get("proposed_fix_contains_code"),
            "explanation_empty": s.get("explanation_empty"),
            "type_out_of_enum": s.get("type_out_of_enum"),
            "failure_type_raw": s.get("failure_type_raw"),
        })
    if _bool(s, "is_rich_case") and _num(s.get("artifact_count")) > 0:
        data.update({
            "artifact_count": s.get("artifact_count"),
            "artifact_tool_calls": s.get("artifact_tool_calls"),
            "artifact_miss_confidence": artifact_miss.confidence,
        })
    return data


def _notes(buckets: list[str], s: dict, artifact_miss: _ArtifactMatch) -> list[str]:
    notes = []
    for bucket in buckets:
        if bucket == "dataset_issue":
            notes.append(
                f"dataset issue: gt_step_id={s.get('gt_step_id')!r}, "
                f"gt_step_in_trace={s.get('gt_step_in_trace')!r}, "
                f"fix_concept_total={s.get('fix_concept_total')!r}"
            )
        elif bucket == "parse_failure":
            notes.append(f"parse failure: raw_char_len={s.get('raw_char_len')!r}")
        elif bucket == "false_positive_clean":
            notes.append(f"clean trace flagged as {s.get('failure_type_raw')!r}")
        elif bucket == "false_negative_buggy":
            notes.append(
                f"buggy trace marked clean; expected {s.get('gt_failure_type')!r} at {s.get('gt_step_id')!r}"
            )
        elif bucket == "fabricated_step_ref":
            notes.append("fabricated step refs: " + ", ".join(s.get("fabricated_step_refs") or []))
        elif bucket == "bad_localization":
            notes.append(f"bad localization; expected step {s.get('gt_step_id')!r}")
        elif bucket == "bad_failure_type":
            notes.append(
                f"bad failure type: raw={s.get('failure_type_raw')!r}, expected={s.get('gt_failure_type')!r}"
            )
        elif bucket == "weak_fix":
            notes.append(
                f"weak fix: matched {s.get('fix_concept_matched')}/{s.get('fix_concept_total')} concepts"
            )
        elif bucket == "artifact_miss":
            notes.append(
                f"artifact miss: artifact_count={s.get('artifact_count')!r}, "
                f"artifact_tool_calls={s.get('artifact_tool_calls')!r}, confidence={artifact_miss.confidence}"
            )
        elif bucket == "prompt_confusion":
            notes.append("prompt confusion: code/empty explanation/out-of-enum signal fired")
    return notes


def _diagnosis(primary: str, s: dict) -> str:
    if primary == "dataset_issue":
        return f"Ground truth is structurally ungradeable for step {s.get('gt_step_id')!r}."
    if primary == "parse_failure":
        return f"Auditor output did not parse as a valid verdict ({s.get('raw_char_len', 0)} chars)."
    if primary == "false_positive_clean":
        return f"Clean trace was flagged as a fault ({s.get('failure_type_raw')!r})."
    if primary == "false_negative_buggy":
        return f"Buggy trace was marked clean; expected {s.get('gt_failure_type')!r} at {s.get('gt_step_id')!r}."
    if primary == "fabricated_step_ref":
        return "Auditor cited step refs that are absent from the trace."
    if primary == "bad_localization":
        return f"Auditor claimed a fault but missed the planted step {s.get('gt_step_id')!r}."
    if primary == "bad_failure_type":
        return f"Auditor localized the step but used failure type {s.get('failure_type_raw')!r}."
    if primary == "weak_fix":
        return "Auditor found the fault but under-covered the corrective process concepts."
    if primary == "artifact_miss":
        return "Auditor skipped available rich-case artifacts."
    if primary == "prompt_confusion":
        return "Auditor violated a format or rubric instruction despite otherwise parseable output."
    return "Deterministic self-improvement issue."


def _action(primary: str, s: dict, factors: list[str], alias: dict) -> str:
    if primary == "dataset_issue":
        return "Repair the planted label or fix metadata before counting this run."
    if primary == "parse_failure":
        return "Tighten verdict-only JSON output and check max-token truncation before retraining."
    if primary == "false_positive_clean":
        if "fabricated_step_ref" in factors:
            return "Reinforce clean-trace calibration and verbatim step-id citation."
        return "Add hard clean negatives showing healthy recovery and self-correction."
    if primary == "false_negative_buggy":
        if "artifact_miss" in factors:
            return "Require artifact inspection on rich cases before calling a trace clean."
        return "Add positive examples for this fault type."
    if primary == "fabricated_step_ref":
        return "Reinforce copying step_id values verbatim from observed trace/tool output."
    if primary == "bad_localization":
        if "artifact_miss" in factors:
            return "Require reading the relevant patch/log before blaming a step."
        return "Add localization-focused examples keyed to exact planted steps."
    if primary == "bad_failure_type":
        if alias:
            return f"Consider adding alias {alias!r} to the failure-type normalizer."
        return "Clarify the failure-type taxonomy and add contrastive examples."
    if primary == "weak_fix":
        return "Require proposed_fix to name the corrective process action and target."
    if primary == "artifact_miss":
        return "Require list_artifacts/read_artifact usage before final verdicts on rich cases."
    if primary == "prompt_confusion":
        return "Clarify the prompt/rubric for process-only fixes, explanations, and enum values."
    return "Review deterministic evidence before changing prompts or data."


def _missing_sidecar_record(eval_result: dict) -> dict:
    return {
        "run_id": str(eval_result.get("run_id", "")),
        "model": str(eval_result.get("model", "")),
        "reward": _num(eval_result.get("reward", 0.0)),
        "bucket": "dataset_issue",
        "buckets": ["dataset_issue"],
        "contributing_factors": [],
        "fix_type": "dataset_repair",
        "recommended_fix_type": RECOMMENDED_FIX_TYPES["dataset_issue"],
        "confidence": "candidate",
        "severity": "high",
        "suggested_alias": {},
        "evidence": {"missing_sidecar": True},
        "notes": ["missing verdict sidecar; cannot classify deterministic signals"],
        "diagnosis": "Eval result has no verdict sidecar signals.",
        "suggested_action": "Emit verdicts.jsonl keyed by (run_id, model) for this eval.",
    }


def _normalize_key(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _report_sort_key(row: dict) -> tuple:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    bucket_rank = {bucket: index for index, bucket in enumerate(PRIMARY_ORDER)}
    return (
        severity_rank.get(row.get("severity"), 9),
        bucket_rank.get(row.get("bucket"), 99),
        str(row.get("run_id", "")),
        str(row.get("model", "")),
    )


def _bool(row: dict, key: str, default: bool = False) -> bool:
    value = row.get(key, default)
    return bool(value)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
