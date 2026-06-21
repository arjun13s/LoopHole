#!/usr/bin/env python3
"""Act 1 — "the pain": a scripted montage of a naive coding agent melting down.

Theatrical by design. Renders a believable agentic build that grows confident,
then drowns in errors while an Anthropic bill climbs, the context window fills,
and time passes — ending in a red failure. Reproducible every take.

Usage:
    python act1_montage.py "build me a note taking app"
    LOOPHOLE_SPEED=0.5 python act1_montage.py "..."   # 2x faster (for retakes)
    python act1_montage.py --smoke "..."              # instant, for verification

Timing scales with env LOOPHOLE_SPEED (default 1.0; smaller = faster).
"""
from __future__ import annotations

import os
import sys
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
SPEED = float(os.environ.get("LOOPHOLE_SPEED", "1.0"))
SMOKE = "--smoke" in sys.argv
MODEL = "claude-opus-4-loop · autonomous"


def nap(seconds: float) -> None:
    if not SMOKE:
        time.sleep(seconds * SPEED)


# --- header: live cost / context / clock --------------------------------------
def header(cost: float, ctx: float, elapsed: int, *, danger: bool = False) -> Panel:
    mm, ss = divmod(elapsed, 60)
    filled = int(round(ctx / 100 * 24))
    bar_style = "red" if ctx >= 90 else "yellow" if ctx >= 65 else "green"
    bar = Text("▕") + Text("█" * filled, style=bar_style) + Text("░" * (24 - filled)) + Text("▏")
    ctx_label = Text(f" {ctx:>3.0f}%", style="bold red" if ctx >= 90 else "white")
    if ctx >= 98:
        ctx_label = Text("  CONTEXT FULL", style="bold white on red")

    t = Table.grid(expand=True, padding=(0, 2))
    t.add_column(justify="left"); t.add_column(justify="center"); t.add_column(justify="right")
    cost_style = "bold red" if cost >= 10 else "bold yellow"
    t.add_row(
        Text(f"💸 ${cost:,.2f}", style=cost_style),
        Text("🧠 ctx ") + bar + ctx_label,
        Text(f"⏱  {mm:02d}:{ss:02d}", style="bold red" if danger else "white"),
    )
    return Panel(t, title=Text(MODEL, style="dim"), border_style="red" if danger else "grey37")


def frame(log: list[Text], cost: float, ctx: float, elapsed: int, *, danger=False) -> Group:
    body = Group(*log[-16:])
    return Group(header(cost, ctx, elapsed, danger=danger), body)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--smoke"]
    prompt = args[0] if args else "build me a note taking app"

    log: list[Text] = []
    cost, ctx, elapsed = 0.0, 4.0, 0

    with Live(frame(log, cost, ctx, elapsed), console=console, refresh_per_second=24, screen=False) as live:
        # 1) the human prompt, typed
        typed = Text("❯ ", style="bold cyan")
        log.append(typed)
        for ch in prompt:
            typed.append(ch, style="bold white")
            live.update(frame(log, cost, ctx, elapsed))
            nap(0.045)
        nap(0.6)

        # 2) confident start
        confident = [
            ("🤖 planning project structure…", 0.18, 0.9),
            ("  ✓ scaffolding  src/App.tsx", 0.16, 1.2),
            ("  ✓ writing      src/NoteList.tsx", 0.16, 1.4),
            ("  ✓ writing      src/storage.ts", 0.16, 1.6),
            ("  ✓ installing   react, vite, tailwind, zustand…", 0.5, 3.1),
            ("  ✓ writing      tests/notes.test.ts", 0.16, 1.5),
        ]
        for msg, dt, dcost in confident:
            log.append(Text(msg, style="green"))
            cost += dcost; ctx += 7; elapsed += int(9 * dt)
            live.update(frame(log, cost, ctx, elapsed)); nap(dt)

        # 3) first crack
        nap(0.4)
        log.append(Text("  ⟳ running test suite…", style="cyan"))
        live.update(frame(log, cost, ctx, elapsed)); nap(0.7)
        errors = [
            "  ✗ TypeError: Cannot read properties of undefined (reading 'notes')",
            "  ↻ retrying (1/3)… re-reading 14 files into context",
            "  ✗ vitest: 6 failed, module 'zustand' resolved twice",
            "  ↻ retrying (2/3)… regenerating storage.ts from scratch",
            "  ✗ tsc: 23 type errors across 9 files",
            "  ↻ retrying (3/3)… widening edits to entire src/ tree",
            "  ✗ ENOSPC build cache · hot reload crashed",
        ]
        for i, msg in enumerate(errors):
            style = "yellow" if "↻" in msg else "red"
            log.append(Text(msg, style=style))
            cost += 2.3 + i * 0.9
            ctx += 9 + i * 1.5
            elapsed += 47 + i * 18
            danger = ctx >= 90
            live.update(frame(log, cost, min(ctx, 99), elapsed, danger=danger))
            nap(0.55)

        # 4) failed midway -> reverts to default
        nap(0.5)
        for msg in [
            "  ⚠ context window exhausted — dropping earlier files",
            "  ⚠ lost the plan; reverting to default scaffold",
            "  ✗ note saving broken · search returns nothing · 0 tests passing",
        ]:
            log.append(Text(msg, style="bold red"))
            cost += 3.4; ctx = 99; elapsed += 96
            live.update(frame(log, cost, ctx, elapsed, danger=True)); nap(0.7)

        # 5) the verdict
        nap(0.6)
        mm, ss = divmod(elapsed, 60)
        verdict = Panel(
            Text.assemble(
                ("BUILD FAILED\n\n", "bold red"),
                ("the agent burned ", "white"), (f"${cost:,.2f}", "bold red"),
                (" over ", "white"), (f"{mm}m {ss:02d}s", "bold red"),
                (" and shipped nothing.\n", "white"),
                ("context exhausted · reverted to a broken default · you start over", "dim"),
            ),
            border_style="red", title="❌", padding=(1, 4),
        )
        log.append(Text(""))
        live.update(Group(header(cost, 99, elapsed, danger=True), Group(*log[-12:]), verdict))
        nap(2.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
