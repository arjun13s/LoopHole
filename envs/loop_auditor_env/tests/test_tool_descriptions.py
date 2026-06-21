"""Regression guard: every served MCP tool must expose a non-empty description.

A real agent's MCP client rejects description-less tools ("requires a description
and inputSchema"), which silently breaks every rollout while unit tests that only
list tool *names* still pass. This catches that class of bug.
"""

import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import env as E  # noqa: E402


async def test_all_served_tools_have_descriptions():
    from hud.capabilities.mcp import MCPClient

    await E.env.start()
    try:
        client = await MCPClient.connect(E.env.capability("trace-inspector"))
        try:
            tools = await client.list_tools()
            assert len(tools) == 13
            missing = [t.name for t in tools if not (getattr(t, "description", "") or "").strip()]
            assert not missing, f"tools missing descriptions: {missing}"
        finally:
            await client.close()
    finally:
        await E.env.stop()
