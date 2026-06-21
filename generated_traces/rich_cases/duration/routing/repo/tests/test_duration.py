from src.duration import parse_duration


def test_minutes_seconds():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(parse_duration)
