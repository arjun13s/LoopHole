"""Command-line entry point for Loop-Auditor eval + self-improvement."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

from . import analyzer


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
