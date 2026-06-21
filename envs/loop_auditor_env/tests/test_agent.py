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


def test_eval_agent_uses_high_budget_without_token_ids(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_THINK", True)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_MAX_TOKENS", 4096)
    _model, kw = agent_mod.build_auditor_agent("m")
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] == 4096  # eval can spend more to avoid coding-agent escalation
    assert "chat_template_kwargs" not in cc.get("extra_body", {})
    # eval/inference rollout doesn't pay the token-id overhead
    assert "return_token_ids" not in cc.get("extra_body", {})


def test_train_profile_disables_reasoning_by_default(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_TRAIN_THINK", False)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_TRAIN_MAX_TOKENS", 512)
    _model, kw = agent_mod.build_auditor_agent("qwen-fork", trainable=True)
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] == 512
    assert cc["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_eval_profile_keeps_reasoning(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_THINK", True)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_MAX_TOKENS", 4096)
    _model, kw = agent_mod.build_auditor_agent("qwen-fork", profile="eval")
    cc = kw["completion_kwargs"]
    assert cc["max_tokens"] == 4096
    assert "chat_template_kwargs" not in cc.get("extra_body", {})


def test_anthropic_model_uses_top_level_max_tokens(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_MAX_TOKENS", 777)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_MAX_STEPS", 55)
    _model, kw = agent_mod.build_auditor_agent("claude-sonnet-4-6")
    # ClaudeConfig has real max_tokens/max_steps fields and no completion_kwargs/extra_body
    assert kw == {"max_tokens": 777, "max_steps": 55}


def test_profiles_set_a_generous_step_budget(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    monkeypatch.setattr(agent_mod.config, "AUDITOR_TRAIN_MAX_STEPS", 40)
    monkeypatch.setattr(agent_mod.config, "AUDITOR_EVAL_MAX_STEPS", 70)
    _m, train_kw = agent_mod.build_auditor_agent("qwen-fork", trainable=True)
    _m, eval_kw = agent_mod.build_auditor_agent("qwen-fork")
    assert train_kw["max_steps"] == 40  # cheaper ceiling for GRPO rollouts
    assert eval_kw["max_steps"] == 70   # generous for eval (gate needs ~2 calls/iter)
