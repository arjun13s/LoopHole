import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import env as E  # noqa: E402


async def test_capability_serves_all_ten_tools():
    from hud.capabilities.mcp import MCPClient
    await E.env.start()
    try:
        client = await MCPClient.connect(E.env.capability("trace-inspector"))
        try:
            names = sorted(t.name for t in await client.list_tools())
            assert names == sorted([
                "get_trace_summary", "get_iteration", "get_step", "search_steps",
                "get_errors", "get_step_io", "get_budget", "get_solution",
                "observe_next", "gate",
            ])
        finally:
            await client.close()
    finally:
        await E.env.stop()


async def test_get_budget_reflects_charges():
    sc = next(s for s in E._SCENARIOS.values() if s.mode == "audit")
    E._begin_run(sc)
    before = (await E.get_budget())
    await E.get_trace_summary()           # a read tool charges the meter
    after = (await E.get_budget())
    assert E._run["meter"].spent > 0
    assert "spent" in before and "spent" in after


async def test_get_solution_disabled_by_default_scenario():
    sc = next(s for s in E._SCENARIOS.values() if s.mode == "audit" and "solution" not in s.id)
    E._begin_run(sc)
    msg = await E.get_solution()
    assert "disabled" in msg.lower()
