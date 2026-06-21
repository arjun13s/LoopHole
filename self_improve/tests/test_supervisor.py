import json
from pathlib import Path

from self_improve import supervisor
from self_improve.__main__ import main


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "supervisor_demo"
TASK = FIXTURE_DIR / "task.json"
FAKE_AGENT = FIXTURE_DIR / "fake_coding_agent.py"


def _agent_cmd() -> str:
    rel = FAKE_AGENT.relative_to(Path(__file__).resolve().parents[1])
    return f"{{python}} {{package}}/{rel}"


def test_supervisor_pair_proves_assisted_recovery(tmp_path):
    result = supervisor.run_pair(TASK, _agent_cmd(), tmp_path / "pair", timeout=30)

    assert result["baseline"]["solved"] is False
    assert result["assisted"]["solved"] is True
    assert result["assisted"]["eval_tokens_estimate"] > 0
    side_by_side = Path(result["side_by_side"]).read_text()
    assert "Eval-assisted recovery solved the task" in side_by_side


def test_supervisor_cli_outputs_side_by_side(tmp_path, capsys):
    rc = main([
        "supervise",
        "--task", str(TASK),
        "--agent", _agent_cmd(),
        "--mode", "both",
        "--out-dir", str(tmp_path / "cli"),
        "--timeout", "30",
    ])

    assert rc == 0
    output = capsys.readouterr().out
    assert "supervision comparison complete" in output
    assert "baseline: solved=False" in output
    assert "assisted: solved=True" in output
    side_by_side = tmp_path / "cli" / "side_by_side.md"
    assert side_by_side.exists()
    assisted_metrics = json.loads((tmp_path / "cli" / "assisted" / "metrics.json").read_text())
    assert assisted_metrics["solved"] is True
