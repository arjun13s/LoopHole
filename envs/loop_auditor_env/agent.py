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


_ANTHROPIC_HINTS = ("claude", "sonnet", "opus", "haiku", "anthropic")


def _completion_controls(model: str, *, trainable: bool) -> dict:
    """Build the create_agent kwargs that cap output (and tame reasoning).

    The verdict is a tiny JSON object; an uncapped <think> ramble can run past
    the server's output budget before the closing brace, so the answer parses to
    nothing and scores 0. We therefore always set an output cap.

    Routing matters: ``OpenAIChatConfig`` (the trainable Qwen fork) has NO
    max_tokens field — the cap and the Qwen ``enable_thinking`` switch must ride
    inside ``completion_kwargs`` (forwarded to chat.completions.create). Claude
    configs instead take a top-level ``max_tokens`` and have no thinking switch.
    """
    if any(h in (model or "").lower() for h in _ANTHROPIC_HINTS):
        return {"max_tokens": config.AUDITOR_MAX_TOKENS}

    extra_body: dict = {}
    if trainable:
        # token ids + per-token logprobs, required for forward_backward
        extra_body["return_token_ids"] = True
    if not config.AUDITOR_THINK:
        # vLLM/SGLang Qwen3 switch: emit the verdict directly, no <think> block
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}

    completion_kwargs: dict = {"max_tokens": config.AUDITOR_MAX_TOKENS}
    if extra_body:
        completion_kwargs["extra_body"] = extra_body
    return {"completion_kwargs": completion_kwargs}


def build_auditor_agent(model: "str | None" = None, *, trainable: bool = False):
    """Return a HUD gateway agent for ``model`` (default config.MODEL).

    Always caps the auditor's output so a runaway reasoning ramble can't truncate
    the JSON verdict (see ``_completion_controls`` / config.AUDITOR_MAX_TOKENS).

    ``trainable=True`` also asks the gateway for token ids + per-token logprobs
    (``extra_body.return_token_ids``, which also turns on ``logprobs``), so the
    rollout records ``AgentStep.sample`` token data. That is REQUIRED for
    ``TrainingClient.forward_backward`` — without it the trajectories carry no
    trainable turns and the training step 400s ("no trainable turns in the
    provided inputs"). Only meaningful for a trainable openai_compatible model;
    leave False for eval/inference.
    """
    from hud.agents import create_agent

    model = model or config.MODEL
    return create_agent(model, **_completion_controls(model, trainable=trainable))
