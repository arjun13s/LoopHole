from __future__ import annotations


def parse(tokens: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(tokens):
        pairs.append((tokens[i], tokens[i + 1]))
        i += 2
    return pairs
