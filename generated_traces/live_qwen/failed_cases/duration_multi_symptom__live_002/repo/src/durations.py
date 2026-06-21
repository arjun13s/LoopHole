from __future__ import annotations

import re


_TOKEN_RE = re.compile(r"(\d+)([m])")


def parse_duration(text: str) -> int:
    total = 0
    consumed = ""
    for value, unit in _TOKEN_RE.findall(text):
        consumed += value + unit
        amount = int(value)
        if unit == "h":
            total += amount * 60
        elif unit == "m":
            total += amount
    if consumed != text:
        raise ValueError(f"invalid duration: {text}")
    return total
