#!/usr/bin/env python3
"""Act 2 — the real LoopHole rescue, live in the terminal.

A genuine run: real `claude` builds the note app, genuinely fails a hidden
acceptance test, the real LoopHole eval agent diagnoses the failure, and Claude
applies the fix until the suite is green. Nothing is faked.

    ./scripts/demo/loophole "build me a note taking app"

Env:
    LOOPHOLE_MODEL   claude model slug (default: Claude Code's default)
    LOOPHOLE_SPEED   typewriter speed multiplier (default 1.0; smaller = faster)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

console = Console()
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SKELETON = HERE / "note_app"
PYTEST = str((REPO_ROOT / ".venv/bin/python")) if (REPO_ROOT / ".venv/bin/python").exists() else "python3"
SPEED = float(os.environ.get("LOOPHOLE_SPEED", "1.0"))
MODEL = os.environ.get("LOOPHOLE_MODEL", "").strip()


def typeline(text: str, style: str = "bold white", prompt: str = "❯ ") -> None:
    console.print(Text(prompt, style="bold cyan"), end="")
    t = Text(style=style)
    for ch in text:
        t.append(ch)
        console.print(ch, style=style, end="")
        sys.stdout.flush()
        time.sleep(0.045 * SPEED)
    console.print()


def banner(label: str, desc: str, color: str) -> None:
    console.print()
    console.print(Rule(Text(f" {label} ", style=f"bold {color}"), style=color, align="left"))
    console.print(Text(f"  {desc}", style="dim"))
    console.print()


def claude(prompt: str, cwd: Path, *, read_only: bool) -> str:
    """Run real Claude headless in `cwd`; stream nothing fancy, return its text."""
    cmd = ["claude", "-p", prompt]
    if read_only:
        cmd += ["--allowedTools", "Read", "Grep", "Glob"]
    else:
        # acceptEdits auto-approves file writes headlessly without the blunt
        # --dangerously-skip-permissions. Set LOOPHOLE_CLAUDE_YOLO=1 only if a
        # headless edit ever stalls on a permission prompt in your sandbox.
        cmd += ["--permission-mode", "acceptEdits"]
        if os.environ.get("LOOPHOLE_CLAUDE_YOLO") == "1":
            cmd += ["--dangerously-skip-permissions"]
    if MODEL:
        cmd += ["--model", MODEL]
    with console.status("[bold]Claude is working…", spinner="dots"):
        proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        out = f"(claude exited {proc.returncode})\n{(proc.stderr or '').strip()}"
    return out


def run_tests(cwd: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [PYTEST, "-m", "pytest", "tests/", "-q"],
        cwd=str(cwd), text=True, capture_output=True,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="loophole_demo_"))
    shutil.copytree(SKELETON / "src", ws / "src")
    shutil.copytree(SKELETON / "tests", ws / "tests")
    return ws


def reveal_edge_test(ws: Path) -> None:
    shutil.copy(SKELETON / "edge" / "test_edge.py", ws / "tests" / "test_edge.py")


def main() -> int:
    user_prompt = " ".join(a for a in sys.argv[1:] if not a.startswith("-")) or "build me a note taking app"
    ws = setup_workspace()

    # Wipe the real shell invocation off-screen, then re-type a clean, branded
    # CLI command — this is the call-to-action viewers should remember.
    console.clear()
    console.print()
    # LOOPHOLE_NO_PROMPT=1 hides the command line (composite your own in post).
    if os.environ.get("LOOPHOLE_NO_PROMPT") != "1":
        cmd_label = os.environ.get("LOOPHOLE_CMD_LABEL") or f'loophole "{user_prompt}"'
        typeline(cmd_label)
        time.sleep(0.5 * SPEED)

    # 1) BUILD — real Claude implements the app to satisfy the visible tests.
    banner("BUILDING", "Claude is writing the note app…", "cyan")
    build_prompt = (
        "You're building a small note-taking app. The repo has src/notes.py with a "
        "NoteStore class (methods add and search) to implement, and tests in tests/. "
        "Implement src/notes.py so the tests in tests/ pass. Keep it minimal — implement "
        "exactly what the tests require, nothing more."
    )
    console.print(Text(claude(build_prompt, ws, read_only=False), style="grey85"))

    # 2) TEST — reveal the hidden acceptance test and run the full suite.
    reveal_edge_test(ws)
    banner("TESTING", "running the suite…", "yellow")
    ok, out = run_tests(ws)
    console.print(Text(out.rstrip(), style="grey70"))
    if ok:
        console.print(Panel("All tests passed on the first try (no rescue to show).", border_style="green"))
        return 0
    console.print(Text("✗ a test failed — the app is broken.", style="bold red"))

    # 3) LOOPHOLE — the eval agent diagnoses the real failure (read-only).
    banner("LOOPHOLE", "eval agent inspecting the failure…", "magenta")
    eval_prompt = (
        "You are LoopHole's eval agent supervising a coding agent. A test just failed. "
        "Here is the failing test output:\n\n" + out + "\n\n"
        "Read the relevant code and the failing test, then in 2-3 sentences state the root "
        "cause and the precise fix. Do NOT edit any files — diagnosis only."
    )
    diagnosis = claude(eval_prompt, ws, read_only=True)
    console.print(Panel(Text(diagnosis, style="white"), title="eval agent diagnosis",
                        border_style="magenta", padding=(1, 2)))

    # 4) FIX — Claude applies the eval agent's fix.
    banner("FIXING", "applying the eval agent's fix…", "cyan")
    fix_prompt = (
        "A test is failing in this repo. LoopHole's eval agent diagnosed it:\n\n"
        + diagnosis + "\n\nApply the fix to src/notes.py so all tests in tests/ pass. "
        "Keep the change minimal."
    )
    console.print(Text(claude(fix_prompt, ws, read_only=False), style="grey85"))

    # 5) RETEST — prove it's green.
    banner("TESTING", "re-running the suite…", "yellow")
    ok, out = run_tests(ws)
    console.print(Text(out.rstrip(), style="grey70"))
    console.print()
    if ok:
        console.print(Panel(
            Text.assemble(("✓ all tests passing\n", "bold green"),
                          ("LoopHole caught the failure and fixed it — autonomously.", "white")),
            border_style="green", padding=(1, 2)))
        return 0
    console.print(Panel("Still failing — inspect the workspace.", border_style="red"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
