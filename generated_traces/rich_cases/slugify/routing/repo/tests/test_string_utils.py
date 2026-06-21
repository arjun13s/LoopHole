from src.string_utils import slugify


def test_punctuation():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(slugify)
