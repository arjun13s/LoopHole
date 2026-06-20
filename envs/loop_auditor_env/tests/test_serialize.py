import json
from pathlib import Path

from loop_auditor_env.serialize import summarize_step, summarize_trace


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "trace.json"
ACTION_TYPES = {"reasoning", "tool_call", "tool_result", "message", "final"}
STATUSES = {"ok", "error", "timeout"}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def step_ids(trace: dict) -> list[str]:
    return [step["step_id"] for iteration in trace["iterations"] for step in iteration["steps"]]


def test_fixtures_are_valid_trace_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    failure_types = set(
        schema["$defs"]["PlantedFailure"]["properties"]["failure_type"]["enum"]
    )

    for path in sorted(FIXTURE_DIR.glob("*.json")):
        trace = json.loads(path.read_text())
        assert set(trace) <= {"run_id", "task", "model", "iterations", "planted_failure", "metadata"}
        assert isinstance(trace["run_id"], str)
        assert isinstance(trace["task"], str)
        assert isinstance(trace["iterations"], list)
        for iteration in trace["iterations"]:
            assert set(iteration) <= {"index", "thought", "steps", "metadata"}
            assert isinstance(iteration["index"], int)
            assert isinstance(iteration["steps"], list)
            for step in iteration["steps"]:
                assert set(step) <= {
                    "step_id",
                    "action_type",
                    "tool_name",
                    "input",
                    "output",
                    "status",
                    "tokens",
                    "metadata",
                }
                assert isinstance(step["step_id"], str)
                assert step["action_type"] in ACTION_TYPES
                assert step.get("status", "ok") in STATUSES
        planted_failure = trace["planted_failure"]
        if planted_failure is not None:
            assert set(planted_failure) == {"step_id", "failure_type", "description"}
            assert planted_failure["failure_type"] in failure_types
            assert planted_failure["step_id"] in step_ids(trace)


def test_summarize_trace_is_deterministic_and_excludes_ground_truth():
    trace = load_fixture("buggy_resource_misuse.json")

    assert summarize_trace(trace) == summarize_trace(trace)
    assert "planted_failure" not in summarize_trace(trace)
    assert "resource_misuse" not in summarize_trace(trace)


def test_summarize_trace_contains_all_step_ids():
    trace = load_fixture("buggy_routing.json")
    summary = summarize_trace(trace)

    for step_id in step_ids(trace):
        assert step_id in summary


def test_summarize_step_truncates_long_content():
    step = {
        "step_id": "long.step",
        "action_type": "final",
        "output": "x" * 300,
    }

    summary = summarize_step(step)

    assert summary.startswith("long.step: final")
    assert summary.endswith("...")
    assert len(summary) < 150
