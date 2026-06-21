"""build_auditor_agent forwards the trainable token-id request correctly."""

import os

import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

import hud.agents  # noqa: E402

from loop_auditor_env import agent as agent_mod  # noqa: E402


def test_trainable_requests_token_ids(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    model, kw = agent_mod.build_auditor_agent("m", trainable=True)
    assert model == "m"
    assert kw["completion_kwargs"]["extra_body"]["return_token_ids"] is True


def test_eval_agent_is_capped_without_token_ids(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    _model, kw = agent_mod.build_auditor_agent("m")
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] > 0  # always capped so the verdict can't get truncated
    # eval/inference rollout doesn't pay the token-id overhead
    assert "return_token_ids" not in cc.get("extra_body", {})


def test_no_think_disables_reasoning_by_default(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_THINK", False)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_MAX_TOKENS", 512)
    _model, kw = agent_mod.build_auditor_agent("qwen-fork")
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] == 512
    assert cc["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_think_mode_keeps_reasoning(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_THINK", True)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_MAX_TOKENS", 2048)
    _model, kw = agent_mod.build_auditor_agent("qwen-fork")
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] == 2048
    assert "chat_template_kwargs" not in cc.get("extra_body", {})


def test_anthropic_model_uses_top_level_max_tokens(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_MAX_TOKENS", 777)
    _model, kw = agent_mod.build_auditor_agent("claude-sonnet-4-6")
    # ClaudeConfig has a real max_tokens field and no completion_kwargs/extra_body
    assert kw == {"max_tokens": 777}
