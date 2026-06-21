from src.formatter import render_query
from src.tokenizer import tokenize


def test_render_query_final_output():
    assert render_query("status:open owner:me") == "status=open&owner=me"


def test_tokenizer_keeps_colon_as_separator():
    assert tokenize("status:open") == ["status", "open"]


def test_multiple_pairs():
    assert render_query("priority:high label:bug") == "priority=high&label=bug"
