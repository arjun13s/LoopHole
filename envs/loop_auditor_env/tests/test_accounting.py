from loop_auditor_env.accounting import TokenMeter, estimate_tokens


def test_estimate_tokens():
    assert estimate_tokens(None) == 0
    assert estimate_tokens("") == 1          # min 1 for non-None
    assert estimate_tokens("a" * 40) == 10   # len//4
    assert estimate_tokens({"a": 1}) >= 1     # non-str is json-stringified


def test_charge_accumulates_and_breaks_down():
    m = TokenMeter()
    m.charge(10, "trace")
    m.charge(5, "tool")
    m.charge(3, "trace")
    assert m.spent == 18
    assert m.breakdown == {"trace": 13, "tool": 5}


def test_charge_floors_negative_and_returns_spent():
    m = TokenMeter()
    assert m.charge(-7, "x") == 0
    assert m.spent == 0


def test_remaining():
    assert TokenMeter().remaining is None
    m = TokenMeter(budget=100)
    m.charge(30, "x")
    assert m.remaining == 70
    m.charge(1000, "x")
    assert m.remaining == 0
