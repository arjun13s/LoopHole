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


def build_auditor_agent(model: "str | None" = None, *, trainable: bool = False):
    """Return a HUD gateway agent for ``model`` (default config.MODEL).

    ``trainable=True`` asks the gateway for token ids + per-token logprobs
    (``extra_body.return_token_ids``, which also turns on ``logprobs``), so the
    rollout records ``AgentStep.sample`` token data. That is REQUIRED for
    ``TrainingClient.forward_backward`` — without it the trajectories carry no
    trainable turns and the training step 400s ("no trainable turns in the
    provided inputs"). Only meaningful for a trainable openai_compatible model;
    leave False for eval/inference.
    """
    from hud.agents import create_agent

    kwargs = {}
    if trainable:
        kwargs["completion_kwargs"] = {"extra_body": {"return_token_ids": True}}
    return create_agent(model or config.MODEL, **kwargs)
