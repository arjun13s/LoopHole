"""Verdict parsing + validation against schemas/verdict.json.

OWNER: Codex. Pure, deterministic, no network.
"""

from __future__ import annotations

import json
from typing import Any

try:  # package (pytest) | flat (hud `env:env`)
    from . import config
except ImportError:
    import config


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

    Requires keys fault_present, predicted_step_id, failure_type, explanation,
    proposed_fix and enum membership for failure_type. Returns the normalized
    verdict. Raise ValueError (including the schema errors) on invalid input.
    Load schemas/verdict.json from config.SCHEMAS_DIR; keep validation dependency-free.
    """
    if not isinstance(obj, dict):
        raise TypeError("verdict must be a dict")

    normalized = dict(obj)
    for key, value in list(normalized.items()):
        if isinstance(value, str):
            normalized[key] = value.strip()

    # Lenient failure_type: coerce known aliases / case-variants onto the enum.
    # An unknown type is kept as-is (not nulled) and is NOT a hard error below —
    # it should cost only the type term in compute_reward, never discard a
    # correct localization. The structural clean/fault checks still apply.
    if "failure_type" in normalized:
        normalized["failure_type"] = config.normalize_failure_type(normalized["failure_type"])

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
        rule_type = rules.get("type")
        allowed_types = rule_type if isinstance(rule_type, list) else [rule_type]
        if rule_type is not None and not _matches_type(value, allowed_types):
            errors.append(f"{key}: {value!r} is not of type {allowed_types!r}")
            continue
        if "enum" in rules and value not in rules["enum"]:
            if key == "failure_type":
                continue  # lenient: an out-of-enum type is a soft mismatch, not a reject
            errors.append(f"{key}: {value!r} is not one of {rules['enum']!r}")
    if normalized.get("fault_present") is False:
        if normalized.get("predicted_step_id") is not None:
            errors.append("predicted_step_id: clean verdict must use null")
        if normalized.get("failure_type") is not None:
            errors.append("failure_type: clean verdict must use null")
        if normalized.get("proposed_fix") is not None:
            errors.append("proposed_fix: clean verdict must use null")
    elif normalized.get("fault_present") is True:
        if normalized.get("predicted_step_id") is None:
            errors.append("predicted_step_id: fault verdict must name a step")
        if normalized.get("failure_type") is None:
            errors.append("failure_type: fault verdict must name a failure type")
        if normalized.get("proposed_fix") is None:
            errors.append("proposed_fix: fault verdict must include a fix")

    if errors:
        raise ValueError("invalid verdict: " + "; ".join(errors))
    return normalized


def _matches_type(value, allowed_types: list) -> bool:
    for type_name in allowed_types:
        if type_name == "boolean" and isinstance(value, bool):
            return True
        if type_name == "string" and isinstance(value, str):
            return True
        if type_name == "null" and value is None:
            return True
    return False
