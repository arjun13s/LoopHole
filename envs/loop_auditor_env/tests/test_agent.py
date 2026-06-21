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


def test_eval_agent_has_no_token_id_request(monkeypatch):
    monkeypatch.setattr(hud.agents, "create_agent", lambda model, **kw: (model, kw))
    _model, kw = agent_mod.build_auditor_agent("m")
    assert kw == {}  # eval/inference rollout doesn't pay the token-id overhead
