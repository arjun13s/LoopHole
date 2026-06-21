"""The hidden acceptance test — NOT present while Claude builds.

The orchestrator copies this into tests/ only when judging, so Claude's first
implementation (written to satisfy the visible tests) misses it. This is the
edge case the LoopHole eval agent catches: search must be case-insensitive.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.notes import NoteStore


def test_search_is_case_insensitive():
    s = NoteStore()
    s.add("Groceries", "milk, eggs")
    assert [n.title for n in s.search("groceries")] == ["Groceries"], (
        "a user searching 'groceries' should still find the note titled 'Groceries'"
    )
