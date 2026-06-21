from __future__ import annotations


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        elif ch == ":":
            current.append(ch)
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens
