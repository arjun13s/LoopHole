"""Pure per-group reward-spread helper for the H4 GRPO gate."""

import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")  # train.py imports env -> hud

from loop_auditor_env import train  # noqa: E402


def test_spreads_by_group_is_per_key():
    s = train.spreads_by_group([("a", 0.0), ("a", 1.0), ("b", 0.5), ("b", 0.5)])
    assert s == {"a": 1.0, "b": 0.0}  # GRPO advantage is within-group


def test_spreads_by_group_drops_none():
    s = train.spreads_by_group([("a", None), ("a", 0.4), ("a", 0.9)])
    assert s["a"] == pytest.approx(0.5)


def test_spreads_by_group_empty():
    assert train.spreads_by_group([]) == {}
