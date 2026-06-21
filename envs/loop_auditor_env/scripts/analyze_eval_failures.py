"""Analyze Loop-Auditor eval_results.jsonl into deterministic failure reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _import_self_improve():
    try:
        from loop_auditor_env import self_improve

        return self_improve
    except ModuleNotFoundError:
        env_root = Path(__file__).resolve().parent.parent
        if str(env_root) not in sys.path:
            sys.path.insert(0, str(env_root))
        import self_improve

        return self_improve


def main() -> None:
    si = _import_self_improve()
    parser = argparse.ArgumentParser()
    parser.add_argument("eval_results", help="Path to eval_results.jsonl")
    parser.add_argument("--verdicts", default=None, help="Optional verdict/raw-output JSONL sidecar")
    parser.add_argument("--traces", default=None, help="Optional trace JSONL sidecar keyed by run_id")
    parser.add_argument("--out-jsonl", required=True, help="Output improvement-record JSONL path")
    parser.add_argument("--out-md", required=True, help="Output markdown summary path")
    parser.add_argument("--max-reward", type=float, default=0.999)
    parser.add_argument("--weak-fix-threshold", type=float, default=0.5)
    args = parser.parse_args()

    eval_records = si.read_jsonl(args.eval_results)
    verdicts = si.index_by_run_id(si.read_jsonl(args.verdicts)) if args.verdicts else {}
    traces = si.index_by_run_id(si.read_jsonl(args.traces)) if args.traces else {}

    improvements = si.analyze_eval_records(
        eval_records,
        verdicts_by_run_id=verdicts,
        traces_by_run_id=traces,
        max_reward=args.max_reward,
        weak_fix_threshold=args.weak_fix_threshold,
    )
    si.write_jsonl(improvements, args.out_jsonl)
    Path(args.out_md).write_text(si.format_markdown_summary(improvements))
    summary = si.summarize_improvements(improvements)
    print(
        f"wrote {summary['n']} records -> {args.out_jsonl}; "
        f"summary -> {args.out_md}"
    )


if __name__ == "__main__":
    main()
