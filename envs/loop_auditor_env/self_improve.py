"""Deterministic self-improvement analysis for Loop-Auditor eval records.

Consumes eval_result JSONL rows plus optional verdict/trace sidecars and emits
failure-analysis records. Pure stdlib: no HUD imports, network calls, or model
judges.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


BUCKETS = (
    "parse_failure",
    "false_positive_clean",
    "false_negative_buggy",
    "bad_localization",
    "bad_failure_type",
    "weak_fix",
    "fabricated_step_ref",
    "artifact_miss",
    "dataset_issue",
)

_REQUIRED_EVAL_KEYS = {
    "run_id",
    "reward",
    "localization_correct",
    "failure_type_correct",
    "explanation_score",
}
_REQUIRED_VERDICT_KEYS = {
    "fault_present",
    "predicted_step_id",
    "failure_type",
    "explanation",
    "proposed_fix",
}
_ARTIFACT_TOOLS = {"list_artifacts", "read_artifact", "search_artifacts"}
_ARTIFACT_HINTS = (
    "repo/",
    "test_outputs/",
    "patches/",
    "command_logs/",
    "transcripts/",
    "artifact",
)
_STEP_REF_RE = re.compile(r"(?<![A-Za-z0-9_])(a(?:\d+|_[A-Za-z0-9_]+_\d+))(?![A-Za-z0-9_])")
_PLAIN_NUMERIC_RE = re.compile(r"^a(\d+)$")


def read_jsonl(path: "str | Path") -> list[dict]:
    """Read a JSONL file into dict rows."""
    rows = []
    for line_no, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{line_no}: JSONL row must be an object")
        rows.append(obj)
    return rows


def write_jsonl(rows: list[dict], path: "str | Path") -> Path:
    """Write dict rows as deterministic JSONL."""
    out = Path(path)
    out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return out


def index_by_run_id(rows: list[dict]) -> dict[str, dict]:
    """Return last-row-wins mapping by run_id."""
    out: dict[str, dict] = {}
    for row in rows:
        run_id = row.get("run_id")
        if isinstance(run_id, str) and run_id:
            out[run_id] = row
    return out


def analyze_eval_records(
    eval_records: list[dict],
    verdicts_by_run_id: "dict[str, Any] | None" = None,
    traces_by_run_id: "dict[str, dict] | None" = None,
    max_reward: float = 0.999,
    weak_fix_threshold: float = 0.5,
) -> list[dict]:
    """Analyze low-score eval rows and return improvement records.

    ``max_reward`` is inclusive: rows with reward <= max_reward are included.
    Rows above the threshold are still included if deterministic sidecar evidence
    produces a bucket, which catches cases like fabricated citations that leave
    partial reward.
    """
    verdicts_by_run_id = verdicts_by_run_id or {}
    traces_by_run_id = traces_by_run_id or {}
    improvements = []
    for record in eval_records:
        run_id = str(record.get("run_id", ""))
        verdict_row = verdicts_by_run_id.get(run_id)
        trace = traces_by_run_id.get(run_id)
        analyzed = analyze_eval_record(
            record,
            verdict_row=verdict_row,
            trace=trace,
            weak_fix_threshold=weak_fix_threshold,
        )
        reward = _number(record.get("reward"), 0.0)
        if reward <= max_reward or analyzed["buckets"]:
            improvements.append(analyzed)
    return improvements


def analyze_eval_record(
    eval_record: dict,
    verdict_row: Any = None,
    trace: "dict | None" = None,
    weak_fix_threshold: float = 0.5,
) -> dict:
    """Classify one eval record into deterministic self-improvement buckets."""
    evidence: list[str] = []
    buckets: list[str] = []

    run_id = str(eval_record.get("run_id", ""))
    model = eval_record.get("model")
    reward = _number(eval_record.get("reward"), 0.0)
    explanation_score = _number(eval_record.get("explanation_score"), 0.0)
    localization_correct = eval_record.get("localization_correct")
    failure_type_correct = eval_record.get("failure_type_correct")

    missing_eval = sorted(_REQUIRED_EVAL_KEYS - set(eval_record))
    if missing_eval:
        _add(buckets, "dataset_issue")
        evidence.append(f"eval record missing required keys: {', '.join(missing_eval)}")

    ground_truth, gt_status = _ground_truth(trace)
    if gt_status == "malformed":
        _add(buckets, "dataset_issue")
        evidence.append("trace planted_failure is malformed")

    verdict, verdict_error = _parse_verdict(verdict_row)
    if verdict_error:
        _add(buckets, "parse_failure")
        evidence.append(verdict_error)

    if trace is None:
        evidence.append("trace sidecar unavailable; clean/buggy direction may be inferred only from verdict/eval fields")

    if trace is not None and gt_status == "unknown":
        _add(buckets, "dataset_issue")
        evidence.append("trace sidecar is missing planted_failure; cannot tell clean from buggy")

    if gt_status == "clean":
        _classify_clean(eval_record, verdict, buckets, evidence)
    elif gt_status == "buggy":
        _classify_buggy(
            eval_record,
            verdict,
            ground_truth,
            buckets,
            evidence,
            explanation_score,
            weak_fix_threshold,
        )
    else:
        _classify_from_eval_only(
            localization_correct,
            failure_type_correct,
            explanation_score,
            weak_fix_threshold,
            buckets,
            evidence,
        )

    if verdict is not None and trace is not None:
        fabricated = fabricated_step_refs(verdict, trace)
        if fabricated:
            _add(buckets, "fabricated_step_ref")
            evidence.append("fabricated step refs: " + ", ".join(fabricated))

    if _artifact_miss(eval_record, verdict_row, verdict, trace, reward):
        _add(buckets, "artifact_miss")
        evidence.append("artifact context was available but no artifact inspection tool was recorded")

    diagnosis = _diagnosis(buckets)
    return {
        "run_id": run_id,
        "model": model,
        "reward": reward,
        "buckets": buckets,
        "diagnosis": diagnosis,
        "evidence": evidence,
        "recommended_fix_type": _recommended_fix_type(buckets),
        "proposed_change": _proposed_change(buckets),
    }


def fabricated_step_refs(verdict: dict, trace: dict) -> list[str]:
    """Return step references in verdict prose that are absent from the trace."""
    text = f"{verdict.get('explanation') or ''} {verdict.get('proposed_fix') or ''}"
    checked = _step_refs(text)
    real = {_canonical_step_id(step_id) for step_id in _trace_step_ids(trace)}
    return [ref for ref in checked if _canonical_step_id(ref) not in real]


def summarize_improvements(records: list[dict]) -> dict:
    """Return deterministic aggregate counts for improvement records."""
    counts = Counter()
    for record in records:
        counts.update(record.get("buckets") or [])
    rewards = [_number(record.get("reward"), 0.0) for record in records]
    return {
        "n": len(records),
        "bucket_counts": {bucket: counts[bucket] for bucket in BUCKETS if counts[bucket]},
        "mean_reward": (sum(rewards) / len(rewards)) if rewards else 0.0,
    }


def format_markdown_summary(records: list[dict]) -> str:
    """Format a compact deterministic markdown report."""
    summary = summarize_improvements(records)
    lines = [
        "# Loop-Auditor Eval Failure Analysis",
        "",
        f"- Records analyzed: {summary['n']}",
        f"- Mean reward: {summary['mean_reward']:.3f}",
        "",
        "## Bucket Counts",
    ]
    if summary["bucket_counts"]:
        for bucket, count in summary["bucket_counts"].items():
            lines.append(f"- {bucket}: {count}")
    else:
        lines.append("- none: 0")
    lines.extend(["", "## Records"])
    if not records:
        lines.append("- No low-score records found.")
    for record in records:
        buckets = ", ".join(record.get("buckets") or ["unclassified"])
        lines.append(
            f"- {record.get('run_id')}: reward={_number(record.get('reward'), 0.0):.3f}; "
            f"buckets={buckets}; fix={record.get('recommended_fix_type')}"
        )
    return "\n".join(lines) + "\n"


def _classify_clean(eval_record, verdict, buckets, evidence) -> None:
    if verdict is not None and verdict.get("fault_present") is True:
        _add(buckets, "false_positive_clean")
        evidence.append(
            f"clean trace predicted fault at {verdict.get('predicted_step_id')!r}"
        )
    elif verdict is None and _number(eval_record.get("reward"), 0.0) < 1.0:
        _add(buckets, "false_positive_clean")
        evidence.append("clean trace received less than full clean reward")


def _classify_buggy(
    eval_record,
    verdict,
    ground_truth,
    buckets,
    evidence,
    explanation_score,
    weak_fix_threshold,
) -> None:
    gt_step = ground_truth.get("step_id")
    gt_type = ground_truth.get("failure_type")
    if verdict is not None and verdict.get("fault_present") is False:
        _add(buckets, "false_negative_buggy")
        evidence.append(f"buggy trace marked clean; ground_truth step={gt_step!r}, type={gt_type!r}")
        return

    predicted_step = verdict.get("predicted_step_id") if verdict is not None else None
    predicted_type = verdict.get("failure_type") if verdict is not None else None
    if eval_record.get("localization_correct") is False:
        _add(buckets, "bad_localization")
        if verdict is not None:
            evidence.append(f"predicted step {predicted_step!r}; expected {gt_step!r}")
        else:
            evidence.append(f"localization_correct=false; expected {gt_step!r}")
    if eval_record.get("failure_type_correct") is False:
        _add(buckets, "bad_failure_type")
        if verdict is not None:
            evidence.append(f"predicted type {predicted_type!r}; expected {gt_type!r}")
        else:
            evidence.append(f"failure_type_correct=false; expected {gt_type!r}")

    if (
        eval_record.get("localization_correct") is True
        and eval_record.get("failure_type_correct") is True
        and explanation_score < weak_fix_threshold
    ):
        _add(buckets, "weak_fix")
        evidence.append(
            f"localization/type correct but explanation_score={explanation_score:.3f} "
            f"< {weak_fix_threshold:.3f}"
        )


def _classify_from_eval_only(
    localization_correct,
    failure_type_correct,
    explanation_score,
    weak_fix_threshold,
    buckets,
    evidence,
) -> None:
    if localization_correct is False:
        _add(buckets, "bad_localization")
        evidence.append("localization_correct=false without trace/verdict sidecar")
    if failure_type_correct is False:
        _add(buckets, "bad_failure_type")
        evidence.append("failure_type_correct=false without trace/verdict sidecar")
    if localization_correct is True and failure_type_correct is True and explanation_score < weak_fix_threshold:
        _add(buckets, "weak_fix")
        evidence.append(
            f"localization/type correct but explanation_score={explanation_score:.3f} "
            f"< {weak_fix_threshold:.3f}"
        )


def _parse_verdict(row: Any) -> tuple["dict | None", "str | None"]:
    if row is None:
        return None, None
    if isinstance(row, dict):
        signals = row.get("signals")
        if isinstance(signals, dict) and signals.get("verdict_parsed") is False:
            if signals.get("raw_present") is False:
                return None, "parse failure: auditor produced no verdict text"
            return None, "parse failure: raw auditor verdict did not parse"
    raw = _verdict_payload(row)
    if raw is None:
        return None, "parse failure: verdict sidecar has no verdict/raw output field"
    if isinstance(raw, dict):
        verdict = dict(raw)
    elif isinstance(raw, str):
        try:
            verdict = _extract_json_object(raw)
        except ValueError as exc:
            return None, f"parse failure: {exc}"
    else:
        return None, f"parse failure: unsupported verdict payload type {type(raw).__name__}"

    missing = sorted(_REQUIRED_VERDICT_KEYS - set(verdict))
    if missing:
        return verdict, "parse failure: verdict missing required keys: " + ", ".join(missing)
    if verdict.get("fault_present") is False:
        wrong_clean = [
            key for key in ("predicted_step_id", "failure_type", "proposed_fix")
            if verdict.get(key) is not None
        ]
        if wrong_clean:
            return verdict, "parse failure: clean verdict must null " + ", ".join(wrong_clean)
    if verdict.get("fault_present") is True and (
        verdict.get("predicted_step_id") is None
        or verdict.get("failure_type") is None
        or verdict.get("proposed_fix") is None
    ):
        return verdict, "parse failure: fault verdict missing step, type, or fix"
    return verdict, None


def _verdict_payload(row: Any) -> Any:
    if isinstance(row, (str, dict)):
        if isinstance(row, str):
            return row
        for key in ("verdict", "raw_verdict", "raw_output", "output", "final", "content"):
            if key in row:
                return row[key]
        if _REQUIRED_VERDICT_KEYS & set(row):
            return row
    return None


def _extract_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise ValueError("no JSON object found in verdict text")


def _ground_truth(trace: "dict | None") -> tuple["dict | None", str]:
    if trace is None:
        return None, "unavailable"
    if "planted_failure" not in trace:
        return None, "unknown"
    gt = trace.get("planted_failure")
    if gt is None:
        return None, "clean"
    if isinstance(gt, dict) and isinstance(gt.get("step_id"), str) and isinstance(gt.get("failure_type"), str):
        return gt, "buggy"
    return None, "malformed"


def _artifact_miss(eval_record, verdict_row, verdict, trace, reward: float) -> bool:
    if reward >= 1.0 or not _trace_has_artifacts(trace):
        return False
    usage_known, used_artifact_tool = _artifact_usage(verdict_row)
    if usage_known:
        return not used_artifact_tool
    text = ""
    if verdict is not None:
        text = f"{verdict.get('explanation') or ''} {verdict.get('proposed_fix') or ''}".lower()
    if text and not any(hint in text for hint in _ARTIFACT_HINTS):
        return True
    return bool(eval_record.get("artifact_tools_used") is False)


def _artifact_usage(row: Any) -> tuple[bool, bool]:
    if not isinstance(row, dict):
        return False, False
    signals = row.get("signals")
    if isinstance(signals, dict):
        artifact_calls = signals.get("artifact_tool_calls")
        inspection_calls = signals.get("inspection_tool_calls")
        if artifact_calls is not None or inspection_calls is not None:
            return True, int(artifact_calls or 0) > 0
    for key in ("tool_calls", "tools", "used_tools", "actions"):
        if key not in row:
            continue
        names = {_tool_name(item) for item in _as_list(row[key])}
        names.discard(None)
        return True, bool(names & _ARTIFACT_TOOLS)
    return False, False


def _tool_name(item: Any) -> "str | None":
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("name", "tool", "tool_name"):
            value = item.get(key)
            if isinstance(value, str):
                return value
    return None


def _trace_has_artifacts(trace: "dict | None") -> bool:
    if not isinstance(trace, dict):
        return False
    metadata = trace.get("metadata")
    if isinstance(metadata, dict) and any(k in metadata for k in ("case_dir", "artifact_root")):
        return True
    if any(k in trace for k in ("case_dir", "artifact_root", "artifacts")):
        return True
    run_id = trace.get("run_id")
    return isinstance(run_id, str) and "__" in run_id


def _trace_step_ids(trace: dict) -> set[str]:
    ids: set[str] = set()
    for iteration in trace.get("iterations", []) or []:
        for step in iteration.get("steps", []) or []:
            step_id = step.get("step_id")
            if isinstance(step_id, str):
                ids.add(step_id)
    return ids


def _step_refs(text: str) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for match in _STEP_REF_RE.finditer(text or ""):
        ref = match.group(1)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _canonical_step_id(ref: str) -> str:
    match = _PLAIN_NUMERIC_RE.match(ref)
    return f"a{int(match.group(1))}" if match else ref


def _diagnosis(buckets: list[str]) -> str:
    if not buckets:
        return "No deterministic failure bucket assigned."
    if "parse_failure" in buckets:
        return "Auditor output was malformed before reward analysis could trust its fields."
    if "dataset_issue" in buckets:
        return "Eval or sidecar data is missing deterministic context needed for a precise diagnosis."
    if "false_positive_clean" in buckets:
        return "Auditor over-called a clean trace as faulty."
    if "false_negative_buggy" in buckets:
        return "Auditor missed a planted process fault."
    if "fabricated_step_ref" in buckets:
        return "Auditor cited a step reference that is absent from the trace."
    if "bad_localization" in buckets and "bad_failure_type" in buckets:
        return "Auditor found the wrong fault location and failure category."
    if "bad_localization" in buckets:
        return "Auditor identified a fault but localized it to the wrong step."
    if "bad_failure_type" in buckets:
        return "Auditor localized the fault but used the wrong failure category."
    if "weak_fix" in buckets:
        return "Auditor found the fault but proposed a weak deterministic fix."
    if "artifact_miss" in buckets:
        return "Auditor likely skipped available repo/test/patch artifacts."
    return "Deterministic low-score eval issue."


def _recommended_fix_type(buckets: list[str]) -> str:
    if not buckets:
        return "none"
    if "parse_failure" in buckets:
        return "verdict_format"
    if "dataset_issue" in buckets:
        return "dataset_or_sidecar"
    if "false_positive_clean" in buckets:
        return "clean_trace_calibration"
    if "false_negative_buggy" in buckets:
        return "fault_detection"
    if "fabricated_step_ref" in buckets:
        return "citation_grounding"
    if "artifact_miss" in buckets:
        return "artifact_inspection"
    if "bad_localization" in buckets:
        return "localization"
    if "bad_failure_type" in buckets:
        return "failure_type_taxonomy"
    if "weak_fix" in buckets:
        return "fix_quality"
    return "analysis"


def _proposed_change(buckets: list[str]) -> str:
    fix_type = _recommended_fix_type(buckets)
    changes = {
        "none": "No change recommended from deterministic analysis.",
        "verdict_format": "Add format-only retry/filtering data for JSON verdict compliance; keep reward semantics unchanged.",
        "dataset_or_sidecar": "Emit trace/verdict sidecars with run_id so analysis can separate clean, buggy, and parse failures.",
        "clean_trace_calibration": "Add or upweight clean traces where suspicious but healthy behavior should remain fault_present=false.",
        "fault_detection": "Add examples that contrast planted process faults with healthy recovery after errors.",
        "citation_grounding": "Constrain cited step refs to copied trace step_id values and add tests for absent refs.",
        "artifact_inspection": "Require artifact-tool use on rich traces before final verdicts in eval/prompt review.",
        "localization": "Add localization-focused examples keyed to the exact planted step_id.",
        "failure_type_taxonomy": "Add deterministic taxonomy examples for the confused failure_type.",
        "fix_quality": "Add fix-comparison examples that turn correct localization into concrete process fixes.",
        "analysis": "Review low-score deterministic evidence before changing prompts or data.",
    }
    return changes[fix_type]


def _add(buckets: list[str], bucket: str) -> None:
    if bucket not in buckets:
        buckets.append(bucket)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]
