"""Deterministic step-id anti-fabrication gate for Loop-Auditor verdicts."""

from __future__ import annotations

import re


STEP_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(a(?:\d+|_[A-Za-z0-9]+_\d+))(?![A-Za-z0-9_])")


def trace_step_ids(trace: dict) -> set[str]:
    """Return all real step_ids present in the trace."""
    ids: set[str] = set()
    for iteration in trace.get("iterations", []) or []:
        for step in iteration.get("steps", []) or []:
            step_id = step.get("step_id")
            if isinstance(step_id, str):
                ids.add(step_id)
    return ids


def extract_step_refs(text: str) -> list[str]:
    """Return deduped step-id references found in text."""
    seen: set[str] = set()
    refs: list[str] = []
    for match in STEP_ID_RE.finditer(text or ""):
        ref = match.group(1)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def check(verdict: dict, trace: dict) -> dict:
    """Return whether verdict text cites only real trace step_ids."""
    text = f"{verdict.get('explanation') or ''} {verdict.get('proposed_fix') or ''}"
    checked = extract_step_refs(text)
    real = trace_step_ids(trace)
    fabricated = [ref for ref in checked if ref not in real]
    return {
        "passed": not fabricated,
        "checked": checked,
        "fabricated": fabricated,
    }
