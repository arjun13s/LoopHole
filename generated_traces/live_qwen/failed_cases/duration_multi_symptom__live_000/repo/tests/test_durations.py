import pytest

from src.durations import parse_duration
from src.formatting import format_minutes


def test_minutes_only():
    assert parse_duration("45m") == 45


def test_hours_only():
    assert parse_duration("2h") == 120


def test_combined_hours_and_minutes():
    assert parse_duration("1h30m") == 90


def test_formatting_round_trip_value():
    assert format_minutes(parse_duration("1h15m")) == "1h15m"


def test_invalid_suffix_rejected():
    with pytest.raises(ValueError):
        parse_duration("20x")
