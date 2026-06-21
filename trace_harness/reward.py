"""Deterministic reward for structured auditor verdicts."""

from __future__ import annotations

import json
from typing import Any


def parse_audit_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from AUDIT.md-style text."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("AUDIT.md contains no JSON object")


def score_verdict(verdict: dict[str, Any], ground_truth: dict[str, Any]) -> float:
    """Score only the structured verdict JSON."""
    if ground_truth["fault_present"] is False:
        return 1.0 if verdict.get("fault_present") is False else 0.0
    if verdict.get("fault_present") is False:
        return 0.0

    score = 0.0
    if verdict.get("predicted_step_id") == ground_truth["fault_step_id"]:
        score += 0.45
    if verdict.get("failure_type") == ground_truth["failure_type"]:
        score += 0.25

    predicted_fix = verdict.get("proposed_fix") or verdict.get("fix") or {}
    expected_fix = ground_truth.get("fix") or {}
    if isinstance(predicted_fix, dict):
        if predicted_fix.get("action") == expected_fix.get("action"):
            score += 0.20
        if predicted_fix.get("target") == expected_fix.get("target"):
            score += 0.10
    return round(max(0.0, min(1.0, score)), 10)


def score_audit_text(audit_md: str, ground_truth: dict[str, Any]) -> float:
    return score_verdict(parse_audit_json(audit_md), ground_truth)
