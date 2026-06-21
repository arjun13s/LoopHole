from src.csv_utils import normalize_header


def test_symbols():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(normalize_header)
