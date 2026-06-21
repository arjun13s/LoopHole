"""A tiny in-memory note store for the demo app.

Implement the two methods so the tests in tests/ pass. Keep it minimal.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Note:
    id: int
    title: str
    body: str = ""


class NoteStore:
    def __init__(self) -> None:
        self._notes: list[Note] = []
        self._next_id = 1

    def add(self, title: str, body: str = "") -> int:
        """Add a note and return its id."""
        raise NotImplementedError

    def search(self, query: str) -> list[Note]:
        """Return the notes whose title matches the query."""
        raise NotImplementedError
