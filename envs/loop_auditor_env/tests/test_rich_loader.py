"""rich_loader normalizes Person 1's rich taskset into the env trace schema."""

from loop_auditor_env import config, rich_loader
from loop_auditor_env import verdict as V

_STEP_KEYS = {"step_id", "action_type", "tool_name", "input", "output", "status", "tokens"}


def _heldout():
    return rich_loader.load_rich_taskset(config.RICH_TASKSET_DIR / "heldout.jsonl", config.REPO_ROOT)


def test_load_rich_heldout_normalizes_to_env_schema():
    traces = _heldout()
    assert len(traces) == 10
    for t in traces:
        assert t["run_id"] and isinstance(t["iterations"], list) and t["iterations"]
        step = t["iterations"][0]["steps"][0]
        assert _STEP_KEYS <= set(step)
        assert t["iterations"][0]["index"] == 0


def test_buggy_planted_failure_carries_structured_fix():
    traces = _heldout()
    buggy = [t for t in traces if t["planted_failure"]]
    clean = [t for t in traces if not t["planted_failure"]]
    assert buggy and clean  # a real mix
    pf = buggy[0]["planted_failure"]
    assert pf["step_id"] and pf["failure_type"] in config.FAILURE_TYPES
    assert pf.get("fix") and pf["fix"].get("target")  # structured fix forwarded for grading
    sids = {st["step_id"] for it in buggy[0]["iterations"] for st in it["steps"]}
    assert pf["step_id"] in sids  # the faulty step exists in the normalized trace


def test_wrong_file_edit_is_valid_failure_type():
    assert "wrong_file_edit" in config.FAILURE_TYPES
    v = {
        "fault_present": True, "predicted_step_id": "a007",
        "failure_type": "wrong_file_edit", "explanation": "x", "proposed_fix": "y",
    }
    assert V.validate_verdict(v)["failure_type"] == "wrong_file_edit"
