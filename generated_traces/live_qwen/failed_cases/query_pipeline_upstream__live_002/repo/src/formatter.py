from __future__ import annotations

from .parser import parse
from .tokenizer import tokenize


def render_query(text: str) -> str:
    pairs = parse(tokenize(text))
    return "&".join(f"{key}={value}" for key, value in pairs)
