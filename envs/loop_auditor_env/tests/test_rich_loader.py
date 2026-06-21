"""rich_loader normalizes Person 1's rich taskset into the env trace schema."""

import json

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
        assert t["metadata"]["case_dir"].startswith("generated_traces/rich_cases/")
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


def test_vendored_rich_present_and_normalized():
    # Guard: the deploy image ships these; regenerate with scripts/vendor_rich.py.
    for split, n in (("train", 40), ("heldout", 10)):
        path = config.PKG_DIR / "rich" / f"{split}.jsonl"
        assert path.exists(), "run scripts/vendor_rich.py and commit envs/loop_auditor_env/rich/"
        traces = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        assert len(traces) == n
        assert all({"run_id", "iterations", "planted_failure"} <= set(t) for t in traces)
