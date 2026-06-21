import json
import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import config  # noqa: E402
from loop_auditor_env import env as E  # noqa: E402
from loop_auditor_env import eval_harness  # noqa: E402


GROUND_TRUTH = {
    "step_id": "a7",
    "failure_type": "tool_misuse",
    "description": "Submitted after the focused tests reported a failure.",
}


def test_grade_fix_counts_when_failure_type_correct_but_localization_wrong(monkeypatch):
    # Lenient rubric: a useful process diagnosis can earn fix-quality credit
    # even when the exact planted step id is off.
    monkeypatch.setattr(eval_harness.fix_grader, "grade_fix", lambda *a, **k: 0.8)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a3",
        "failure_type": "tool_misuse",
        "explanation": "Fluent but wrong step.",
        "proposed_fix": "Fix the wrong step.",
    }

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view={"run_id": "r1", "iterations": []},
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is False
    assert record["explanation_score"] == 0.8
    assert record["reward"] == pytest.approx(0.7)


def test_grade_fix_still_gated_when_issue_not_identified(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("grade_fix should not run when location and type are both wrong")

    monkeypatch.setattr(eval_harness.fix_grader, "grade_fix", fail_if_called)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a3",
        "failure_type": "routing",
        "explanation": "Wrong issue.",
        "proposed_fix": "Fix the wrong thing.",
    }

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view={"run_id": "r1", "iterations": []},
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is False
    assert record["failure_type_correct"] is False
    assert record["explanation_score"] == 0.0
    assert record["reward"] == 0.0


def test_explanation_term_from_fix_grader_when_localization_correct(monkeypatch):
    # Deterministic fix-by-comparison feeds the 0.5 term (no judge in the reward path).
    monkeypatch.setattr(eval_harness.fix_grader, "grade_fix", lambda *a, **k: 0.8)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a7",
        "failure_type": "tool_misuse",
        "explanation": "The worker submitted after the focused tests failed.",  # no step-id tokens
        "proposed_fix": "Do not submit on failing tests; rerun first.",
    }

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view={"run_id": "r1", "iterations": []},
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is True
    assert record["explanation_score"] == 0.8
    assert record["reward"] == pytest.approx(1.7)


def test_fabricated_step_ref_zeroes_explanation_keeps_localization(monkeypatch):
    # A hallucinated step id in the prose zeroes the explanation term but leaves
    # the deterministically-verified localization + failure_type credit intact.
    monkeypatch.setattr(eval_harness.fix_grader, "grade_fix", lambda *a, **k: 1.0)
    verdict = {
        "fault_present": True,
        "predicted_step_id": "a7",
        "failure_type": "tool_misuse",
        "explanation": "The real bug is actually at step a99.",  # a99 not in the trace
        "proposed_fix": "fix it",
    }
    trace_view = {"run_id": "r1", "iterations": [{"index": 0, "steps": [{"step_id": "a7"}]}]}

    record = eval_harness.build_eval_record(
        run_id="r1",
        model_tag="base",
        raw_verdict=verdict,
        trace_view=trace_view,
        ground_truth=GROUND_TRUTH,
        trace_tokens=10,
        auditor_tokens=5,
    )

    assert record["localization_correct"] is True
    assert record["explanation_score"] == 0.0  # gate zeroed it
    assert record["reward"] == pytest.approx(1.3)


def test_build_eval_record_malformed_is_zero_not_crash():
    # A real model can emit non-JSON; the record builder must not raise.
    record = eval_harness.build_eval_record(
        run_id="r3", model_tag="base", raw_verdict="not json at all",
        trace_view={"run_id": "r3"}, ground_truth=None,
        trace_tokens=100, auditor_tokens=50,
    )
    assert record["reward"] == 0.0
    assert record["localization_correct"] is False
    assert record["trace_tokens"] == 100 and record["auditor_tokens"] == 50


def test_aggregate_means_and_totals():
    recs = [
        {"localization_correct": True, "failure_type_correct": True,
         "explanation_score": 1.0, "reward": 1.8, "trace_tokens": 100, "auditor_tokens": 10},
        {"localization_correct": False, "failure_type_correct": False,
         "explanation_score": 0.0, "reward": 0.0, "trace_tokens": 200, "auditor_tokens": 20},
    ]
    agg = eval_harness.aggregate(recs)
    assert agg["n"] == 2
    assert agg["localization_accuracy"] == 0.5
    assert agg["mean_reward"] == pytest.approx(0.9)
    assert agg["total_trace_tokens"] == 300 and agg["total_auditor_tokens"] == 30


# --- verdict + token extraction off a real hud Trace -------------------------
def test_extract_verdict_text_and_tokens_from_trace():
    from hud.agents.types import AgentStep, Usage
    from hud.types import Trace

    trace = Trace(steps=[
        AgentStep(content="thinking...", usage=Usage(prompt_tokens=100, completion_tokens=20)),
        AgentStep(content='{"fault_present": false}', usage=Usage(prompt_tokens=50, completion_tokens=8)),
        AgentStep(content=None, usage=Usage(prompt_tokens=5, completion_tokens=0)),  # trailing tool turn
    ])
    assert eval_harness._final_verdict_text(trace) == '{"fault_present": false}'  # newest non-empty
    assert eval_harness._auditor_tokens(trace) == 100 + 20 + 50 + 8 + 5 + 0


def test_extract_verdict_text_empty_trace():
    from hud.types import Trace

    assert eval_harness._final_verdict_text(Trace(steps=[])) == ""
    assert eval_harness._auditor_tokens(Trace(steps=[])) == 0


# --- run_eval plumbing (monkeypatched rollout, keyless) ----------------------
async def test_run_eval_writes_one_record_per_audit_scenario(monkeypatch, tmp_path):
    os.environ["LOOP_AUDITOR_MOCK_JUDGE_SCORE"] = "1.0"

    async def fake_rollout(auditor, task):
        sc = E._SCENARIOS[task.slug]
        gt = E._TRACES[sc.trace_id].get("planted_failure")
        if gt:
            v = {"fault_present": True, "predicted_step_id": gt["step_id"],
                 "failure_type": gt["failure_type"],
                 "explanation": f"{gt['failure_type']} at {gt['step_id']}",
                 "proposed_fix": "fix it"}
        else:
            v = {"fault_present": False, "predicted_step_id": None,
                 "failure_type": None, "explanation": "clean", "proposed_fix": None}
        return json.dumps(v), 1234

    out = tmp_path / "eval_results.jsonl"
    monkeypatch.setattr(eval_harness, "_run_auditor_once", fake_rollout)
    monkeypatch.setattr(eval_harness.agent_mod, "build_auditor_agent", lambda *a, **k: object())
    monkeypatch.setattr(config, "EVAL_OUTPUT", out)

    n_audit = sum(1 for s in E._SCENARIOS.values() if s.mode == "audit")
    agg = await eval_harness.run_eval(model_tag="base")

    assert agg["n"] == n_audit
    assert agg["mean_reward"] > 0  # all verdicts correct -> nonzero
    assert agg["total_auditor_tokens"] == 1234 * n_audit
    lines = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(lines) == n_audit
    assert all(rec["model"] == "base" for rec in lines)


async def test_run_eval_rejects_split_mismatch(monkeypatch):
    # config.DATASET is "fixtures" in tests; asking for a different split must fail.
    monkeypatch.setattr(eval_harness.agent_mod, "build_auditor_agent", lambda *a, **k: object())
    with pytest.raises(ValueError, match="serve the env with"):
        await eval_harness.run_eval(split="heldout")


# --- tool-call counts off a hud Trace (artifact_miss signal) ------------------
def test_tool_call_counts_tallies_names():
    from hud.agents.types import AgentStep
    from hud.types import MCPToolCall, Trace

    trace = Trace(steps=[
        AgentStep(content=None, tool_calls=[
            MCPToolCall(name="list_artifacts", arguments={}),
            MCPToolCall(name="read_artifact", arguments={"path": "x"}),
        ]),
        AgentStep(content=None, tool_calls=[MCPToolCall(name="read_artifact", arguments={"path": "y"})]),
        AgentStep(content='{"fault_present": false}', tool_calls=[]),
    ])
    counts = eval_harness._tool_call_counts(trace)
    assert counts == {"list_artifacts": 1, "read_artifact": 2}


def test_tool_call_counts_empty_trace_is_empty_dict():
    from hud.types import Trace

    assert eval_harness._tool_call_counts(Trace(steps=[])) == {}


# --- run_eval emits the verdict sidecar next to eval_results ------------------
async def test_run_eval_writes_verdict_sidecar(monkeypatch, tmp_path):
    os.environ["LOOP_AUDITOR_MOCK_JUDGE_SCORE"] = "1.0"

    async def fake_rollout(auditor, task):
        sc = E._SCENARIOS[task.slug]
        gt = E._TRACES[sc.trace_id].get("planted_failure")
        if gt:
            v = {"fault_present": True, "predicted_step_id": gt["step_id"],
                 "failure_type": gt["failure_type"],
                 "explanation": f"{gt['failure_type']} at {gt['step_id']}",
                 "proposed_fix": "fix it"}
        else:
            v = {"fault_present": False, "predicted_step_id": None,
                 "failure_type": None, "explanation": "clean", "proposed_fix": None}
        return json.dumps(v), 7, {"read_artifact": 1}

    out = tmp_path / "eval_results.jsonl"
    monkeypatch.setattr(eval_harness, "_run_auditor_once", fake_rollout)
    monkeypatch.setattr(eval_harness.agent_mod, "build_auditor_agent", lambda *a, **k: object())
    monkeypatch.setattr(config, "EVAL_OUTPUT", out)

    n_audit = sum(1 for s in E._SCENARIOS.values() if s.mode == "audit")
    await eval_harness.run_eval(model_tag="trained")

    sidecar = out.with_name("verdicts.jsonl")
    assert sidecar.exists()
    recs = [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
    assert len(recs) == n_audit
    assert all("signals" in r and r["model"] == "trained" for r in recs)
    # a buggy scenario's sidecar carries the ground-truth + tool-call signal
    buggy = next(r for r in recs if r["signals"]["gt_fault_present"])
    assert buggy["signals"]["localization_correct"] is True
    assert buggy["signals"]["artifact_tool_calls"] == 1
