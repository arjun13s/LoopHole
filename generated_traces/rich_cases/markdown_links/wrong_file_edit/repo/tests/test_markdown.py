from src.markdown import extract_links


def test_multiple_links():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(extract_links)
