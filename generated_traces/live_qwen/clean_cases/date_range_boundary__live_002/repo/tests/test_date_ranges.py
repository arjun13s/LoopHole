from datetime import date

import pytest

from src.date_ranges import days_between


def test_exclusive_range():
    assert days_between(date(2026, 1, 1), date(2026, 1, 4)) == 3


def test_inclusive_range_counts_both_boundaries():
    assert days_between(date(2026, 1, 1), date(2026, 1, 4), inclusive=True) == 4


def test_same_day_inclusive():
    assert days_between(date(2026, 1, 1), date(2026, 1, 1), inclusive=True) == 1


def test_reverse_range_rejected():
    with pytest.raises(ValueError):
        days_between(date(2026, 1, 4), date(2026, 1, 1))
