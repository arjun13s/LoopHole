# envs/loop_auditor_env/tests/test_tasks.py
import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")


def test_tasks_cover_audit_and_gate_per_trace():
    import importlib, sys
    sys.path.insert(0, "envs/loop_auditor_env")     # flat import like hud does
    tasks_mod = importlib.import_module("tasks")
    slugs = {t.slug for t in tasks_mod.tasks}
    assert any(s.startswith("audit__") for s in slugs)
    assert any(s.startswith("gate__") for s in slugs)
    assert len(tasks_mod.tasks) == len(tasks_mod.env_mod._SCENARIOS)
