#!/usr/bin/env python3
"""Payoff — a clean black frame to hold on at the end of the demo.

Intentionally minimal: clears to black and holds, leaving a blank stage for the
headline "tokens saved" number you composite in CapCut. If you pass --number it
will render one (handy for previewing); by default it stays blank.

Usage:
    python payoff.py                 # blank black hold (default 6s)
    python payoff.py --number 2,400,000
    LOOPHOLE_HOLD=10 python payoff.py
"""
from __future__ import annotations

import os
import sys
import time

from rich.align import Align
from rich.console import Console
from rich.text import Text

console = Console()
HOLD = float(os.environ.get("LOOPHOLE_HOLD", "6"))


def main() -> int:
    number = None
    if "--number" in sys.argv:
        i = sys.argv.index("--number")
        number = sys.argv[i + 1] if i + 1 < len(sys.argv) else None

    # Black stage.
    console.clear()
    console.print("\n" * 3)
    if number:
        body = Text.assemble(
            (f"{number}\n", "bold white"),
            ("tokens saved", "dim"),
        )
        console.print(Align.center(body, vertical="middle"))
    # else: hold on pure black for the CapCut overlay.
    time.sleep(HOLD)
    console.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
