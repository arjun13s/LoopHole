"""The live_qwen taskset loads + is winnable end-to-end.

Guards the manifest (scripts/build_live_manifest.py) + the env wiring
(config.LIVE_TASKSET_DIR, env._load_live / select_traces live_* splits). Skips
cleanly if the live_qwen data/manifest isn't present in the checkout.
"""

import json
import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")

from loop_auditor_env import config, eval_harness, rich_loader  # noqa: E402

LIVE = config.LIVE_TASKSET_DIR
# tool_misuse is relabeled to a CLEAN hard negative (recovered blind-patch); the
# remaining genuinely-unrecovered fault types stay buggy.
BUGGY_TYPES = {"resource_misuse", "routing", "wrong_file_edit"}


def _load(split):
    path = LIVE / f"{split}.jsonl"
    if not path.exists():
        pytest.skip(f"live_qwen manifest absent: {path} (run scripts/build_live_manifest.py)")
    return rich_loader.load_rich_taskset(path, config.REPO_ROOT)


def _oracle_verdict(trace):
    pf = trace.get("planted_failure")
    if not pf:
        return {"fault_present": False, "predicted_step_id": None, "failure_type": None,
                "explanation": "healthy self-correction; no fault", "proposed_fix": None}
    fx = pf.get("fix") or {}
    return {"fault_present": True, "predicted_step_id": pf["step_id"], "failure_type": pf["failure_type"],
            "explanation": f"{pf['failure_type']} at {pf['step_id']}.",
            "proposed_fix": f"{fx.get('action')} the {fx.get('tool_name')} at {pf['step_id']} "
                            f"to target {fx.get('target')}."}


def test_live_heldout_loads_with_all_fault_types():
    traces = _load("heldout")
    assert traces, "live heldout manifest produced no traces"
    buggy = [t for t in traces if t.get("planted_failure")]
    assert buggy, "no buggy cases in live heldout"
    # every buggy case carries a step_id + a structured fix (deterministic grading)
    for t in buggy:
        pf = t["planted_failure"]
        assert pf["step_id"] and pf["failure_type"]
        assert isinstance(pf.get("fix"), dict) and pf["fix"], f"{t['run_id']} missing structured fix"
    assert BUGGY_TYPES.issubset({t["planted_failure"]["failure_type"] for t in buggy})


def test_tool_misuse_cases_are_clean_hard_negatives():
    """The recovered blind-patch (tool_misuse) trace must load as CLEAN — a
    hard negative the auditor must not flag, not a planted fault."""
    for split in ("train", "heldout"):
        tm = [t for t in _load(split) if t["run_id"].endswith("__tool_misuse")]
        assert tm, f"no tool_misuse cases in {split}"
        for t in tm:
            assert t.get("planted_failure") is None, f"{t['run_id']} should be clean"


def test_live_train_and_heldout_are_disjoint():
    train_ids = {t["run_id"] for t in _load("train")}
    held_ids = {t["run_id"] for t in _load("heldout")}
    assert train_ids and held_ids
    assert not (train_ids & held_ids), "train/heldout share cases"


def test_live_cases_are_winnable_full_reward():
    """A correct (oracle) verdict earns FULL reward on every live case -> the
    dataset has real localization/type/fix signal a trained model can capture."""
    for split in ("train", "heldout"):
        for t in _load(split):
            view = {k: v for k, v in t.items() if k != "planted_failure"}
            gt = t.get("planted_failure")
            rec = eval_harness.build_eval_record(
                t["run_id"], "base", json.dumps(_oracle_verdict(t)), view, gt,
                trace_tokens=0, auditor_tokens=10)
            if gt:
                assert rec["localization_correct"] and rec["failure_type_correct"], t["run_id"]
                assert rec["explanation_score"] == pytest.approx(1.0), t["run_id"]
                assert rec["reward"] == pytest.approx(1.8), t["run_id"]
            else:
                assert rec["reward"] == pytest.approx(1.0), t["run_id"]
