"""CLI: run the base auditor (Modal vLLM) over traces -> dashboard-ready base output.

  # after `modal deploy training/modal_infer.py` prints the URL:
  python -m training.run_base_eval \
    --traces dashboard/fixtures/traces \
    --base-url https://<workspace>--loophole-base-vllm-serve.modal.run/v1 \
    --out results

Emits results/eval_results.base.jsonl + results/verdicts.base.jsonl (the dashboard
reads these). Explanation is scored deterministically (fix-by-comparison + citation
gate) — identical to the trained side, so base-vs-trained is fair.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import base_eval
from .backends import ModalBackend

PKG_DIR = Path(__file__).resolve().parent
SCHEMAS_DIR = PKG_DIR.parent / "schemas"


def load_traces(path) -> list[dict]:
    """Load traces from a directory of .json files, a .jsonl, or a single .json."""
    p = Path(path)
    if p.is_dir():
        return [json.loads(fp.read_text()) for fp in sorted(p.glob("*.json"))]
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return [json.loads(p.read_text())]


def validate_traces(traces: list[dict]) -> None:
    """Fail loudly if traces don't conform to the frozen trace schema (issue #3 guard)."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(json.loads((SCHEMAS_DIR / "trace.json").read_text()))
    for t in traces:
        validator.validate(t)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_base_eval")
    ap.add_argument("--traces", required=True, help="dir of .json | a .jsonl | a single .json")
    ap.add_argument("--base-url", required=True, help="Modal vLLM OpenAI base url (…/v1)")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--model-tag", default="base")
    ap.add_argument("--out", default="results")
    ap.add_argument("--base-traces-dir", default=None, help="clean reference traces for fix grading")
    ap.add_argument("--no-validate-traces", action="store_true")
    args = ap.parse_args(argv)

    traces = load_traces(args.traces)
    if not args.no_validate_traces:
        validate_traces(traces)
    backend = ModalBackend(base_url=args.base_url, model=args.model)
    scorer = (
        base_eval.deterministic_explanation_scorer(args.base_traces_dir)
        if args.base_traces_dir
        else None  # base_eval lazily builds the deterministic default
    )
    agg = base_eval.run_base_eval(
        traces, backend, model_tag=args.model_tag, explanation_scorer=scorer, out_dir=args.out
    )
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
