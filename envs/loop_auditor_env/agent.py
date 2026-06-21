"""Auditor agent factory.

OWNER: Claude. ``create_agent`` (hud-python 0.6.x) routes the model through the
HUD gateway. For an open / trainable model, pass its gateway slug — see
``hud models list`` / ``hud models fork``. (For the CLI flow you don't need this:
``hud eval tasks.py claude --gateway`` picks the agent directly.)
"""

from __future__ import annotations

try:  # package (pytest) | flat (hud `env:env`)
    from . import config
except ImportError:
    import config


def build_auditor_agent(model: "str | None" = None):
    """Return a HUD gateway agent for ``model`` (default config.MODEL)."""
    from hud.agents import create_agent

    return create_agent(model or config.MODEL)
