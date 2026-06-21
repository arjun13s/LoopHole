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


def _normalize_step(s: dict) -> dict:
    """Rich trace.jsonl step -> our ActionSpan schema."""
    tool = s.get("tool_name")
    result = s.get("result") or {}
    return {
        "step_id": s["step_id"],
        "action_type": "final" if tool == "submit" else "tool_call",
        "tool_name": tool,
        "input": s.get("args"),
        "output": result.get("summary"),
        "status": result.get("status"),
        "tokens": int(s.get("tokens", 0) or 0),
    }


def normalize_case(row: dict, repo_root) -> dict:
    """Manifest row + its case/ground-truth files -> a normalized trace dict.

    Flat trace.jsonl steps map to one iteration each (index = position, the step's
    ``summary`` becomes the iteration ``thought``) — faithful to a flat step list
    and natural for the gate's step-by-step reveal.
    """
    repo_root = Path(repo_root)
    steps_raw = [
        json.loads(line)
        for line in (repo_root / row["case_dir"] / "trace.jsonl").read_text().splitlines()
        if line.strip()
    ]
    gt = json.loads((repo_root / row["ground_truth"]).read_text())
    iterations = [
        {"index": i, "thought": s.get("summary", ""), "steps": [_normalize_step(s)]}
        for i, s in enumerate(steps_raw)
    ]
    trace = {
        "run_id": row["case_id"],
        "task": row["case_id"].split("__")[0],
        "model": "rich",
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
