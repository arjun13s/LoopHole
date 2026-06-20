"""Auditor agent factory.

OWNER: Claude. Points a HUD agent at config.MODEL (open-source, e.g. via
OpenAIChatAgent->vLLM, or create_agent on a HUD-forked slug).
"""

from __future__ import annotations

from . import config


def build_auditor_agent(model: "str | None" = None):
    """Return a HUD agent for ``model`` (default config.MODEL)."""
    raise NotImplementedError
