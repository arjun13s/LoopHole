"""Auditor agent factory.

OWNER: Claude. Points a HUD agent at config.MODEL.

!!! VERIFY @ Step 0: the exact HUD agent class names / kwargs from the installed
hud SDK. Symbols below (OpenAIChatAgent, create_agent) are research-derived and
may differ. hud import is guarded so this module imports without hud installed.
"""

from __future__ import annotations

import os

from . import config


def build_auditor_agent(model: "str | None" = None):
    """Return a HUD agent for ``model`` (default config.MODEL).

    Heuristic:
      - a HF-style slug ("org/name") OR a set LOOP_AUDITOR_VLLM_URL -> an
        OpenAI-compatible agent against a vLLM endpoint;
      - otherwise treat ``model`` as a HUD-forked slug via create_agent.
    """
    model = model or config.MODEL
    vllm_url = os.environ.get("LOOP_AUDITOR_VLLM_URL")

    if vllm_url or "/" in model:
        from hud.agents import OpenAIChatAgent  # VERIFY name/location

        return OpenAIChatAgent(
            base_url=vllm_url or "http://localhost:8000/v1",
            api_key=os.environ.get("LOOP_AUDITOR_VLLM_KEY", "EMPTY"),
            model=model,
        )

    from hud.agents import create_agent  # VERIFY name/location

    return create_agent(model)
