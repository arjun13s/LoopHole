"""Local tool loop for live coding-model trace generation.

This module runs inside Modal or locally. It does not inject faults. It only
collects clean successful worker traces that can later be corrupted by the
deterministic injectors.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from trace_harness.live_task_templates import LIVE_TASK_TEMPLATES, LiveTaskTemplate
from trace_harness.trace_schema import ActionSpan, GroundTruth, ToolResult
from trace_harness.validator import validate_case_dir


class WorkerModel(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the next JSON action as text."""


@dataclass
class LiveTraceResult:
    case_id: str
    success: bool
    case_dir: str | None
    ground_truth_path: str | None
    reason: str
    steps: int
    debug_tail: str


SYSTEM_PROMPT = """\
You are a coding agent operating through tools. Respond with exactly one JSON
object and no prose. Use one tool per turn.

Available actions:
{"tool_name":"read_file","args":{"path":"repo/path.py"}}
{"tool_name":"write_file","args":{"path":"repo/path.py","content":"FULL FILE CONTENT"}}
{"tool_name":"run_tests","args":{"command":"pytest -q"}}
{"tool_name":"submit","args":{"files":["repo/src/file.py"]}}

Rules:
- Read tests and relevant source before editing.
- Use the exact file paths listed in the task prompt.
- After any edit, run tests before submit.
- Submit only after tests pass.
"""


def run_live_trace_batch(
    model: WorkerModel,
    output_root: str | Path,
    max_successes: int = 5,
    attempts_per_template: int = 4,
) -> list[LiveTraceResult]:
    output_root = Path(output_root)
    results: list[LiveTraceResult] = []
    successes = 0
    for template in LIVE_TASK_TEMPLATES:
        for attempt in range(attempts_per_template):
            if successes >= max_successes:
                return results
            result = run_live_trace(
                model=model,
                template=template,
                output_root=output_root,
                attempt=attempt,
            )
            results.append(result)
            if result.success:
                successes += 1
    return results


def run_live_trace(
    model: WorkerModel,
    template: LiveTaskTemplate,
    output_root: Path,
    attempt: int,
) -> LiveTraceResult:
    case_id = f"{template.slug}__live_{attempt:03d}"
    with tempfile.TemporaryDirectory(prefix=f"loophole_{template.slug}_") as tmp:
        work = Path(tmp)
        _materialize_repo(work, template)
        trace: list[dict[str, Any]] = []
        transcript: list[str] = []
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _task_prompt(template)},
        ]
        submitted = False
        saw_passing_tests = False
        for step_num in range(1, template.max_steps + 1):
            raw = model.complete(messages)
            action = _parse_action(raw)
            step_id = f"a{step_num:03d}"
            span, observation = _execute_action(work, template, step_id, action)
            if span.tool_name == "run_tests" and span.result.status == "ok":
                saw_passing_tests = True
                observation = (
                    observation
                    + "\n\nTests passed. Submit now with exactly this JSON action:\n"
                    + json.dumps({"tool_name": "submit", "args": {"files": list(template.expected_submit_files)}})
                )
            elif span.tool_name == "run_tests" and span.result.status == "error":
                stdout_ref = span.result.stdout_ref or f"test_outputs/{step_id}.txt"
                observation = (
                    observation
                    + "\n\nTests failed. Before editing, inspect the failure output with this JSON action:\n"
                    + json.dumps({"tool_name": "read_file", "args": {"path": stdout_ref}})
                )
            trace.append(span.to_json())
            transcript.extend(_transcript_lines(step_id, raw, observation))
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": observation})
            if span.tool_name == "submit":
                submitted = True
                break

        debug_tail = _debug_tail(trace)
        if not submitted:
            case_dir = _write_attempt_bundle(work, template, output_root, attempt, trace, transcript, success=False)
            return LiveTraceResult(case_id, False, str(case_dir), None, "worker did not submit", len(trace), debug_tail)
        if not saw_passing_tests:
            case_dir = _write_attempt_bundle(work, template, output_root, attempt, trace, transcript, success=False)
            return LiveTraceResult(
                case_id,
                False,
                str(case_dir),
                None,
                "worker submitted without passing tests",
                len(trace),
                debug_tail,
            )
        if not _submitted_expected_file(trace, template):
            case_dir = _write_attempt_bundle(work, template, output_root, attempt, trace, transcript, success=False)
            return LiveTraceResult(case_id, False, str(case_dir), None, "worker submitted wrong file", len(trace), debug_tail)

        case_dir = _write_attempt_bundle(work, template, output_root, attempt, trace, transcript, success=True)
        gt_dir = output_root / "live_ground_truth"
        gt_dir.mkdir(parents=True, exist_ok=True)
        ground_truth = GroundTruth(case_id, False, None, None, None).to_json()
        gt_path = gt_dir / f"{case_id}__clean.json"
        _write_json(gt_path, ground_truth)
        try:
            validate_case_dir(case_dir, gt_path)
        except ValueError as exc:
            failed_dir = _write_attempt_bundle(work, template, output_root, attempt, trace, transcript, success=False)
            if case_dir.exists():
                shutil.rmtree(case_dir)
            if gt_path.exists():
                gt_path.unlink()
            return LiveTraceResult(
                case_id,
                False,
                str(failed_dir),
                None,
                f"clean trace failed validator: {exc}",
                len(trace),
                debug_tail,
            )
        return LiveTraceResult(
            case_id=case_id,
            success=True,
            case_dir=str(case_dir),
            ground_truth_path=str(gt_path),
            reason="ok",
            steps=len(trace),
            debug_tail=debug_tail,
        )


def _task_prompt(template: LiveTaskTemplate) -> str:
    file_list = "\n".join(f"- {path}" for path in sorted(template.files))
    return f"""\
Repository root is the current working directory. Task:
{template.task}

Files available:
{file_list}

Use `pytest -q` for tests. If you submit, include exactly one of:
{json.dumps(list(template.expected_submit_files))}

Keep scope narrow. Expected repo size is small; prefer targeted reads.
"""


def _materialize_repo(work: Path, template: LiveTaskTemplate) -> None:
    for rel, content in template.files.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for pkg in (work / "repo" / "src", work / "repo" / "tests"):
        (pkg / "__init__.py").write_text("", encoding="utf-8")
    (work / "test_outputs").mkdir()
    (work / "command_logs").mkdir()
    (work / "patches").mkdir()


def _parse_action(raw: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "tool_name" in obj and "args" in obj:
            return obj
    return {"tool_name": "submit", "args": {"files": []}, "_parse_error": raw[:500]}


def _execute_action(
    work: Path,
    template: LiveTaskTemplate,
    step_id: str,
    action: dict[str, Any],
) -> tuple[ActionSpan, str]:
    tool_name = str(action.get("tool_name", ""))
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    if tool_name == "read_file":
        return _read_file(work, step_id, args)
    if tool_name == "write_file":
        return _write_file(work, template, step_id, args)
    if tool_name == "run_tests":
        return _run_tests(work, step_id, args)
    if tool_name == "submit":
        files = args.get("files") if isinstance(args.get("files"), list) else []
        normalized_files = []
        for file_path in files:
            normalized, _ = _resolve_tool_path(work, str(file_path), for_write=False)
            normalized_files.append(normalized)
        span = ActionSpan(
            step_id,
            "submit",
            {"files": normalized_files},
            ToolResult("ok", 0, summary="Submitted files."),
            "Submitted the claimed final files.",
            tokens=80,
        )
        return span, f"submit accepted for files={normalized_files}"
    span = ActionSpan(
        step_id,
        "submit",
        {"files": []},
        ToolResult("error", 2, summary=f"Unknown tool: {tool_name}"),
        "Invalid tool call; forced terminal submit error.",
        tokens=20,
    )
    return span, f"unknown tool {tool_name!r}; available tools are read_file/write_file/run_tests/submit"


def _read_file(work: Path, step_id: str, args: dict[str, Any]) -> tuple[ActionSpan, str]:
    rel, path = _resolve_tool_path(work, str(args.get("path", "")), for_write=False)
    if path is None or not path.exists():
        summary = f"File not found: {rel}. Available files:\n{_file_tree(work / 'repo')}"
        result = ToolResult("error", 1, summary=summary[:240])
        return ActionSpan(step_id, "read_file", {"path": rel}, result, "Tried to read a missing file.", 60), summary
    if path.is_dir():
        listing = _file_tree(path)
        result = ToolResult("ok", 0, summary=f"Listed directory {rel}.")
        return ActionSpan(step_id, "read_file", {"path": rel}, result, f"Listed {rel}.", 90), listing
    text = path.read_text(encoding="utf-8", errors="replace")
    result = ToolResult("ok", 0, summary=f"Read {rel} ({len(text)} chars).")
    return ActionSpan(step_id, "read_file", {"path": rel}, result, f"Read {rel}.", max(80, len(text) // 4)), text[:6000]


def _write_file(work: Path, template: LiveTaskTemplate, step_id: str, args: dict[str, Any]) -> tuple[ActionSpan, str]:
    rel, path = _resolve_tool_path(work, str(args.get("path", "")), for_write=True)
    content = args.get("content")
    if path is None or not rel.startswith("repo/") or not isinstance(content, str):
        result = ToolResult("error", 1, summary="write_file requires repo-relative path and full content string.")
        return ActionSpan(step_id, "write_file", {"path": rel, "content_summary": "invalid write"}, result, "Invalid write_file call.", 80), result.summary
    before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    patch_rel = f"patches/{step_id}.diff"
    _write_text(work / patch_rel, _simple_diff(rel, before, content))
    summary = f"Wrote {rel}; diff saved to {patch_rel}."
    span = ActionSpan(
        step_id,
        "write_file",
        {"path": rel, "content_summary": _summarize_content(content)},
        ToolResult("ok", 0, summary=summary),
        f"Wrote {rel}.",
        max(120, len(content) // 5),
    )
    return span, summary


def _run_tests(work: Path, step_id: str, args: dict[str, Any]) -> tuple[ActionSpan, str]:
    command = str(args.get("command") or "pytest -q")
    proc = subprocess.run(
        command,
        cwd=work / "repo",
        shell=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    out_rel = f"test_outputs/{step_id}.txt"
    log_rel = f"command_logs/{step_id}.log"
    _write_text(work / out_rel, combined)
    _write_text(work / log_rel, f"$ {command}\nexit={proc.returncode}\n\n{combined}")
    status = "ok" if proc.returncode == 0 else "error"
    summary = _summarize_test_output(combined, proc.returncode)
    span = ActionSpan(
        step_id,
        "run_tests",
        {"command": command},
        ToolResult(status, proc.returncode, stdout_ref=out_rel, summary=summary),
        f"Ran tests: {summary}",
        180,
    )
    return span, combined[-6000:]


def _resolve_tool_path(work: Path, rel: str, *, for_write: bool) -> tuple[str, Path | None]:
    rel = rel.strip()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return rel, None
    if rel.startswith("repo/") or rel in {"repo", "test_outputs", "patches", "command_logs"}:
        return rel, work / rel
    if rel.startswith(("test_outputs/", "patches/", "command_logs/")):
        return rel, work / rel
    repo_rel = f"repo/{rel}"
    repo_path = work / repo_rel
    if for_write or repo_path.exists():
        return repo_rel, repo_path
    return rel, work / rel


def _safe_path(work: Path, rel: str) -> Path | None:
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    return work / rel


def _file_tree(root: Path) -> str:
    if not root.exists():
        return ""
    files = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and "__pycache__" not in item.parts:
            files.append(str(item.relative_to(root)))
    return "\n".join(files[:80])


def _submitted_expected_file(trace: list[dict[str, Any]], template: LiveTaskTemplate) -> bool:
    for step in reversed(trace):
        if step.get("tool_name") == "submit":
            files = tuple(step.get("args", {}).get("files", []))
            return any(path in files for path in template.expected_submit_files)
    return False


def _copy_repo_snapshot(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _copy_optional_dir(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst)


def _write_attempt_bundle(
    work: Path,
    template: LiveTaskTemplate,
    output_root: Path,
    attempt: int,
    trace: list[dict[str, Any]],
    transcript: list[str],
    success: bool,
) -> Path:
    root_name = "live_cases" if success else "failed_cases"
    leaf_name = "clean" if success else "attempt"
    case_dir = output_root / root_name / template.slug / f"live_{attempt:03d}" / leaf_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    _copy_repo_snapshot(work / "repo", case_dir / "repo")
    _copy_optional_dir(work / "test_outputs", case_dir / "test_outputs")
    _copy_optional_dir(work / "patches", case_dir / "patches")
    _copy_optional_dir(work / "command_logs", case_dir / "command_logs")
    _write_text(case_dir / "prompt.md", _task_prompt(template))
    _write_trace(case_dir / "trace.jsonl", trace)
    _write_text(case_dir / "agent_transcript.md", "\n".join(transcript) + "\n")
    _write_text(case_dir / "AUDIT.md", _audit_stub())
    return case_dir


def _write_trace(path: Path, trace: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in trace:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _debug_tail(trace: list[dict[str, Any]], count: int = 5) -> str:
    pieces = []
    for row in trace[-count:]:
        result = row.get("result", {})
        pieces.append(
            f"{row.get('step_id')}:{row.get('tool_name')}:{result.get('status')}:{result.get('summary')}"
        )
    return " | ".join(pieces)


def _transcript_lines(step_id: str, raw: str, observation: str) -> list[str]:
    return [
        f"## {step_id}",
        "model_action:",
        "```json",
        raw.strip(),
        "```",
        "observation:",
        "```",
        observation[-3000:].strip(),
        "```",
        "",
    ]


def _simple_diff(rel: str, before: str, after: str) -> str:
    return (
        f"diff --git a/{rel.removeprefix('repo/')} b/{rel.removeprefix('repo/')}\n"
        "@@\n"
        f"- {before[:300].replace(chr(10), chr(10) + '- ')}\n"
        f"+ {after[:300].replace(chr(10), chr(10) + '+ ')}\n"
    )


def _summarize_content(content: str) -> str:
    first = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return first[:160] or f"{len(content)} chars"


def _summarize_test_output(output: str, exit_code: int) -> str:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if " passed" in line or " failed" in line or " error" in line:
            return line[:220]
    return "tests passed" if exit_code == 0 else f"tests failed with exit code {exit_code}"


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
