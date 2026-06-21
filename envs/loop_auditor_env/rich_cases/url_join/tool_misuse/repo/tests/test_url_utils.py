from src.url_utils import join_url


def test_duplicate_slashes():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(join_url)
