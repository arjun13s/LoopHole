"""Stop-and-resume supervisor for coding-agent repair experiments.

The supervisor is intentionally CLI-agnostic. It runs a coding-agent command in
a task repo, watches test failures, optionally asks an eval agent for a
diagnosis, then resumes the coding agent with that diagnosis in a hint file.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


DEFAULT_MAX_ATTEMPTS = 2


@dataclass
class RunSummary:
    mode: str
    solved: bool
    attempts: int
    test_runs: int
    coding_tokens: int
    eval_tokens: int
    total_tokens: int
    out_dir: Path
    transcript: Path
    metrics: Path


def run_supervision(
    task_path: "str | Path",
    agent_cmd: str,
    mode: str,
    out_dir: "str | Path",
    eval_agent_cmd: "str | None" = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: int = 120,
) -> RunSummary:
    """Run one baseline or assisted stop-and-resume experiment."""
    if mode not in {"baseline", "assisted"}:
        raise ValueError("mode must be baseline or assisted")
    task_path = Path(task_path)
    task = json.loads(task_path.read_text())
    run_dir = Path(out_dir)
    repo_dir = run_dir / "repo"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _materialize_repo(task, repo_dir)

    transcript_lines = [
        f"# {task.get('id', task_path.stem)} [{mode}]",
        "",
        "## Task",
        str(task.get("prompt", "")).strip(),
        "",
    ]
    coding_tokens = 0
    eval_tokens = 0
    test_runs = 0
    solved = False
    hint_text = ""
    latest_test_output = ""

    for attempt in range(1, max_attempts + 1):
        hint_file = logs_dir / f"hint_{attempt}.md"
        hint_file.write_text(hint_text)
        agent_log = logs_dir / f"agent_attempt_{attempt}.log"
        result = _run_agent(
            agent_cmd,
            task_path=task_path,
            repo_dir=repo_dir,
            mode=mode,
            attempt=attempt,
            hint_file=hint_file,
            transcript_file=agent_log,
            timeout=timeout,
        )
        agent_text = _combined_output(result)
        agent_log.write_text(agent_text)
        coding_tokens += estimate_tokens(agent_text)
        transcript_lines.extend([
            f"## Coding Agent Attempt {attempt}",
            _fenced(agent_text),
            "",
        ])

        test_result = _run_tests(task, repo_dir, timeout=timeout)
        test_runs += 1
        latest_test_output = _combined_output(test_result)
        test_log = logs_dir / f"tests_attempt_{attempt}.log"
        test_log.write_text(latest_test_output)
        transcript_lines.extend([
            f"## Test Result {attempt}",
            f"- exit_code: {test_result.returncode}",
            _fenced(latest_test_output),
            "",
        ])
        if test_result.returncode == 0:
            solved = True
            break
        if attempt >= max_attempts:
            break
        if mode == "assisted":
            eval_text = _run_eval_agent(
                eval_agent_cmd,
                task=task,
                task_path=task_path,
                repo_dir=repo_dir,
                logs_dir=logs_dir,
                latest_test_output=latest_test_output,
                timeout=timeout,
            )
            eval_tokens += estimate_tokens(eval_text)
            hint_text = _assisted_hint(eval_text)
            transcript_lines.extend([
                "## Eval Agent Intervention",
                _fenced(eval_text, "json" if eval_text.lstrip().startswith("{") else ""),
                "",
            ])
        else:
            hint_text = _baseline_hint(latest_test_output)
            transcript_lines.extend([
                "## Baseline Self-Prompt",
                _fenced(hint_text),
                "",
            ])

    transcript = run_dir / "transcript.md"
    metrics = run_dir / "metrics.json"
    total_tokens = coding_tokens + eval_tokens
    summary = RunSummary(
        mode=mode,
        solved=solved,
        attempts=attempt,
        test_runs=test_runs,
        coding_tokens=coding_tokens,
        eval_tokens=eval_tokens,
        total_tokens=total_tokens,
        out_dir=run_dir,
        transcript=transcript,
        metrics=metrics,
    )
    transcript_lines.extend([
        "## Metrics",
        _fenced(json.dumps(_summary_dict(summary), indent=2), "json"),
        "",
    ])
    transcript.write_text("\n".join(transcript_lines))
    metrics.write_text(json.dumps(_summary_dict(summary), indent=2) + "\n")
    return summary


def run_pair(
    task_path: "str | Path",
    agent_cmd: str,
    out_dir: "str | Path",
    eval_agent_cmd: "str | None" = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: int = 120,
) -> dict:
    """Run baseline and assisted variants, then write a side-by-side report."""
    root = Path(out_dir)
    baseline = run_supervision(
        task_path, agent_cmd, "baseline", root / "baseline",
        eval_agent_cmd=eval_agent_cmd, max_attempts=max_attempts, timeout=timeout,
    )
    assisted = run_supervision(
        task_path, agent_cmd, "assisted", root / "assisted",
        eval_agent_cmd=eval_agent_cmd, max_attempts=max_attempts, timeout=timeout,
    )
    side_by_side = root / "side_by_side.md"
    side_by_side.write_text(format_side_by_side(baseline, assisted))
    return {
        "baseline": _summary_dict(baseline),
        "assisted": _summary_dict(assisted),
        "side_by_side": str(side_by_side),
    }


def format_side_by_side(baseline: RunSummary, assisted: RunSummary) -> str:
    """Return a compact side-by-side comparison report."""
    return "\n".join([
        "# Loop-Auditor Supervision Comparison",
        "",
        "| Metric | Baseline | Eval-assisted |",
        "|---|---:|---:|",
        f"| solved | {baseline.solved} | {assisted.solved} |",
        f"| attempts | {baseline.attempts} | {assisted.attempts} |",
        f"| test runs | {baseline.test_runs} | {assisted.test_runs} |",
        f"| coding tokens estimate | {baseline.coding_tokens} | {assisted.coding_tokens} |",
        f"| eval tokens estimate | {baseline.eval_tokens} | {assisted.eval_tokens} |",
        f"| total tokens estimate | {baseline.total_tokens} | {assisted.total_tokens} |",
        "",
        "## Transcripts",
        f"- Baseline: `{baseline.transcript}`",
        f"- Eval-assisted: `{assisted.transcript}`",
        "",
        "## Interpretation",
        _interpretation(baseline, assisted),
        "",
    ])


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate for CLI transcripts."""
    return max(0, (len(text or "") + 3) // 4)


def _materialize_repo(task: dict, repo_dir: Path) -> None:
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True)
    for rel, content in (task.get("files") or {}).items():
        path = repo_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _run_agent(
    agent_cmd: str,
    *,
    task_path: Path,
    repo_dir: Path,
    mode: str,
    attempt: int,
    hint_file: Path,
    transcript_file: Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    env = {
        **dict(os.environ),
        "LOOP_AUDITOR_TASK_FILE": str(task_path),
        "LOOP_AUDITOR_REPO": str(repo_dir),
        "LOOP_AUDITOR_MODE": mode,
        "LOOP_AUDITOR_ATTEMPT": str(attempt),
        "LOOP_AUDITOR_HINT_FILE": str(hint_file),
        "LOOP_AUDITOR_TRANSCRIPT_FILE": str(transcript_file),
    }
    return subprocess.run(
        _expand_command(agent_cmd),
        cwd=repo_dir,
        env=env,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _run_tests(task: dict, repo_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    command = task.get("test_command") or [sys.executable, "-m", "unittest", "discover"]
    if isinstance(command, str):
        command = command.replace("{python}", sys.executable)
        return subprocess.run(
            command, cwd=repo_dir, shell=True, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    command = [sys.executable if part == "{python}" else str(part) for part in command]
    return subprocess.run(
        command, cwd=repo_dir, text=True, capture_output=True,
        timeout=timeout, check=False,
    )


def _run_eval_agent(
    eval_agent_cmd: "str | None",
    *,
    task: dict,
    task_path: Path,
    repo_dir: Path,
    logs_dir: Path,
    latest_test_output: str,
    timeout: int,
) -> str:
    if not eval_agent_cmd:
        return json.dumps(_builtin_eval_agent(task, repo_dir, latest_test_output), indent=2)
    context_file = logs_dir / "eval_context.md"
    context_file.write_text(_eval_context(task, repo_dir, latest_test_output))
    env = {
        **dict(os.environ),
        "LOOP_AUDITOR_TASK_FILE": str(task_path),
        "LOOP_AUDITOR_REPO": str(repo_dir),
        "LOOP_AUDITOR_EVAL_CONTEXT": str(context_file),
    }
    result = subprocess.run(
        _expand_command(eval_agent_cmd),
        cwd=repo_dir,
        env=env,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return _combined_output(result)


def _expand_command(command: str) -> str:
    package_dir = Path(__file__).resolve().parent
    return (
        command
        .replace("{python}", sys.executable)
        .replace("{package}", str(package_dir))
    )


def _builtin_eval_agent(task: dict, repo_dir: Path, latest_test_output: str) -> dict:
    """Deterministic demo evaluator; real eval-agent CLIs plug in via --eval-agent."""
    files = sorted(str(p.relative_to(repo_dir)) for p in repo_dir.rglob("*") if p.is_file())
    duration_path = repo_dir / "src" / "duration.py"
    if "parse_duration" in latest_test_output and duration_path.exists():
        diagnosis = (
            "The failing tests exercise src/duration.py::parse_duration, but the "
            "coding agent has not corrected that implementation."
        )
        action = (
            "Inspect src/duration.py and update parse_duration to accumulate all "
            "number+unit pairs such as 1h30m before rerunning tests."
        )
        root = "src/duration.py"
    else:
        diagnosis = "The tests still fail after the coding-agent attempt."
        action = "Use the latest test output to target the failing function before making more edits."
        root = None
    return {
        "root_cause_file": root,
        "failure_type": "wrong_file_or_failed_test_loop",
        "diagnosis": diagnosis,
        "evidence": [
            "latest tests failed",
            "repo files visible to evaluator: " + ", ".join(files[:12]),
        ],
        "suggested_next_action": action,
    }


def _baseline_hint(latest_test_output: str) -> str:
    return (
        "Your previous attempt still failed. Review the current repo state and "
        "the latest test output, then try again without external evaluator help.\n\n"
        f"Latest test output:\n{latest_test_output}"
    )


def _assisted_hint(eval_text: str) -> str:
    return (
        "External evaluator diagnosis. Use this as guidance, but you are still "
        "responsible for making and testing the code changes.\n\n"
        f"{eval_text}"
    )


def _eval_context(task: dict, repo_dir: Path, latest_test_output: str) -> str:
    files = sorted(str(p.relative_to(repo_dir)) for p in repo_dir.rglob("*") if p.is_file())
    return "\n".join([
        "# Eval Context",
        "",
        "## Task",
        str(task.get("prompt", "")),
        "",
        "## Repo Files",
        "\n".join(f"- {path}" for path in files),
        "",
        "## Latest Test Output",
        _fenced(latest_test_output),
        "",
    ])


def _combined_output(result: subprocess.CompletedProcess) -> str:
    parts = []
    if result.stdout:
        parts.append(result.stdout.rstrip())
    if result.stderr:
        parts.append("[stderr]\n" + result.stderr.rstrip())
    if not parts:
        parts.append(f"[no output; exit_code={result.returncode}]")
    return "\n".join(parts)


def _summary_dict(summary: RunSummary) -> dict:
    return {
        "mode": summary.mode,
        "solved": summary.solved,
        "attempts": summary.attempts,
        "test_runs": summary.test_runs,
        "coding_tokens_estimate": summary.coding_tokens,
        "eval_tokens_estimate": summary.eval_tokens,
        "total_tokens_estimate": summary.total_tokens,
        "out_dir": str(summary.out_dir),
        "transcript": str(summary.transcript),
        "metrics": str(summary.metrics),
    }


def _interpretation(baseline: RunSummary, assisted: RunSummary) -> str:
    if assisted.solved and not baseline.solved:
        return "Eval-assisted recovery solved the task where the baseline self-prompt did not."
    if assisted.solved and baseline.solved:
        delta = baseline.total_tokens - assisted.total_tokens
        return f"Both runs solved the task; assisted token delta is {delta} estimated tokens."
    if not assisted.solved and baseline.solved:
        return "Baseline solved the task and eval-assisted did not; the intervention likely hurt or was ignored."
    return "Neither run solved the task; inspect transcripts for the next trigger/evaluator change."


def _fenced(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"
