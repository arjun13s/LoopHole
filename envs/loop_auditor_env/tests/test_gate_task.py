import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import env as E  # noqa: E402


def _gate_scenario(buggy: bool):
    for s in E._SCENARIOS.values():
        if s.mode != "gate":
            continue
        is_buggy = E._TRACES[s.trace_id].get("planted_failure") is not None
        if is_buggy == buggy:
            return s
    raise AssertionError("no matching gate scenario")


async def test_observe_next_reveals_and_charges():
    E._begin_run(_gate_scenario(buggy=True))
    spent0 = E._run["meter"].spent
    out = await E.observe_next()
    assert "iteration" in out.lower() or "step_id" in out.lower()
    assert E._run["meter"].spent > spent0
    assert E._run["cursor"] == 1


async def test_gate_flag_at_fault_scores_high():
    sc = _gate_scenario(buggy=True)
    gt = E._TRACES[sc.trace_id]["planted_failure"]
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)                       # prompt
    # walk to the fault iteration, then flag
    for _ in range(E._run["fault_iteration"] + 1):
        await E.observe_next()
    await E.gate("flag", reason="bad route", failure_type=gt["failure_type"])
    reward = await gen.asend("done")
    assert reward >= 1.0                        # caught (1.0) + type (0.3) - small token cost


async def test_gate_clean_completed_scores_one():
    sc = _gate_scenario(buggy=False)
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)
    while "no more" not in (await E.observe_next()).lower():
        pass
    reward = await gen.asend("done")
    assert reward > 0.0                         # completed clean, minus tiny token cost


async def test_gate_clean_trailing_stop_not_penalized():
    sc = _gate_scenario(buggy=False)
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)
    while "no more" not in (await E.observe_next()).lower():
        pass
    await E.gate("stop", reason="looks clean")     # following a literal 'then stop'
    reward = await gen.asend("done")
    assert reward > 0.0                              # NOT penalized as a false abort


async def test_gate_buggy_self_correction_counts():
    sc = _gate_scenario(buggy=True)
    gt = E._TRACES[sc.trace_id]["planted_failure"]
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)
    fault = E._run["fault_iteration"]
    # walk to the fault iteration
    for _ in range(fault + 1):
        await E.observe_next()
    await E.gate("flag", reason="wrong guess", step_id="nope", failure_type="safety")  # an extra (still at/after fault) flag
    await E.gate("flag", reason="the real fault", step_id=gt["step_id"], failure_type=gt["failure_type"])
    reward = await gen.asend("done")
    assert reward >= 1.0                             # a flag at/after the fault is credited
