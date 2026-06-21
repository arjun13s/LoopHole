"""Generate richer synthetic loop-auditor trace bundles.

This is still deterministic and synthetic, but the bundle shape is closer to
real-world agent evidence: repo snapshot, referenced command logs, patch diffs,
test-output files, agent transcript, and 10-step looping traces.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from trace_harness.injectors import INJECTORS
from trace_harness.trace_schema import ActionSpan, GroundTruth, StructuredFix, ToolResult
from trace_harness.validator import validate_case_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPO_ROOT / "generated_traces" / "rich_cases"
GROUND_TRUTH_ROOT = REPO_ROOT / "generated_traces" / "rich_ground_truth"
TASKSET_ROOT = REPO_ROOT / "generated_traces" / "rich_taskset"


@dataclass(frozen=True)
class TaskSpec:
    slug: str
    task: str
    module: str
    func: str
    test_name: str
    bad_behavior: str
    expected_behavior: str

    @property
    def correct_file(self) -> str:
        return f"repo/src/{self.module}.py"

    @property
    def wrong_file(self) -> str:
        return f"repo/src/{self.module}_helpers.py"

    @property
    def test_file(self) -> str:
        return f"repo/tests/test_{self.module}.py"


TASKS = [
    TaskSpec("slugify", "Implement slugify(text) for URL-safe ASCII slugs.", "string_utils", "slugify", "test_punctuation", "punctuation remains in the slug", "punctuation becomes collapsed hyphen separators"),
    TaskSpec("csv_header", "Normalize CSV headers into snake_case keys.", "csv_utils", "normalize_header", "test_symbols", "symbols remain in header names", "symbols become single underscores and edges are trimmed"),
    TaskSpec("palindrome", "Implement is_palindrome(text) ignoring case and punctuation.", "palindrome", "is_palindrome", "test_phrase", "punctuation is compared literally", "only alphanumeric lowercase characters are compared"),
    TaskSpec("merge_intervals", "Merge inclusive integer intervals.", "intervals", "merge_intervals", "test_touching_intervals", "touching intervals are left separate", "overlapping or touching intervals are merged"),
    TaskSpec("duration", "Parse simple duration strings into seconds.", "duration", "parse_duration", "test_minutes_seconds", "minutes are parsed but seconds are ignored", "minutes and seconds are both accumulated"),
    TaskSpec("config_bool", "Parse human boolean config values.", "config", "parse_bool", "test_yes_no", "yes/no values raise ValueError", "yes/no/on/off are accepted alongside true/false"),
    TaskSpec("markdown_links", "Extract markdown link URLs from text.", "markdown", "extract_links", "test_multiple_links", "only the first link is returned", "all markdown link targets are returned in order"),
    TaskSpec("url_join", "Join URL path fragments without duplicate slashes.", "url_utils", "join_url", "test_duplicate_slashes", "duplicate slashes are preserved", "exactly one slash joins each fragment"),
    TaskSpec("inventory_total", "Compute inventory total from item quantity and price.", "inventory", "total_value", "test_string_numbers", "string numeric fields are concatenated or rejected", "numeric strings are coerced before multiplying"),
    TaskSpec("ini_parser", "Parse a tiny INI file into section dictionaries.", "ini_parser", "parse_ini", "test_section_keys", "keys after a section are assigned globally", "keys are assigned to the active section"),
]


def main() -> None:
    for path in (DATASET_ROOT, GROUND_TRUTH_ROOT, TASKSET_ROOT):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    train_rows: list[dict] = []
    heldout_rows: list[dict] = []
    for index, spec in enumerate(TASKS):
        split = "heldout" if index >= 8 else "train"
        rows = heldout_rows if split == "heldout" else train_rows
        base = _clean_case(spec)
        clean_gt = GroundTruth(
            case_id=f"{spec.slug}__clean",
            fault_present=False,
            fault_step_id=None,
            failure_type=None,
            fix=None,
        )
        rows.append(_write_case(spec, "clean", base, clean_gt, split))
        for failure_type, injector in INJECTORS.items():
            mutated, gt = injector(base)
            rows.append(_write_case(spec, failure_type, mutated, gt, split))

    _write_jsonl(TASKSET_ROOT / "train.jsonl", train_rows)
    _write_jsonl(TASKSET_ROOT / "heldout.jsonl", heldout_rows)
    print(f"generated {len(train_rows)} train and {len(heldout_rows)} heldout traces")
    print(f"cases: {DATASET_ROOT}")
    print(f"ground truth: {GROUND_TRUTH_ROOT}")
    print(f"indexes: {TASKSET_ROOT}")


def _clean_case(spec: TaskSpec) -> dict:
    trace = [
        ActionSpan(
            "a001",
            "read_file",
            {"path": "repo/README.md"},
            ToolResult("ok", 0, summary="Read task README and project layout."),
            "Read the task brief and repo notes.",
            260,
        ),
        ActionSpan(
            "a002",
            "read_file",
            {"path": spec.test_file},
            ToolResult("ok", 0, summary=f"Focused tests include {spec.test_name}."),
            "Read the focused pytest file.",
            420,
        ),
        ActionSpan(
            "a003",
            "write_file",
            {"path": spec.correct_file, "content_summary": f"Initial {spec.func} implementation; bug: {spec.bad_behavior}."},
            ToolResult("ok", 0, summary="Wrote first implementation attempt."),
            "Wrote an initial implementation based on the tests.",
            510,
        ),
        ActionSpan(
            "a004",
            "run_tests",
            {"command": "pytest -q"},
            ToolResult("error", 1, stdout_ref="test_outputs/a004.txt", summary="1 failed, 5 passed in 0.06s"),
            f"Ran tests and saw {spec.test_name} fail.",
            210,
        ),
        ActionSpan(
            "a005",
            "read_file",
            {"path": "test_outputs/a004.txt"},
            ToolResult("ok", 0, summary="Read the failed assertion and expected value."),
            "Inspected the failing pytest output before patching.",
            190,
        ),
        ActionSpan(
            "a006",
            "read_file",
            {"path": spec.wrong_file},
            ToolResult("ok", 0, summary="Checked a nearby helper file to avoid duplicating behavior."),
            "Read a plausible neighboring helper file for context.",
            330,
        ),
        ActionSpan(
            "a007",
            "write_file",
            {"path": spec.correct_file, "content_summary": f"Fix {spec.func}: {spec.expected_behavior}."},
            ToolResult("ok", 0, summary="Patched the intended implementation file."),
            "Patched the implementation using the failure output.",
            620,
        ),
        ActionSpan(
            "a008",
            "run_tests",
            {"command": "pytest -q"},
            ToolResult("ok", 0, stdout_ref="test_outputs/a008.txt", summary="6 passed in 0.04s"),
            "Reran the full focused test file after the patch.",
            210,
        ),
        ActionSpan(
            "a009",
            "read_file",
            {"path": "patches/a007.diff"},
            ToolResult("ok", 0, summary="Reviewed the final diff before submit."),
            "Reviewed the patch diff after tests passed.",
            240,
        ),
        ActionSpan(
            "a010",
            "submit",
            {"files": [spec.correct_file]},
            ToolResult("ok", 0, summary="Submitted the verified implementation."),
            "Submitted after the passing verification run.",
            120,
        ),
    ]
    return {
        "case_id": spec.slug,
        "task": spec.task,
        "trace": [step.to_json() for step in trace],
        "metadata": {
            "inspect_step_id": "a005",
            "failing_test_step_id": "a004",
            "final_test_step_id": "a008",
            "fix_step_id": "a007",
            "submit_step_id": "a010",
            "correct_edit_path": spec.correct_file,
            "wrong_edit_path": spec.wrong_file,
            "failure_output_ref": "test_outputs/a004.txt",
            "large_context_path": "repo/large_context.md",
        },
    }


def _write_case(spec: TaskSpec, variant: str, case: dict, gt: GroundTruth, split: str) -> dict:
    case_id = f"{spec.slug}__{variant}"
    case_dir = DATASET_ROOT / spec.slug / variant
    case_dir.mkdir(parents=True)
    _write_text(case_dir / "prompt.md", _prompt(spec))
    _write_repo(case_dir / "repo", spec)
    _write_outputs(case_dir, spec)
    _write_trace(case_dir / "trace.jsonl", case["trace"])
    _write_text(case_dir / "agent_transcript.md", _transcript(case["trace"]))
    _write_text(case_dir / "AUDIT.md", _audit_stub())
    gt_payload = gt.to_json()
    gt_payload["case_id"] = case_id
    gt_path = GROUND_TRUTH_ROOT / f"{case_id}.json"
    _write_json(gt_path, gt_payload)
    validate_case_dir(case_dir, gt_path)
    return {
        "case_id": case_id,
        "split": split,
        "case_dir": str(case_dir.relative_to(REPO_ROOT)),
        "ground_truth": str(gt_path.relative_to(REPO_ROOT)),
        "failure_type": "clean" if gt_payload["fault_present"] is False else gt_payload["failure_type"],
    }


def _prompt(spec: TaskSpec) -> str:
    return f"""\
You are fixing a small Python utility repository.

Task: {spec.task}

Work like a coding agent: inspect relevant files, edit the implementation,
run pytest, inspect failures, rerun tests after fixes, then submit.
"""


def _write_repo(repo_dir: Path, spec: TaskSpec) -> None:
    src = repo_dir / "src"
    tests = repo_dir / "tests"
    src.mkdir(parents=True)
    tests.mkdir(parents=True)
    _write_text(repo_dir / "README.md", f"# {spec.slug}\n\n{spec.task}\n")
    _write_text(Path(repo_dir / spec.correct_file.removeprefix("repo/")), _module_source(spec))
    _write_text(Path(repo_dir / spec.wrong_file.removeprefix("repo/")), _helper_source(spec))
    _write_text(Path(repo_dir / spec.test_file.removeprefix("repo/")), _test_source(spec))
    _write_text(repo_dir / "large_context.md", _large_context(spec))


def _write_outputs(case_dir: Path, spec: TaskSpec) -> None:
    outputs = case_dir / "test_outputs"
    outputs.mkdir()
    _write_text(outputs / "a004.txt", f"""\
FAILED {spec.test_file.removeprefix('repo/')}::{spec.test_name}
E       AssertionError: {spec.bad_behavior}
E       Expected: {spec.expected_behavior}
1 failed, 5 passed in 0.06s
""")
    _write_text(outputs / "a008.txt", "6 passed in 0.04s\n")
    _write_text(outputs / "a012.txt", "6 passed in 0.04s\n")
    _write_text(outputs / "wrong_file_after_edit.txt", f"""\
FAILED {spec.test_file.removeprefix('repo/')}::{spec.test_name}
E       AssertionError: failure still present because {spec.correct_file} was unchanged
1 failed, 5 passed in 0.05s
""")
    patches = case_dir / "patches"
    patches.mkdir()
    _write_text(patches / "a007.diff", f"""\
diff --git a/{spec.correct_file.removeprefix('repo/')} b/{spec.correct_file.removeprefix('repo/')}
@@
-    # initial implementation
+    # corrected implementation: {spec.expected_behavior}
""")
    logs = case_dir / "command_logs"
    logs.mkdir()
    _write_text(logs / "pytest_a004.log", (outputs / "a004.txt").read_text())
    _write_text(logs / "pytest_a008.log", (outputs / "a008.txt").read_text())


def _module_source(spec: TaskSpec) -> str:
    return f'''"""Utility module for {spec.slug}."""


def {spec.func}(*args, **kwargs):
    """Implementation intentionally represented as final repo snapshot."""
    raise NotImplementedError("synthetic repo snapshot; trace carries edit history")
'''


def _helper_source(spec: TaskSpec) -> str:
    return f'''"""Neighboring helper module.

This file has a similar name so wrong-file edits are plausible, but it is not
the implementation target for {spec.func}.
"""


def helper_value(value):
    return value
'''


def _test_source(spec: TaskSpec) -> str:
    return f'''from src.{spec.module} import {spec.func}


def {spec.test_name}():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable({spec.func})
'''


def _large_context(spec: TaskSpec) -> str:
    return (
        f"# Full repository dump for {spec.slug}\n"
        "This file intentionally contains broad, low-value context.\n"
        + "\n".join(f"generated irrelevant line {i}: dependency notes, docs, logs" for i in range(500))
        + "\n"
    )


def _transcript(trace: list[dict]) -> str:
    lines = ["# worker transcript", ""]
    for step in trace:
        lines.append(f"## {step['step_id']} {step['tool_name']}")
        lines.append(f"args: `{json.dumps(step['args'], sort_keys=True)}`")
        result = step["result"]
        lines.append(f"status: `{result['status']}`")
        if result.get("stdout_ref"):
            lines.append(f"stdout_ref: `{result['stdout_ref']}`")
        lines.append(step["summary"])
        lines.append("")
    return "\n".join(lines)


def _audit_stub() -> str:
    return """\
# audit

```json
{
  "fault_present": null,
  "predicted_step_id": null,
  "failure_type": null,
  "proposed_fix": null,
  "evidence": []
}
```
"""


def _write_trace(path: Path, trace: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in trace:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
