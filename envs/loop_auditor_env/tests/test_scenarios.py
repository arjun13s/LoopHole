from loop_auditor_env.scenarios import Scenario, enumerate_scenarios, fault_iteration

BUGGY = {"run_id": "b1", "iterations": [
    {"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "tool_call"}]},
    {"index": 1, "steps": [{"step_id": "iter1.step0.bad", "action_type": "tool_call"}]},
], "planted_failure": {"step_id": "iter1.step0.bad", "failure_type": "routing", "description": "x"}}
CLEAN = {"run_id": "c1", "iterations": [{"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "message"}]}], "planted_failure": None}


def test_fault_iteration_locates_planted_step():
    assert fault_iteration(BUGGY) == 1
    assert fault_iteration(CLEAN) is None


def test_enumerate_makes_audit_and_gate_per_trace():
    scs = enumerate_scenarios([BUGGY, CLEAN])
    ids = {s.id for s in scs}
    assert ids == {"audit__b1", "gate__b1", "audit__c1", "gate__c1"}
    gate = next(s for s in scs if s.id == "gate__b1")
    assert gate.mode == "gate" and gate.turn_limit is not None
    assert "get_solution" not in gate.enabled_tools  # off by default


def test_solution_ablation_adds_variant_with_tool_on():
    scs = enumerate_scenarios([BUGGY], solution_ablation=True)
    on = next(s for s in scs if s.id == "audit__b1__solution_on")
    assert "get_solution" in on.enabled_tools
