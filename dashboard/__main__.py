"""CLI entry for the Loop-Auditor dashboard.

  python -m dashboard --render              # static Rich report (default; CLI-agent visible)
  python -m dashboard --render --mock       # use the bundled demo fixtures
  python -m dashboard --render \
      --results results/base.jsonl results/trained.jsonl \
      --verdicts results/verdicts.jsonl --traces path/to/traces/

  python -m dashboard                        # (stretch) interactive Textual TUI — needs a real terminal

The static (--render) path is the primary surface and the one wired into run_demo.sh.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from . import loader, render


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dashboard", description="Loop-Auditor dashboard")
    p.add_argument("--render", action="store_true", help="static Rich report to stdout (CLI-agent visible)")
    p.add_argument("--mock", action="store_true", help="use bundled demo fixtures")
    p.add_argument("--results", nargs="+", metavar="JSONL", help="eval-result JSONL file(s)")
    p.add_argument("--verdicts", metavar="JSONL", help="optional verdict sidecar JSONL")
    p.add_argument("--traces", metavar="PATH", help="trace .json file(s) or a directory of them")
    return p


def _source_label(args) -> str:
    """Provenance subtitle so the surface never misleads about what's real."""
    if args.mock or not args.results:
        return "demo fixtures · illustrative verdicts on real held-out traces"
    return "real held-out eval"


def run_static(args) -> int:
    results_paths, verdicts_path, trace_paths = loader.resolve_inputs(args)
    console = Console()
    try:
        records = loader.load_eval_results(results_paths)
        verdicts = loader.load_verdicts(verdicts_path)
        traces = loader.load_traces(trace_paths)
    except (loader.ValidationError, FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Failed to load dashboard inputs:[/] {exc}")
        return 1
    console.print(render.dashboard(records, verdicts, traces, source_label=_source_label(args)))
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.render or not sys.stdout.isatty():
        # Default to static when piped/captured (e.g. inside a CLI agent).
        return run_static(args)
    # Interactive Textual TUI is a stretch layer; fall back to static if absent
    # or broken (e.g. wrong Textual version that raises ImportError/AttributeError).
    try:
        from .interactive import run_interactive  # noqa: F401
    except ImportError:
        return run_static(args)
    return run_interactive(args)  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
