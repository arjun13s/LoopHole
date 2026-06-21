"""Deterministic self-improvement signal producer (the analyzer's INPUT).

OWNER: Claude. Pure + deterministic: every signal is a function of
``(eval_record, raw_verdict, trace_view, ground_truth)`` computed with the SAME
helpers the reward path uses (``verdict``, ``citation_gate``, ``fix_grader``,
``artifacts``) — no LLM, no network, no GRPO-reward change. Emits one
``schemas/verdict_sidecar.json`` record per run; ``eval_harness`` writes them to
``verdicts.jsonl`` next to ``eval_results.jsonl``.

The (Codex-owned) ``self_improve`` analyzer consumes ``signals`` and classifies
each defective run into a taxonomy bucket. See
``docs/superpowers/specs/2026-06-21-loop-auditor-self-improvement-taxonomy.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:  # package (pytest) | flat (hud `env:env`)
    from . import artifacts, citation_gate, config, fix_grader
    from . import verdict as verdict_mod
except ImportError:  # flat mode
    import artifacts
    import citation_gate
    import config
    import fix_grader
    import verdict as verdict_mod


ARTIFACT_TOOLS = ("list_artifacts", "read_artifact", "search_artifacts")
INSPECTION_TOOLS = (
    "get_trace_summary", "get_iteration", "get_step",
    "search_steps", "get_errors", "get_step_io",
)

# Conservative "this is code, not a process action" detector. Requires CODE-SHAPED
# context — a fenced block, a diff hunk, or a keyword followed by an identifier —
# so prose like "a class of error" or "run the tests" is NOT flagged as code.
_CODE_RE = re.compile(
    r"```"                               # fenced code block
    r"|(?m:^\s*(?:@@|\+\+\+|---)\s)"     # diff hunk / file markers
    r"|\bdef\s+\w+\s*\("                 # python function def
    r"|\bclass\s+\w+\s*[:(]"             # python class def
    r"|\bimport\s+\w"                    # import statement
    r"|=>"                               # arrow (lambda / js)
)
# A file path / filename reference: a known extension, OR a recognizable source
# directory prefix. Avoids matching bare "and/or" / "before/after" word pairs.
_PATH_RE = re.compile(
    r"[\w.\-]+\.(?:py|txt|md|json|jsonl|log|diff|patch|cfg|ini|ya?ml|toml|js|ts|csv)\b"
    r"|\b(?:src|tests?|repo|lib|app|pkg|cmd|internal|server|routes?)/[\w./\-]+"
)

_CLEAN_CORE = {
    "fault_present": False, "predicted_step_id": None,
    "failure_type": None, "explanation": "", "proposed_fix": None,
}


def _raw_text(raw_verdict) -> str:
    if isinstance(raw_verdict, str):
        return raw_verdict
    if isinstance(raw_verdict, dict):
        return json.dumps(raw_verdict)
    return "" if raw_verdict is None else str(raw_verdict)


def _looks_like_code(text) -> bool:
    return bool(text) and bool(_CODE_RE.search(text))


def _references_path(text) -> bool:
    return bool(text) and bool(_PATH_RE.search(text))


_PLAIN_NUMERIC_RE = re.compile(r"^a(\d+)$")


def _canon_step(ref):
    """Collapse zero-padding on a plain ``aNNN`` id (mirrors citation_gate) so
    ``a7`` == ``a07`` when checking the planted step against the trace."""
    if not isinstance(ref, str):
        return ref
    m = _PLAIN_NUMERIC_RE.match(ref)
    return f"a{int(m.group(1))}" if m else ref


def _safe_load_base_trace(run_id: str, base_dir) -> "dict | None":
    """fix_grader.load_base_trace, but a corrupt/unreadable base file degrades to
    None instead of crashing the eval (guarded only here; reward path untouched)."""
    try:
        return fix_grader.load_base_trace(run_id, base_dir)
    except (OSError, ValueError):  # JSONDecodeError is a ValueError subclass
        return None


def _structured_fix_groups(structured: dict) -> list:
    groups: list = []
    target = structured.get("target")
    if isinstance(target, str) and target:
        groups.append([target, Path(target).name])
    tool_or_action = [
        v for v in (structured.get("tool_name"), structured.get("action"))
        if isinstance(v, str) and v
    ]
    if tool_or_action:
        groups.append(tool_or_action)
    return groups


def _fix_concept_coverage(core: dict, ground_truth, trace_view: dict, base_dir) -> "tuple[int, int]":
    """Return (matched, total) corrective concept groups covered by the fix prose.

    Mirrors fix_grader.grade_fix's group accounting (structured fix vs the
    fix-by-comparison concept groups) so weak_fix evidence reads as "matched N/M".
    """
    if not isinstance(ground_truth, dict):
        return 0, 0
    structured = ground_truth.get("fix")
    try:
        if isinstance(structured, dict):
            groups = _structured_fix_groups(structured)
        else:
            base_trace = _safe_load_base_trace(trace_view.get("run_id", ""), base_dir)
            groups = fix_grader.expected_correction(trace_view, ground_truth, base_trace)["concept_groups"]
    except (KeyError, TypeError):
        # Malformed ground truth (e.g. missing failure_type/step_id) -> ungradeable.
        # 0 groups => the analyzer routes this to dataset_issue, never a crash.
        return 0, 0
    if not groups:
        return 0, 0
    text = f"{core.get('proposed_fix') or ''} {core.get('explanation') or ''}".lower()
    matched = sum(1 for g in groups if any(t.lower() in text for t in g if t))
    return matched, len(groups)


def _tool_count(tool_calls, names) -> "int | None":
    if not isinstance(tool_calls, dict):
        return None
    return sum(int(tool_calls.get(n, 0) or 0) for n in names)


def extract_signals(eval_record: dict, raw_verdict, trace_view: dict, ground_truth,
                    *, tool_calls=None, base_traces_dir=None) -> dict:
    """Compute the deterministic detection signals for one run."""
    base_dir = base_traces_dir if base_traces_dir is not None else config.BASE_TRACES_DIR
    trace_view = trace_view if isinstance(trace_view, dict) else {}

    raw = _raw_text(raw_verdict)

    # Parse (best-effort) to recover the ORIGINAL failure_type, then validate.
    try:
        parsed = verdict_mod.parse_verdict(raw_verdict)
    except (ValueError, TypeError):
        parsed = None
    raw_ft = parsed.get("failure_type") if isinstance(parsed, dict) else None
    failure_type_raw = raw_ft.strip() if isinstance(raw_ft, str) and raw_ft.strip() else None

    try:
        v = verdict_mod.validate_verdict(parsed) if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        v = None
    verdict_parsed = v is not None
    core = {k: v[k] for k in _CLEAN_CORE} if verdict_parsed else dict(_CLEAN_CORE)

    norm_ft = core["failure_type"]
    type_out_of_enum = bool(norm_ft) and norm_ft not in config.FAILURE_TYPES

    gt = ground_truth if isinstance(ground_truth, dict) else None
    gt_fault_present = gt is not None

    citation = citation_gate.check(core, trace_view)

    if gt is None:
        fix_grounded = True
        gt_step_in_trace = True
    else:
        has_struct = isinstance(gt.get("fix"), dict) and bool(gt.get("fix"))
        base_present = _safe_load_base_trace(trace_view.get("run_id", ""), base_dir) is not None
        fix_grounded = has_struct or base_present
        real = {_canon_step(x) for x in citation_gate.trace_step_ids(trace_view)}
        gt_step_in_trace = _canon_step(gt.get("step_id")) in real

    matched, total = _fix_concept_coverage(core, gt, trace_view, base_dir)

    try:
        is_rich_case = artifacts.resolve_case_dir(trace_view) is not None
        artifact_count = len(artifacts.list_artifacts(trace_view)) if is_rich_case else 0
    except (OSError, ValueError):
        is_rich_case, artifact_count = False, 0

    prose = f"{core.get('explanation') or ''} {core.get('proposed_fix') or ''}"

    return {
        "verdict_parsed": verdict_parsed,
        "raw_present": bool(raw.strip()),
        "raw_char_len": len(raw),

        "failure_type_raw": failure_type_raw,
        "type_out_of_enum": type_out_of_enum,

        "pred_fault_present": bool(core.get("fault_present")),
        "gt_fault_present": gt_fault_present,
        "gt_step_id": gt.get("step_id") if gt else None,
        "gt_failure_type": gt.get("failure_type") if gt else None,

        "localization_correct": bool(eval_record.get("localization_correct")),
        "failure_type_correct": bool(eval_record.get("failure_type_correct")),
        "explanation_score": float(eval_record.get("explanation_score", 0.0)),
        "reward": float(eval_record.get("reward", 0.0)),

        "citation_passed": bool(citation["passed"]),
        "fabricated_step_refs": list(citation["fabricated"]),

        "fix_grounded": bool(fix_grounded),
        "fix_concept_total": int(total),
        "fix_concept_matched": int(matched),

        "gt_step_in_trace": bool(gt_step_in_trace),

        "is_rich_case": bool(is_rich_case),
        "artifact_count": int(artifact_count),
        "artifact_tool_calls": _tool_count(tool_calls, ARTIFACT_TOOLS),
        "inspection_tool_calls": _tool_count(tool_calls, INSPECTION_TOOLS),

        "proposed_fix_contains_code": _looks_like_code(core.get("proposed_fix")),
        "explanation_empty": bool(core.get("fault_present")) and not (core.get("explanation") or "").strip(),
        "references_path_token": _references_path(prose),
    }


def build_sidecar_record(eval_record: dict, raw_verdict, trace_view: dict, ground_truth,
                         *, tool_calls=None, base_traces_dir=None) -> dict:
    """Build one ``schemas/verdict_sidecar.json`` record for a run.

    Envelope = ``(run_id, model)`` from ``eval_record``. Core = the validated
    verdict (or the dashboard-valid clean placeholder when the verdict did not
    parse — ``signals.verdict_parsed`` carries the truth). ``signals`` = the
    deterministic detection block.
    """
    signals = extract_signals(
        eval_record, raw_verdict, trace_view, ground_truth,
        tool_calls=tool_calls, base_traces_dir=base_traces_dir,
    )
    try:
        parsed = verdict_mod.validate_verdict(verdict_mod.parse_verdict(raw_verdict))
        core = {k: parsed[k] for k in _CLEAN_CORE}
    except (ValueError, TypeError):
        core = dict(_CLEAN_CORE)
    # Keep the sidecar verdict CORE valid against the FROZEN schemas/verdict.json so
    # the dashboard (dashboard/loader.py:load_verdicts) never rejects the whole file:
    # validate_verdict is lenient and lets an out-of-enum failure_type through, but
    # verdict.json constrains the enum. The out-of-enum value is preserved for the
    # analyzer in signals.failure_type_raw + signals.type_out_of_enum.
    if core["failure_type"] is not None and core["failure_type"] not in config.FAILURE_TYPES:
        core["failure_type"] = None
    return {
        "run_id": eval_record["run_id"],
        "model": eval_record["model"],
        **core,
        "signals": signals,
    }
