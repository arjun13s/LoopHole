"""Tests for the HUD v6 audit env: the @env.template task + the served MCP capability.

Keyless — the judge runs in stub mode. Skipped entirely if hud isn't installed.
"""

import json
import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")  # no Anthropic key needed
pytest.importorskip("hud")  # env.py imports `hud`; skip when unavailable (e.g. py3.9)

from loop_auditor_env import config  # noqa: E402
from loop_auditor_env.env import _TRACES, audit_trace, env  # noqa: E402


def _a_buggy():
    return next(rid for rid, t in _TRACES.items() if t.get("planted_failure"))


def _a_clean():
    return next(rid for rid, t in _TRACES.items() if not t.get("planted_failure"))


class TestAuditTemplate:
    async def test_buggy_perfect_verdict_scores_above_one(self):
        rid = _a_buggy()
        gt = _TRACES[rid]["planted_failure"]
        gen = audit_trace.func(run_id=rid)
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
        gen = audit_trace.func(run_id=rid)
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
        gen = audit_trace.func(run_id=rid)
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
        gen = audit_trace.func(run_id=rid)
        await gen.asend(None)
        assert await gen.asend("not json at all") == 0.0


class TestTraceInspectorCapability:
    """The in-process MCP capability actually serves the inspection tools."""

    async def test_capability_serves_inspection_tools(self):
        from hud.capabilities.mcp import MCPClient

        await env.start()
        try:
            cap = env.capability("trace-inspector")
            assert cap.protocol.startswith("mcp")
            client = await MCPClient.connect(cap)
            try:
                names = sorted(t.name for t in await client.list_tools())
                assert names == ["get_iteration", "get_step", "get_trace_summary"]
            finally:
                await client.close()
        finally:
            await env.stop()
