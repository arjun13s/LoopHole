import pytest

from loop_auditor_env import config
from loop_auditor_env.verdict import parse_verdict, validate_verdict


VALID_VERDICT = {
    "predicted_step_id": "iter0.step1.bad",
    "failure_type": "routing",
    "explanation": "The agent edited the admin route instead of customer checkout.",
    "proposed_fix": "Edit apps/customer/checkout/tax.ts instead.",
}


def test_parse_verdict_from_model_text():
    raw = f"""
    The answer is:
    ```json
    {{"predicted_step_id": "iter0.step1.bad", "failure_type": "routing", "explanation": "Wrong route.", "proposed_fix": "Patch the customer checkout route."}}
    ```
    """

    verdict = parse_verdict(raw)

    assert verdict["predicted_step_id"] == "iter0.step1.bad"
    assert verdict["failure_type"] == "routing"


def test_validate_verdict_valid_normalizes_strings():
    messy = {key: f"  {value}  " for key, value in VALID_VERDICT.items()}

    assert validate_verdict(messy) == VALID_VERDICT


def test_validate_verdict_accepts_clean_sentinel():
    verdict = {
        "predicted_step_id": config.NO_FAULT_STEP_ID,
        "failure_type": config.NO_FAULT_TYPE,
        "explanation": "No faulty span is visible.",
        "proposed_fix": "No fix needed.",
    }

    assert validate_verdict(verdict) == verdict


def test_parse_verdict_malformed_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        parse_verdict("there is no json object here")


def test_validate_verdict_reports_schema_errors():
    with pytest.raises(ValueError, match="failure_type"):
        validate_verdict(
            {
                "predicted_step_id": "iter0.step1.bad",
                "failure_type": "not-a-type",
                "explanation": "Bad enum.",
                "proposed_fix": "Use a valid enum.",
            }
        )

