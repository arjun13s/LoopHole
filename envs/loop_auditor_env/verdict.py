"""Verdict parsing + validation against schemas/verdict.json.

OWNER: Codex. Pure, deterministic, no network.
"""

from __future__ import annotations


def parse_verdict(raw: "str | dict") -> dict:
    """Coerce raw auditor output into a verdict dict.

    If ``raw`` is a str, tolerantly extract the JSON object (handle ```json code
    fences and surrounding prose). Returns a dict (not yet validated).
    Raise ValueError if no JSON object can be recovered.
    """
    raise NotImplementedError


def validate_verdict(obj: dict) -> dict:
    """Validate ``obj`` against schemas/verdict.json and normalize.

    Requires keys predicted_step_id, failure_type, explanation, proposed_fix and
    enum membership for failure_type (incl. 'none'). Returns the normalized
    verdict. Raise ValueError (including the schema errors) on invalid input.
    Use the ``jsonschema`` package + the schema loaded from config.SCHEMAS_DIR.
    """
    raise NotImplementedError
