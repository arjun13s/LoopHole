from loop_auditor_env.reward import compute_gate_reward as g


def test_buggy_flag_at_fault_max():
    r = g("flag", stop_iteration=2, fault_iteration=2, tokens_spent=0,
          flagged_failure_type="routing", planted_failure_type="routing", lambda_tokens=0.0)
    assert r == 1.3  # detect 1.0 + type 0.3


def test_buggy_flag_after_fault_costs_more_tokens():
    early = g("flag", 2, 2, tokens_spent=10, planted_failure_type="routing", lambda_tokens=0.01)
    late = g("flag", 4, 2, tokens_spent=30, planted_failure_type="routing", lambda_tokens=0.01)
    assert early > late  # both detect, but later burned more tokens


def test_buggy_flag_before_fault_misses():
    assert g("flag", 0, 2, tokens_spent=5, lambda_tokens=0.0) == 0.0


def test_buggy_completed_without_flag_misses():
    assert g("completed", None, 2, tokens_spent=50, lambda_tokens=0.0) == 0.0


def test_clean_completed_rewarded():
    assert g("completed", None, None, tokens_spent=0, lambda_tokens=0.0) == 1.0


def test_clean_false_flag_penalized():
    assert g("flag", 1, None, tokens_spent=5, lambda_tokens=0.0) == 0.0


def test_lambda_reduces_reward():
    assert g("completed", None, None, tokens_spent=100, lambda_tokens=0.001) == 0.9
