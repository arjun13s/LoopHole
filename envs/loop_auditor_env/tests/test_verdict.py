import json
from pathlib import Path

import pytest

from loop_auditor_env import config
from loop_auditor_env.verdict import parse_verdict, validate_verdict


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "verdict.json"
VALID_VERDICT = {
    "fault_present": True,
    "predicted_step_id": "iter0.step1.bad",
    "failure_type": "routing",
    "explanation": "The agent edited the admin route instead of customer checkout.",
    "proposed_fix": "Edit apps/customer/checkout/tax.ts instead.",
}


def test_verdict_schema_contract_matches_config_and_valid_fixture():
    schema = json.loads(SCHEMA_PATH.read_text())

    assert schema["required"] == [
        "fault_present",
        "predicted_step_id",
        "failure_type",
        "explanation",
        "proposed_fix",
    ]
    assert schema["additionalProperties"] is False
    assert config.NO_FAULT_TYPE in schema["properties"]["failure_type"]["enum"]
    assert set(config.FAILURE_TYPES) <= set(schema["properties"]["failure_type"]["enum"])
    assert validate_verdict(VALID_VERDICT) == VALID_VERDICT


def test_parse_verdict_from_model_text():
    raw = f"""
    The answer is:
    ```json
    {{"fault_present": true, "predicted_step_id": "iter0.step1.bad", "failure_type": "routing", "explanation": "Wrong route.", "proposed_fix": "Patch the customer checkout route."}}
    ```
    """

    verdict = parse_verdict(raw)

    assert verdict["predicted_step_id"] == "iter0.step1.bad"
    assert verdict["failure_type"] == "routing"


def test_parse_verdict_does_not_validate():
    raw = '{"predicted_step_id": "iter0.step1.bad", "failure_type": "not-a-type"}'

    parsed = parse_verdict(raw)

    assert parsed == {
        "predicted_step_id": "iter0.step1.bad",
        "failure_type": "not-a-type",
    }
    with pytest.raises(ValueError, match="proposed_fix"):
        validate_verdict(parsed)


def test_validate_verdict_valid_normalizes_strings():
    messy = dict(VALID_VERDICT)
    for key, value in list(messy.items()):
        if isinstance(value, str):
            messy[key] = f"  {value}  "

    assert validate_verdict(messy) == VALID_VERDICT


def test_validate_verdict_accepts_clean_sentinel():
    verdict = {
        "fault_present": False,
        "predicted_step_id": config.NO_FAULT_STEP_ID,
        "failure_type": config.NO_FAULT_TYPE,
        "explanation": "No faulty span is visible.",
        "proposed_fix": None,
    }

    assert validate_verdict(verdict) == verdict


def test_parse_verdict_malformed_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        parse_verdict("there is no json object here")


def test_validate_verdict_reports_schema_errors():
    with pytest.raises(ValueError, match="failure_type"):
        validate_verdict(
            {
                "fault_present": True,
                "predicted_step_id": "iter0.step1.bad",
                "failure_type": "not-a-type",
                "explanation": "Bad enum.",
                "proposed_fix": "Use a valid enum.",
            }
        )


def test_validate_verdict_rejects_extra_fields():
    verdict = dict(VALID_VERDICT)
    verdict["confidence"] = 0.9

    with pytest.raises(ValueError, match="additional properties"):
        validate_verdict(verdict)


def test_validate_verdict_rejects_missing_proposed_fix():
    verdict = dict(VALID_VERDICT)
    del verdict["proposed_fix"]

    with pytest.raises(ValueError, match="proposed_fix"):
        validate_verdict(verdict)


def test_validate_verdict_rejects_clean_verdict_with_fix():
    verdict = {
        "fault_present": False,
        "predicted_step_id": None,
        "failure_type": None,
        "explanation": "No fault.",
        "proposed_fix": "Change something anyway.",
    }

    with pytest.raises(ValueError, match="clean verdict"):
        validate_verdict(verdict)
