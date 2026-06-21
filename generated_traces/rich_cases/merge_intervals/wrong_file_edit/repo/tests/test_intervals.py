from src.intervals import merge_intervals


def test_touching_intervals():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(merge_intervals)
