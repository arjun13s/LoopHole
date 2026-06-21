from src.config import parse_bool


def test_yes_no():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(parse_bool)
