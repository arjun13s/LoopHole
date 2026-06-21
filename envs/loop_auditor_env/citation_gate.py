"""Deterministic step-id anti-fabrication gate for Loop-Auditor verdicts."""

from __future__ import annotations

import re


STEP_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(a(?:\d+|_[A-Za-z0-9]+_\d+))(?![A-Za-z0-9_])")
_PLAIN_NUMERIC_RE = re.compile(r"^a(\d+)$")


def _canonical_ref(ref: str) -> str:
    """Collapse zero-padding on a plain ``aNNN`` id so ``a5`` == ``a05`` == ``a005``.

    Real trace ids are zero-padded (``a001``..``a010``); the auditor often cites
    the shorthand ``a5``. Matching on the numeric value (not the literal text)
    stops that loose-but-correct reference from being scored as fabricated. Ids
    with non-numeric suffixes (``a_safety_0``) are left untouched.
    """
    m = _PLAIN_NUMERIC_RE.match(ref)
    return f"a{int(m.group(1))}" if m else ref


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
    real_canonical = {_canonical_ref(ref) for ref in trace_step_ids(trace)}
    fabricated = [ref for ref in checked if _canonical_ref(ref) not in real_canonical]
    return {
        "passed": not fabricated,
        "checked": checked,
        "fabricated": fabricated,
    }
