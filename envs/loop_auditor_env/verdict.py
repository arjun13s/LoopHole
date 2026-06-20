"""Verdict parsing + validation against schemas/verdict.json.

OWNER: Codex. Pure, deterministic, no network.
"""

from __future__ import annotations

import json
from typing import Any

from . import config


_SCHEMA_PATH = config.SCHEMAS_DIR / "verdict.json"


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise ValueError("no JSON object found in verdict text")


def parse_verdict(raw: "str | dict") -> dict:
    """Coerce raw auditor output into a verdict dict.

    If ``raw`` is a str, tolerantly extract the JSON object (handle ```json code
    fences and surrounding prose). Returns a dict (not yet validated).
    Raise ValueError if no JSON object can be recovered.
    """
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        raise TypeError("raw verdict must be a str or dict")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _extract_json_object(raw)
    if not isinstance(parsed, dict):
        raise ValueError("verdict JSON must be an object")
    return parsed


def validate_verdict(obj: dict) -> dict:
    """Validate ``obj`` against schemas/verdict.json and normalize.

    Requires keys predicted_step_id, failure_type, explanation, proposed_fix and
    enum membership for failure_type (incl. 'none'). Returns the normalized
    verdict. Raise ValueError (including the schema errors) on invalid input.
    Load schemas/verdict.json from config.SCHEMAS_DIR; keep validation dependency-free.
    """
    if not isinstance(obj, dict):
        raise TypeError("verdict must be a dict")

    normalized = dict(obj)
    for key, value in list(normalized.items()):
        if isinstance(value, str):
            normalized[key] = value.strip()

    schema = json.loads(_SCHEMA_PATH.read_text())
    required = set(schema["required"])
    allowed = set(schema["properties"])
    errors = []

    missing = sorted(required - set(normalized))
    for key in missing:
        errors.append(f"{key}: required property is missing")

    extra = sorted(set(normalized) - allowed)
    for key in extra:
        errors.append(f"{key}: additional properties are not allowed")

    for key, rules in schema["properties"].items():
        if key not in normalized:
            continue
        value = normalized[key]
        if rules.get("type") == "string" and not isinstance(value, str):
            errors.append(f"{key}: {value!r} is not of type 'string'")
            continue
        if "enum" in rules and value not in rules["enum"]:
            errors.append(f"{key}: {value!r} is not one of {rules['enum']!r}")

    if errors:
        raise ValueError("invalid verdict: " + "; ".join(errors))
    return normalized
