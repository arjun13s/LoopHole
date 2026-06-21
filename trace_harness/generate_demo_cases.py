"""Generate the hour-0 demo case set for the synthetic trace harness."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from trace_harness.injectors import INJECTORS
from trace_harness.reward import score_verdict
from trace_harness.trace_schema import ActionSpan, GroundTruth, StructuredFix, ToolResult
from trace_harness.validator import validate_case_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "generated_traces" / "string_utils"
GROUND_TRUTH_ROOT = REPO_ROOT / "generated_traces" / "string_utils_ground_truth"


def main() -> None:
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    if GROUND_TRUTH_ROOT.exists():
        shutil.rmtree(GROUND_TRUTH_ROOT)
    OUT_ROOT.mkdir(parents=True)
    GROUND_TRUTH_ROOT.mkdir(parents=True)

    base_case = _clean_case()
    clean_gt = GroundTruth(
        case_id="clean",
        fault_present=False,
        fault_step_id=None,
        failure_type=None,
        fix=None,
    )
    _write_case("clean", base_case, clean_gt)

    for name, injector in INJECTORS.items():
        mutated, gt = injector(base_case)
        _write_case(name, mutated, gt)

    _write_reward_demo()
    for name in ("clean", *INJECTORS):
        validate_case_dir(OUT_ROOT / name, GROUND_TRUTH_ROOT / f"{name}.json")
    print("generated and validated: clean, resource_misuse, tool_misuse, routing, wrong_file_edit")
    print(f"cases: {OUT_ROOT}")
    print(f"ground truth: {GROUND_TRUTH_ROOT}")


def _clean_case() -> dict:
    trace = [
        ActionSpan(
            step_id="a001",
            tool_name="write_file",
            args={
                "path": "repo/src/string_utils.py",
                "content_summary": "Initial slugify implementation that lowercases and replaces spaces only.",
            },
            result=ToolResult(status="ok", exit_code=0, summary="Wrote initial implementation."),
            summary="Wrote a first slugify implementation.",
            tokens=320,
        ),
        ActionSpan(
            step_id="a002",
            tool_name="run_tests",
            args={"command": "pytest -q"},
            result=ToolResult(
                status="error",
                exit_code=1,
                stdout_ref="test_outputs/a002.txt",
                summary="1 failed, 4 passed in 0.03s",
            ),
            summary="Ran tests and saw punctuation handling fail.",
            tokens=180,
        ),
        ActionSpan(
            step_id="a003",
            tool_name="read_file",
            args={"path": "test_outputs/a002.txt"},
            result=ToolResult(
                status="ok",
                exit_code=0,
                summary="Read the failed assertion for punctuation separators.",
            ),
            summary="Inspected the failing pytest output before patching.",
            tokens=140,
        ),
        ActionSpan(
            step_id="a004",
            tool_name="write_file",
            args={
                "path": "repo/src/string_utils.py",
                "content_summary": "Replace non-alphanumeric runs with hyphens, collapse duplicates, trim edges.",
            },
            result=ToolResult(status="ok", exit_code=0, summary="Patched slugify implementation."),
            summary="Fixed slugify in the implementation file.",
            tokens=380,
        ),
        ActionSpan(
            step_id="a005",
            tool_name="run_tests",
            args={"command": "pytest -q"},
            result=ToolResult(
                status="ok",
                exit_code=0,
                stdout_ref="test_outputs/a005.txt",
                summary="5 passed in 0.02s",
            ),
            summary="Reran tests after the fix and they passed.",
            tokens=160,
        ),
        ActionSpan(
            step_id="a006",
            tool_name="submit",
            args={"files": ["repo/src/string_utils.py"]},
            result=ToolResult(status="ok", exit_code=0, summary="Submitted final implementation."),
            summary="Submitted after the passing verification run.",
            tokens=90,
        ),
    ]
    return {
        "case_id": "clean",
        "task": "Implement slugify(text) in a Python string-utils repo.",
        "trace": [span.to_json() for span in trace],
    }


def _write_case(name: str, case: dict, ground_truth: GroundTruth) -> None:
    case_dir = OUT_ROOT / name
    case_dir.mkdir(parents=True)
    _write_text(case_dir / "prompt.md", case["task"] + "\n")
    _write_repo(case_dir / "repo")
    _write_test_outputs(case_dir / "test_outputs")
    _write_trace(case_dir / "trace.jsonl", case["trace"])
    _write_text(case_dir / "AUDIT.md", _audit_stub())
    _write_json(GROUND_TRUTH_ROOT / f"{name}.json", ground_truth.to_json())


def _write_repo(repo_dir: Path) -> None:
    src = repo_dir / "src"
    tests = repo_dir / "tests"
    src.mkdir(parents=True)
    tests.mkdir(parents=True)
    _write_text(src / "string_utils.py", """\
import re


def slugify(text: str) -> str:
    lowered = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug
""")
    _write_text(src / "string_format.py", """\
def title_case(text: str) -> str:
    return " ".join(part.capitalize() for part in text.split())
""")
    _write_text(tests / "test_string_utils.py", """\
from src.string_utils import slugify


def test_basic_words():
    assert slugify("Hello World") == "hello-world"


def test_punctuation():
    assert slugify("Hello, world!") == "hello-world"


def test_repeated_separators():
    assert slugify("A  ---  B") == "a-b"


def test_edges():
    assert slugify("  hello  ") == "hello"


def test_empty():
    assert slugify("!!!") == ""
""")
    _write_text(repo_dir / "large_context.md", "irrelevant generated context\n" * 400)


def _write_test_outputs(out_dir: Path) -> None:
    out_dir.mkdir(parents=True)
    _write_text(out_dir / "a002.txt", """\
FAILED tests/test_string_utils.py::test_punctuation
E       AssertionError: assert 'hello,-world!' == 'hello-world'
E         - hello-world
E         + hello,-world!
1 failed, 4 passed in 0.03s
""")
    _write_text(out_dir / "a005.txt", "5 passed in 0.02s\n")


def _write_trace(path: Path, trace: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in trace:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _write_reward_demo() -> None:
    demo_dir = REPO_ROOT / "generated_traces" / "reward_demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    gt = json.loads((GROUND_TRUTH_ROOT / "wrong_file_edit.json").read_text())
    correct = {
        "fault_present": True,
        "predicted_step_id": "a004",
        "failure_type": "wrong_file_edit",
        "proposed_fix": {
            "action": "replace",
            "step_id": "a004",
            "tool_name": "write_file",
            "target": "repo/src/string_utils.py",
        },
        "evidence": ["a004"],
    }
    wrong = {
        "fault_present": True,
        "predicted_step_id": "a003",
        "failure_type": "tool_misuse",
        "proposed_fix": {
            "action": "insert",
            "step_id": "a003",
            "tool_name": "read_file",
            "target": "test_outputs/a002.txt",
        },
        "evidence": ["a002", "a003"],
    }
    _write_json(demo_dir / "correct_verdict.json", correct)
    _write_json(demo_dir / "wrong_verdict.json", wrong)
    _write_json(
        demo_dir / "scores.json",
        {
            "case": "wrong_file_edit",
            "correct_score": score_verdict(correct, gt),
            "wrong_score": score_verdict(wrong, gt),
        },
    )


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


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
