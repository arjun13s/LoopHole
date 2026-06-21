"""Schema-validated ingestion — the dashboard's trust boundary.

Every external record (eval-results, verdict sidecar, traces) is validated
against the FROZEN schemas in ``<repo>/schemas`` before anything is rendered.
Invalid data fails fast with a clear, actionable error.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as _JSONSchemaValidationError

# Re-exported so callers depend on dashboard.loader, not jsonschema internals.
ValidationError = _JSONSchemaValidationError

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = PKG_DIR / "fixtures"


def bundled_fixture_paths():
    """(results_paths, verdicts_path, trace_paths) for the bundled --mock demo."""
    return (
        [FIXTURES_DIR / "eval_results.jsonl"],
        FIXTURES_DIR / "verdicts.jsonl",
        sorted((FIXTURES_DIR / "traces").glob("*.json")),
    )

# The verdict sidecar (a Person 3 ↔ Person 2 contract) is an envelope of the
# frozen verdict object plus routing keys. We validate the verdict CORE against
# schemas/verdict.json and treat these two as the envelope.
_VERDICT_ENVELOPE_KEYS = ("run_id", "model")
_VERDICT_CORE_KEYS = ("fault_present", "predicted_step_id", "failure_type", "explanation", "proposed_fix")


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """Load a frozen schema by base name (e.g. 'eval_result')."""
    path = SCHEMAS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Frozen schema not found: {path}")
    return json.loads(path.read_text())


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name))


def _iter_jsonl(path: Path):
    """Yield parsed JSON objects from a .jsonl file, skipping blank lines."""
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            yield json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc


def load_eval_results(paths: list) -> list[dict]:
    """Load + validate eval-result records from one or more JSONL files."""
    validator = _validator("eval_result")
    out: list[dict] = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"eval-results file not found: {p}")
        for rec in _iter_jsonl(p):
            validator.validate(rec)
            out.append(rec)
    return out


def load_verdicts(path) -> dict:
    """Load the OPTIONAL verdict sidecar, keyed by (run_id, model).

    A missing file is not an error — the dashboard degrades gracefully to a
    booleans-only verdict summary when no sidecar is present.
    """
    path = Path(path)
    if not path.exists():
        return {}
    core_validator = _validator("verdict")
    out: dict = {}
    for rec in _iter_jsonl(path):
        missing = [k for k in (*_VERDICT_ENVELOPE_KEYS, *_VERDICT_CORE_KEYS) if k not in rec]
        if missing:
            raise ValidationError(f"verdict sidecar record missing keys: {missing}")
        # Validate the verdict CORE against the frozen verdict schema.
        core_validator.validate({k: rec[k] for k in _VERDICT_CORE_KEYS})
        out[(rec["run_id"], rec["model"])] = rec
    return out


def load_traces(paths) -> dict:
    """Load + validate trace JSON files, keyed by run_id."""
    validator = _validator("trace")
    out: dict = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"trace file not found: {p}")
        trace = json.loads(p.read_text())
        validator.validate(trace)
        out[trace["run_id"]] = trace
    return out


def resolve_inputs(args):
    """Map parsed CLI args to (results_paths, verdicts_path, trace_paths).

    Shared by the static (--render) and interactive (TUI) entry points. Falls
    back to the bundled --mock fixtures when no explicit results are given.
    """
    if args.mock or not args.results:
        return bundled_fixture_paths()
    results = [Path(p) for p in args.results]
    verdicts = Path(args.verdicts) if args.verdicts else Path("/nonexistent")  # optional
    traces: list[Path] = []
    if args.traces:
        tp = Path(args.traces)
        traces = sorted(tp.glob("*.json")) if tp.is_dir() else [tp]
    return results, verdicts, traces
