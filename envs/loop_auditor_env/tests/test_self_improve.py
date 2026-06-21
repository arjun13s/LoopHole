import json

from loop_auditor_env import self_improve


def _eval(**overrides):
    row = {
        "run_id": "r1",
        "model": "base",
        "localization_correct": False,
        "failure_type_correct": False,
        "explanation_score": 0.0,
        "reward": 0.0,
        "trace_tokens": 10,
        "auditor_tokens": 5,
    }
    row.update(overrides)
    return row


def _trace(planted_failure=None, **overrides):
    row = {
        "run_id": "r1",
        "iterations": [
            {
                "index": 0,
                "steps": [
                    {"step_id": "a1", "action_type": "tool_call"},
                    {"step_id": "a7", "action_type": "tool_call"},
                ],
            }
        ],
        "planted_failure": planted_failure,
    }
    row.update(overrides)
    return row


def _bug():
    return {
        "step_id": "a7",
        "failure_type": "tool_misuse",
        "description": "Submitted after tests failed.",
    }


def _verdict(**overrides):
    row = {
        "fault_present": True,
        "predicted_step_id": "a7",
        "failure_type": "tool_misuse",
        "explanation": "The problem is at a7.",
        "proposed_fix": "Do not submit after failing tests.",
    }
    row.update(overrides)
    return row


def test_clean_false_positive_bucket():
    record = self_improve.analyze_eval_record(
        _eval(run_id="clean", reward=0.0),
        verdict_row=_verdict(predicted_step_id="a1", failure_type="routing"),
        trace=_trace(run_id="clean", planted_failure=None),
    )

    assert record["buckets"] == ["false_positive_clean"]
    assert record["recommended_fix_type"] == "clean_trace_calibration"
    assert "over-called" in record["diagnosis"]


def test_buggy_false_negative_bucket():
    record = self_improve.analyze_eval_record(
        _eval(reward=0.0),
        verdict_row=_verdict(
            fault_present=False,
            predicted_step_id=None,
            failure_type=None,
            proposed_fix=None,
            explanation="No process fault.",
        ),
        trace=_trace(_bug()),
    )

    assert record["buckets"] == ["false_negative_buggy"]
    assert record["recommended_fix_type"] == "fault_detection"
    assert any("marked clean" in item for item in record["evidence"])


def test_bad_localization_bucket():
    record = self_improve.analyze_eval_record(
        _eval(localization_correct=False, failure_type_correct=True, reward=0.3),
        verdict_row=_verdict(predicted_step_id="a1"),
        trace=_trace(_bug()),
    )

    assert record["buckets"] == ["bad_localization"]
    assert record["recommended_fix_type"] == "localization"
    assert any("expected 'a7'" in item for item in record["evidence"])


def test_bad_failure_type_bucket_even_when_reward_above_failure_threshold():
    row = _eval(localization_correct=True, failure_type_correct=False, reward=1.0)
    improvements = self_improve.analyze_eval_records(
        [row],
        verdicts_by_run_id={"r1": _verdict(failure_type="routing")},
        traces_by_run_id={"r1": _trace(_bug())},
        max_reward=0.999,
    )

    assert len(improvements) == 1
    assert improvements[0]["buckets"] == ["bad_failure_type"]
    assert improvements[0]["recommended_fix_type"] == "failure_type_taxonomy"


def test_weak_fix_bucket_for_correct_localization_and_type():
    record = self_improve.analyze_eval_record(
        _eval(localization_correct=True, failure_type_correct=True, explanation_score=0.2, reward=1.4),
        verdict_row=_verdict(),
        trace=_trace(_bug()),
    )

    assert record["buckets"] == ["weak_fix"]
    assert record["recommended_fix_type"] == "fix_quality"
    assert "explanation_score=0.200" in record["evidence"][0]


def test_fabricated_citation_bucket():
    record = self_improve.analyze_eval_record(
        _eval(localization_correct=True, failure_type_correct=True, explanation_score=0.0, reward=1.3),
        verdict_row=_verdict(explanation="The real issue is at a99, not a7."),
        trace=_trace(_bug()),
    )

    assert "fabricated_step_ref" in record["buckets"]
    assert "weak_fix" in record["buckets"]
    assert any("a99" in item for item in record["evidence"])


def test_malformed_raw_verdict_parse_failure_bucket():
    record = self_improve.analyze_eval_record(
        _eval(run_id="parse-fail", reward=0.0),
        verdict_row={"run_id": "parse-fail", "raw_verdict": "not json at all"},
        trace=_trace(run_id="parse-fail", planted_failure=None),
    )

    assert "parse_failure" in record["buckets"]
    assert any("no JSON object" in item for item in record["evidence"])


def test_artifact_miss_when_rich_trace_has_no_artifact_tool_usage():
    record = self_improve.analyze_eval_record(
        _eval(run_id="task__tool_misuse", reward=0.0),
        verdict_row={
            "run_id": "task__tool_misuse",
            "verdict": _verdict(predicted_step_id="a1"),
            "tool_calls": [{"name": "get_step"}],
        },
        trace=_trace(
            _bug(),
            run_id="task__tool_misuse",
            metadata={"case_dir": "envs/loop_auditor_env/rich_cases/task/tool_misuse"},
        ),
    )

    assert "artifact_miss" in record["buckets"]
    assert record["recommended_fix_type"] == "artifact_inspection"


def test_report_helpers_write_jsonl_and_markdown(tmp_path):
    records = [
        self_improve.analyze_eval_record(
            _eval(run_id="clean", reward=0.0),
            verdict_row=_verdict(predicted_step_id="a1"),
            trace=_trace(run_id="clean", planted_failure=None),
        )
    ]
    out = tmp_path / "report.jsonl"

    self_improve.write_jsonl(records, out)
    round_trip = [json.loads(line) for line in out.read_text().splitlines()]
    markdown = self_improve.format_markdown_summary(round_trip)

    assert round_trip[0]["run_id"] == "clean"
    assert "false_positive_clean: 1" in markdown
    assert "clean: reward=0.000" in markdown
