from src.string_utils import slugify


def test_basic_words():
    assert slugify("Hello World") == "hello-world"


def test_punctuation():
    assert slugify("Hello, world!") == "hello-world"


def test_repeated_separators():
    assert slugify("A  ---  B") == "a-b"


def test_edges():
    assert slugify("  hello  ") == "hello"


def test_empty():
    assert slugify("!!!") == ""
