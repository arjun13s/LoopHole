import json
from pathlib import Path

from self_improve import analyzer
from self_improve.__main__ import main
from self_improve import mcp_server


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "improvement_cases.jsonl"


def _cases():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


def test_classify_matches_golden_fixture():
    for row in _cases():
        actual = analyzer.classify(row["eval_result"], row["sidecar"])
        expected = row["expect"]
        if expected is None:
            assert actual is None, row["id"]
            continue
        assert actual is not None, row["id"]
        for key in (
            "bucket",
            "fix_type",
            "recommended_fix_type",
            "confidence",
            "severity",
            "suggested_alias",
        ):
            assert actual[key] == expected[key], row["id"]
        assert sorted(actual["buckets"]) == sorted(expected["buckets"]), row["id"]
        assert sorted(actual["contributing_factors"]) == sorted(
            expected.get("contributing_factors", [])
        ), row["id"]


def test_analyze_joins_by_run_id_and_model():
    row = _cases()[0]
    evals = [
        row["eval_result"],
        {**row["eval_result"], "model": "base"},
    ]
    sidecars = analyzer.sidecar_index([row["sidecar"]])

    records = analyzer.analyze(evals, sidecars)

    assert len(records) == 2
    assert records[0]["bucket"] == "parse_failure"
    assert records[1]["bucket"] == "dataset_issue"
    assert records[1]["confidence"] == "candidate"


def test_cli_writes_jsonl_and_stdout_report(tmp_path, capsys):
    rows = _cases()[:2]
    results = tmp_path / "eval_results.jsonl"
    verdicts = tmp_path / "verdicts.jsonl"
    out = tmp_path / "improvement_records.jsonl"
    results.write_text("".join(json.dumps(row["eval_result"]) + "\n" for row in rows))
    verdicts.write_text("".join(json.dumps(row["sidecar"]) + "\n" for row in rows))

    rc = main([
        "--results", str(results),
        "--verdicts", str(verdicts),
        "--out", str(out),
        "--report",
    ])

    assert rc == 0
    written = [json.loads(line) for line in out.read_text().splitlines()]
    assert [row["bucket"] for row in written] == ["parse_failure", "false_positive_clean"]
    report = capsys.readouterr().out
    assert "Loop-Auditor Self-Improvement Report" in report
    assert "parse_failure: 1" in report


def test_cli_default_invokes_eval_harness_then_analyzes(monkeypatch, tmp_path, capsys):
    from loop_auditor_env import config, eval_harness

    fixture = _cases()[0]
    eval_output = tmp_path / "eval_results.jsonl"
    verdict_output = tmp_path / "verdicts.jsonl"
    out = tmp_path / "improvement_records.jsonl"
    report = tmp_path / "report.md"

    async def fake_run_eval(split=None, model_tag="base"):
        assert split == "heldout"
        assert model_tag == "trained"
        eval_output.write_text(json.dumps(fixture["eval_result"]) + "\n")
        verdict_output.write_text(json.dumps(fixture["sidecar"]) + "\n")
        return {"n": 1, "mean_reward": 0.0}

    monkeypatch.setattr(config, "EVAL_OUTPUT", eval_output)
    monkeypatch.setattr(eval_harness, "run_eval", fake_run_eval)

    rc = main([
        "--split", "heldout",
        "--model-tag", "trained",
        "--out", str(out),
        "--report", str(report),
    ])

    assert rc == 0
    assert json.loads(out.read_text())["bucket"] == "parse_failure"
    assert "parse_failure: 1" in report.read_text()
    assert "hud eval aggregate" in capsys.readouterr().out


def test_mcp_wrapper_analyzes_files(tmp_path):
    rows = _cases()[:1]
    results = tmp_path / "eval_results.jsonl"
    verdicts = tmp_path / "verdicts.jsonl"
    out = tmp_path / "improvement_records.jsonl"
    results.write_text("".join(json.dumps(row["eval_result"]) + "\n" for row in rows))
    verdicts.write_text("".join(json.dumps(row["sidecar"]) + "\n" for row in rows))

    summary = mcp_server.analyze_files(str(results), str(verdicts), str(out))
    report = mcp_server.markdown_report(str(results), str(verdicts))

    assert summary["n"] == 1
    assert summary["bucket_counts"] == {"parse_failure": 1}
    assert json.loads(out.read_text())["bucket"] == "parse_failure"
    assert "parse_failure: 1" in report
