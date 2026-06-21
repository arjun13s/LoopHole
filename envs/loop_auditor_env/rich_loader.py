"""Load Person 1's rich generated taskset into the env's normalized trace schema.

The rich set (generated_traces/rich_taskset/{train,heldout}.jsonl) is a manifest:
each row points at a case dir (with a flat trace.jsonl + a real repo/ + test
outputs) and a separate ground-truth file. This normalizes a manifest into the
trace dicts the env already understands (run_id / iterations / planted_failure),
so serialize.py, tools.py, scenarios.py and the reward path work unchanged.

The rich ground truth carries a STRUCTURED fix (action/step_id/target/tool_name);
we forward it under planted_failure["fix"] so the deterministic fix grader can
score against it directly instead of re-deriving from a base trace.
"""

from __future__ import annotations

import json
from pathlib import Path


# Only neutral, factual action keys reach the auditor. content_summary and any
# other narration are dropped: they editorialize the code/fault and would leak the
# answer. The auditor judges from path/command/files + test results + tokens.
_NEUTRAL_INPUT_KEYS = ("path", "command", "files")


def _neutral_input(args):
    if not isinstance(args, dict):
        return args
    kept = {k: v for k, v in args.items() if k in _NEUTRAL_INPUT_KEYS}
    return kept or {k: args[k] for k in list(args)[:1]}


def _neutral_output(tool: str, args, result: dict) -> str:
    """Factual outcome only, never the narrator's framing. Real run outputs
    (test pass/fail counts) are kept; file ops report the action + path."""
    if tool in ("run_tests", "run_command"):
        return result.get("summary") or result.get("status") or ""
    if isinstance(args, dict) and args.get("path"):
        verb = {"read_file": "read", "write_file": "wrote"}.get(tool, tool or "acted on")
        return f"{verb} {args['path']}"
    if tool == "submit":
        files = args.get("files") if isinstance(args, dict) else None
        return f"submitted {files}" if files else "submitted"
    return result.get("status") or ""


def _normalize_step(s: dict) -> dict:
    """Rich trace.jsonl step -> our ActionSpan schema, neutralized (no narration
    that could leak the planted fault)."""
    tool = s.get("tool_name")
    args = s.get("args")
    result = s.get("result") or {}
    # No `tokens` field: a per-step token count is itself a giveaway (the faulty
    # resource_misuse read is conspicuously large) and tokens are out of the reward
    # (LAMBDA_TOKENS=0). The auditor judges resource use from the path + the actual
    # file via read_artifact, not a handed-over number.
    return {
        "step_id": s["step_id"],
        "action_type": "final" if tool == "submit" else "tool_call",
        "tool_name": tool,
        "input": _neutral_input(args),
        "output": _neutral_output(tool, args, result),
        "status": result.get("status"),
    }


def normalize_case(row: dict, repo_root) -> dict:
    """Manifest row + its case/ground-truth files -> a normalized trace dict.

    Flat trace.jsonl steps map to one iteration each (index = position), with
    narrator summaries removed so the auditor reasons from neutral evidence.
    """
    repo_root = Path(repo_root)
    steps_raw = [
        json.loads(line)
        for line in (repo_root / row["case_dir"] / "trace.jsonl").read_text().splitlines()
        if line.strip()
    ]
    gt = json.loads((repo_root / row["ground_truth"]).read_text())
    # Drop the narrator per-step `summary` entirely: it editorializes the fault
    # ("Read an oversized repository dump...") and would hand the auditor the
    # answer. The auditor reasons from the neutral actions instead.
    iterations = [
        {"index": i, "thought": "", "steps": [_normalize_step(s)]}
        for i, s in enumerate(steps_raw)
    ]
    trace = {
        "run_id": row["case_id"],
        "task": row["case_id"].split("__")[0],
        "model": "rich",
        "metadata": {"case_dir": row.get("case_dir")},
        "iterations": iterations,
        "planted_failure": None,
    }
    if gt.get("fault_present"):
        ftype, sid = gt.get("failure_type"), gt.get("fault_step_id")
        trace["planted_failure"] = {
            "step_id": sid,
            "failure_type": ftype,
            "description": f"{ftype} at {sid}",
            "fix": gt.get("fix"),  # structured fix -> deterministic fix-by-comparison
        }
    return trace


def load_rich_taskset(manifest_path, repo_root) -> "list[dict]":
    """Load + normalize every row of a rich manifest (train.jsonl / heldout.jsonl)."""
    rows = [
        json.loads(line)
        for line in Path(manifest_path).read_text().splitlines()
        if line.strip()
    ]
    return [normalize_case(r, repo_root) for r in rows]
