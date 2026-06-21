"""Command-line entry point for Loop-Auditor eval + self-improvement."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

from . import analyzer
from . import supervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-auditor",
        description="Run the HUD eval agent and analyze failures into deterministic improvement records.",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="Analyze existing eval JSONL artifacts")
    _add_analyze_args(analyze, require_inputs=True)

    run = subparsers.add_parser("run", help="Run the HUD eval agent, then analyze its artifacts")
    _add_run_args(run)
    _add_analyze_args(run, require_inputs=False)

    supervise = subparsers.add_parser(
        "supervise",
        help="Run baseline/eval-assisted stop-and-resume coding-agent experiments",
    )
    supervise.add_argument("--task", required=True, help="Path to supervisor task JSON")
    supervise.add_argument("--agent", required=True, help="Coding-agent shell command")
    supervise.add_argument("--eval-agent", default=None, help="Optional eval-agent shell command")
    supervise.add_argument("--mode", default="both", choices=("baseline", "assisted", "both"))
    supervise.add_argument("--out-dir", default="supervision_runs")
    supervise.add_argument("--max-attempts", type=int, default=supervisor.DEFAULT_MAX_ATTEMPTS)
    supervise.add_argument("--timeout", type=int, default=120)

    # No-subcommand path is the one-line happy path:
    #   loop-auditor --split heldout --report report.md
    _add_run_args(parser)
    _add_analyze_args(parser, require_inputs=False)
    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--split", default=None, help="defaults to LOOP_AUDITOR_DATASET")
    parser.add_argument("--model-tag", default="base", choices=("base", "trained"))
    parser.add_argument(
        "--mock-judge",
        type=float,
        help="Use a fixed explanation score in [0,1] instead of the live/stub judge.",
    )


def _add_analyze_args(parser: argparse.ArgumentParser, *, require_inputs: bool) -> None:
    parser.add_argument("--results", required=require_inputs, help="Path to eval_results.jsonl")
    parser.add_argument("--verdicts", required=require_inputs, help="Path to verdicts.jsonl sidecar")
    parser.add_argument(
        "--out",
        default="improvement_records.jsonl",
        help="Output JSONL path (default: improvement_records.jsonl)",
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const="-",
        default=None,
        help="Write a markdown report to PATH, or stdout when passed without a path",
    )


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None and (args.results or args.verdicts):
        if not (args.results and args.verdicts):
            build_parser().error("--results and --verdicts must be passed together")
        command = "analyze"
    else:
        command = args.command or "run"
    if command == "supervise":
        return _run_supervisor(args)
    if command == "run":
        _run_hud_eval(args)

    results_path, verdicts_path = _artifact_paths(args)
    eval_results = analyzer.read_jsonl(results_path)
    sidecars = analyzer.sidecar_index(analyzer.read_jsonl(verdicts_path))
    records = analyzer.analyze(eval_results, sidecars)
    analyzer.write_jsonl(records, args.out)

    if args.report:
        report = analyzer.format_markdown_summary(records)
        if args.report == "-":
            sys.stdout.write(report)
        else:
            Path(args.report).write_text(report)
    else:
        summary = analyzer.summarize(records)
        print(f"wrote {summary['n']} improvement records -> {args.out}")
    return 0


def _run_supervisor(args: argparse.Namespace) -> int:
    if args.mode == "both":
        result = supervisor.run_pair(
            args.task,
            args.agent,
            args.out_dir,
            eval_agent_cmd=args.eval_agent,
            max_attempts=args.max_attempts,
            timeout=args.timeout,
        )
        print(_supervision_pair_summary(result))
        return 0
    summary = supervisor.run_supervision(
        args.task,
        args.agent,
        args.mode,
        args.out_dir,
        eval_agent_cmd=args.eval_agent,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
    )
    print(_supervision_single_summary(summary))
    return 0


def _supervision_single_summary(summary: supervisor.RunSummary) -> str:
    return "\n".join([
        f"mode={summary.mode} solved={summary.solved} attempts={summary.attempts}",
        f"tokens: coding={summary.coding_tokens} eval={summary.eval_tokens} total={summary.total_tokens}",
        f"transcript={summary.transcript}",
        f"metrics={summary.metrics}",
    ])


def _supervision_pair_summary(result: dict) -> str:
    baseline = result["baseline"]
    assisted = result["assisted"]
    return "\n".join([
        "supervision comparison complete",
        f"baseline: solved={baseline['solved']} total_tokens={baseline['total_tokens_estimate']}",
        f"assisted: solved={assisted['solved']} total_tokens={assisted['total_tokens_estimate']}",
        f"side_by_side={result['side_by_side']}",
    ])


def _run_hud_eval(args: argparse.Namespace) -> None:
    if args.mock_judge is not None:
        os.environ["LOOP_AUDITOR_MOCK_JUDGE_SCORE"] = str(args.mock_judge)
    try:
        from loop_auditor_env import eval_harness
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Could not import loop_auditor_env. Run from the repo checkout or install "
            "the LoopHole package with the HUD env included."
        ) from exc
    agg = asyncio.run(eval_harness.run_eval(split=args.split, model_tag=args.model_tag))
    print(f"hud eval aggregate: {agg}")


def _artifact_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.results and args.verdicts:
        return Path(args.results), Path(args.verdicts)
    try:
        from loop_auditor_env import config
    except ModuleNotFoundError as exc:
        raise SystemExit("--results and --verdicts are required when loop_auditor_env is unavailable") from exc
    results = Path(args.results) if args.results else Path(config.EVAL_OUTPUT)
    verdicts = Path(args.verdicts) if args.verdicts else results.with_name("verdicts.jsonl")
    return results, verdicts


if __name__ == "__main__":
    raise SystemExit(main())
