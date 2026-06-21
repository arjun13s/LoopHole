"""Adapt Person 1's live Qwen worker traces into a base-eval dataset.

`generated_traces/live_qwen/` holds REAL Qwen2.5-Coder-7B agent loops (clean
`clean_cases/` + deterministically fault-injected `labeled_cases/`) with sidecar
ground truth. Each case is a FLAT `trace.jsonl` (step records: step_id/tool_name/
args/result/tokens) — Person 1's shape, not our frozen schema.

This module bridges that shape into the normalized trace dicts the auditor +
deterministic grader already understand, by reusing Person 2's PURE
`rich_loader.normalize_case` (the same adapter the HUD env uses). The result feeds
`base_eval.run_base_eval` unchanged, so the base baseline is scored byte-identically
to the trained side.

Token accounting: `rich_loader` intentionally STRIPS per-step tokens from the
auditor's view (a per-step count leaks the conspicuous resource_misuse read). We
still want the honest audit COST for the dashboard, so we recompute the true total
from the raw flat trace and stash it under `metadata.trace_tokens`, which
`scoring.count_trace_tokens` reads as a fallback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent
LIVE_ROOT = REPO_ROOT / "generated_traces" / "live_qwen"

# Fault subdirectories under labeled_cases/<case>/ mirror the verdict.json enum.
_FAULT_TYPES = ("resource_misuse", "routing", "tool_misuse", "wrong_file_edit")


def build_manifest(live_root=LIVE_ROOT, repo_root=REPO_ROOT) -> list[dict]:
    """Scan live_qwen/ into rich-style manifest rows (paths relative to repo root).

    Only cases that have BOTH a trace.jsonl and a ground-truth sidecar are
    included; `failed_cases/` (worker never solved the task, no ground truth) are
    skipped by construction.
    """
    live_root, repo_root = Path(live_root), Path(repo_root)
    rel = live_root.relative_to(repo_root).as_posix()
    rows: list[dict] = []

    clean_dir = live_root / "clean_cases"
    if clean_dir.is_dir():
        for case in sorted(p for p in clean_dir.iterdir() if p.is_dir()):
            gt = live_root / "clean_ground_truth" / f"{case.name}.json"
            if (case / "trace.jsonl").is_file() and gt.is_file():
                rows.append({
                    "case_id": case.name,
                    "case_dir": f"{rel}/clean_cases/{case.name}",
                    "ground_truth": f"{rel}/clean_ground_truth/{case.name}.json",
                    "failure_type": "clean",
                })

    labeled_dir = live_root / "labeled_cases"
    if labeled_dir.is_dir():
        for base in sorted(p for p in labeled_dir.iterdir() if p.is_dir()):
            for fault in _FAULT_TYPES:
                case = base / fault
                gt = live_root / "labeled_ground_truth" / f"{base.name}__{fault}.json"
                if (case / "trace.jsonl").is_file() and gt.is_file():
                    rows.append({
                        "case_id": f"{base.name}__{fault}",
                        "case_dir": f"{rel}/labeled_cases/{base.name}/{fault}",
                        "ground_truth": f"{rel}/labeled_ground_truth/{base.name}__{fault}.json",
                        "failure_type": fault,
                    })
    return rows


def _raw_trace_tokens(case_dir: Path) -> int:
    """True total tokens from the raw flat trace.jsonl (auditor never sees this)."""
    total = 0
    for line in (case_dir / "trace.jsonl").read_text().splitlines():
        if line.strip():
            total += int(json.loads(line).get("tokens", 0) or 0)
    return total


def load_live_traces(live_root=LIVE_ROOT, repo_root=REPO_ROOT) -> list[dict]:
    """Manifest -> normalized Shape-A traces with honest `metadata.trace_tokens`."""
    from loop_auditor_env import rich_loader

    live_root, repo_root = Path(live_root), Path(repo_root)
    traces: list[dict] = []
    for row in build_manifest(live_root, repo_root):
        trace = rich_loader.normalize_case(row, repo_root)
        meta = dict(trace.get("metadata") or {})
        meta["trace_tokens"] = _raw_trace_tokens(repo_root / row["case_dir"])
        trace["metadata"] = meta
        traces.append(trace)
    return traces


def main(argv=None) -> int:
    from . import base_eval

    ap = argparse.ArgumentParser(prog="live_eval")
    ap.add_argument("--live-root", default=str(LIVE_ROOT), help="generated_traces/live_qwen dir")
    ap.add_argument("--model-tag", default="base")
    ap.add_argument("--base-url", default=None, help="Modal/OpenAI base url (…/v1); omit for a dry run")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--out", default="results")
    args = ap.parse_args(argv)

    traces = load_live_traces(Path(args.live_root))
    if args.base_url:
        from .backends import ModalBackend
        backend = ModalBackend(base_url=args.base_url, model=args.model)
    else:  # dry run: prove the plumbing without a GPU (every case -> "no fault")
        from .backends import DummyBackend
        backend = DummyBackend([
            {"fault_present": False, "predicted_step_id": None, "failure_type": None,
             "explanation": "dry-run stub", "proposed_fix": None}
            for _ in traces
        ])

    agg = base_eval.run_base_eval(traces, backend, model_tag=args.model_tag, out_dir=args.out)
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
