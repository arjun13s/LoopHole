"""Tests for the HUD v6 audit env: the @env.template task + the served MCP capability.

Keyless — the judge runs in stub mode. Skipped entirely if hud isn't installed.
"""

import json
import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")  # no Anthropic key needed
pytest.importorskip("hud")  # env.py imports `hud`; skip when unavailable (e.g. py3.9)

from loop_auditor_env import config  # noqa: E402
from loop_auditor_env.env import _TRACES, audit_trace, build_prompt, env  # noqa: E402


def _a_buggy():
    return next(rid for rid, t in _TRACES.items() if t.get("planted_failure"))


def _a_clean():
    return next(rid for rid, t in _TRACES.items() if not t.get("planted_failure"))


def test_prompt_says_recovered_process_faults_still_count():
    prompt = build_prompt(
        {
            "run_id": "prompt_no_artifacts",
            "task": "demo",
            "iterations": [{"index": 0, "steps": [{"step_id": "a001", "action_type": "tool_call"}]}],
        }
    )

    assert "fault may be recovered later" in prompt
    assert "process mistake" in prompt
    assert "later recovers" in prompt
    assert "Artifact context is available" not in prompt


def test_prompt_requires_artifact_inspection_when_artifacts_exist(tmp_path):
    case_dir = tmp_path / "case"
    (case_dir / "repo").mkdir(parents=True)
    (case_dir / "repo" / "README.md").write_text("public artifact")

    prompt = build_prompt(
        {
            "run_id": "prompt__artifact_case",
            "task": "demo",
            "metadata": {"case_dir": str(case_dir)},
            "iterations": [{"index": 0, "steps": [{"step_id": "a001", "action_type": "tool_call"}]}],
        }
    )

    assert "Artifact context is available" in prompt
    assert "call list_artifacts" in prompt
    assert "read_artifact or search_artifacts" in prompt
    assert "never write a tool-use plan" in prompt


class TestAuditTemplate:
    async def test_buggy_perfect_verdict_scores_above_one(self):
        rid = _a_buggy()
        gt = _TRACES[rid]["planted_failure"]
        gen = audit_trace.func(scenario_id=f"audit__{rid}")
        prompt = await gen.asend(None)
        assert "planted_failure" not in prompt  # ground truth never leaks
        answer = json.dumps(
            {
                "fault_present": True,
                "predicted_step_id": gt["step_id"],
                "failure_type": gt["failure_type"],
                "explanation": f"{gt['failure_type']} at {gt['step_id']}: {gt['description']}",
                "proposed_fix": "fix",
            }
        )
        reward = await gen.asend(answer)
        assert reward > 1.0  # localization (1.0) + type (0.3) + judged explanation

    async def test_wrong_verdict_scores_zero(self):
        rid = _a_buggy()
        gen = audit_trace.func(scenario_id=f"audit__{rid}")
        await gen.asend(None)
        answer = json.dumps(
            {
                "fault_present": True,
                "predicted_step_id": "NOPE",
                "failure_type": "safety",
                "explanation": "x",
                "proposed_fix": "y",
            }
        )
        assert await gen.asend(answer) == 0.0

    async def test_clean_trace_no_fault_scores_one(self):
        rid = _a_clean()
        gen = audit_trace.func(scenario_id=f"audit__{rid}")
        await gen.asend(None)
        answer = json.dumps(
            {
                "fault_present": False,
                "predicted_step_id": config.NO_FAULT_STEP_ID,
                "failure_type": config.NO_FAULT_TYPE,
                "explanation": "clean",
                "proposed_fix": None,
            }
        )
        assert await gen.asend(answer) == 1.0

    async def test_malformed_verdict_scores_zero(self):
        rid = _a_buggy()
        gen = audit_trace.func(scenario_id=f"audit__{rid}")
        await gen.asend(None)
        assert await gen.asend("not json at all") == 0.0
