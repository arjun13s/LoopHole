import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.notes import NoteStore


def test_add_and_search_by_title():
    s = NoteStore()
    s.add("Groceries", "milk, eggs")
    s.add("Workout plan", "monday: legs")
    assert [n.title for n in s.search("Groceries")] == ["Groceries"]


def test_search_no_match_returns_empty():
    s = NoteStore()
    s.add("Groceries")
    assert s.search("vacation") == []
