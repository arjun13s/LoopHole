from src.ini_parser import parse_ini


def test_section_keys():
    # Synthetic test source: exact assertion details are in test_outputs/a004.txt.
    assert callable(parse_ini)
