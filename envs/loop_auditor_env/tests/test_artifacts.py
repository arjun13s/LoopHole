from pathlib import Path

from loop_auditor_env import artifacts


def _trace(tmp_path: Path) -> dict:
    case_dir = tmp_path / "case"
    (case_dir / "repo" / "src").mkdir(parents=True)
    (case_dir / "test_outputs").mkdir()
    (case_dir / "repo" / "README.md").write_text("# demo\n\nImportant task context.\n")
    (case_dir / "repo" / "src" / "mod.py").write_text("VALUE = 1\n")
    (case_dir / "test_outputs" / "a004.txt").write_text("1 failed, 2 passed\n")
    (case_dir / "AUDIT.md").write_text("fault_present: true\n")
    (case_dir / "ground_truth.json").write_text("{}\n")
    return {"run_id": "demo__routing", "metadata": {"case_dir": str(case_dir)}, "iterations": []}


def test_list_artifacts_exposes_public_context_only(tmp_path):
    trace = _trace(tmp_path)
    paths = artifacts.list_artifacts(trace)
    assert paths == [
        "repo/README.md",
        "repo/src/mod.py",
        "test_outputs/a004.txt",
    ]
    assert "AUDIT.md" not in paths
    assert "ground_truth.json" not in paths


def test_read_artifact_returns_truncated_content(tmp_path):
    trace = _trace(tmp_path)
    out = artifacts.read_artifact(trace, "repo/README.md", max_chars=6)
    assert out["ok"] is True
    assert out["path"] == "repo/README.md"
    assert out["content"] == "# demo"
    assert out["truncated"] is True


def test_read_artifact_rejects_traversal_and_hidden_labels(tmp_path):
    trace = _trace(tmp_path)
    assert artifacts.read_artifact(trace, "../secret.txt")["ok"] is False
    assert artifacts.read_artifact(trace, "AUDIT.md")["ok"] is False


def test_search_artifacts_returns_ordered_hits(tmp_path):
    trace = _trace(tmp_path)
    hits = artifacts.search_artifacts(trace, "failed")
    assert hits == [{"path": "test_outputs/a004.txt", "line": 1, "snippet": "1 failed, 2 passed"}]


def test_infers_local_rich_case_dir():
    trace = {"run_id": "ini_parser__routing", "iterations": []}
    paths = artifacts.list_artifacts(trace, max_results=5)
    assert "repo/README.md" in paths
