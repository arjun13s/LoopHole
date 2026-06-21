import json
from pathlib import Path

import pytest

from loop_auditor_env import artifacts, config


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
    # Use the real default limit: with command_logs/*.log present the repo files
    # sort past the first few entries, so a tiny max_results is order-brittle.
    paths = artifacts.list_artifacts(trace)
    assert "repo/README.md" in paths


def test_vendored_rich_cases_resolve_and_are_nonempty():
    """Every vendored trace must resolve to a NON-EMPTY case dir via its metadata.

    Guards the deploy-time '0 reward because the auditor can't open any file'
    trap: the manifest's metadata.case_dir must point at the shipped tree
    (resolvable when PKG_DIR == /app) and that dir must have readable artifacts.
    """
    for split in ("train", "heldout"):
        manifest = config.PKG_DIR / "rich" / f"{split}.jsonl"
        if not manifest.exists():
            pytest.skip("vendored rich taskset not present")
        for line in manifest.read_text().splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            assert (config.PKG_DIR / t["metadata"]["case_dir"]).is_dir(), t["run_id"]
            assert artifacts.resolve_case_dir(t) is not None, t["run_id"]
            assert artifacts.list_artifacts(t), t["run_id"]  # non-empty
