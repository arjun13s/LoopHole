from loop_auditor_env import citation_gate


def _trace() -> dict:
    return {
        "run_id": "trace",
        "iterations": [
            {
                "index": 0,
                "steps": [
                    {"step_id": "a0", "action_type": "message"},
                    {"step_id": "a4", "action_type": "tool_call"},
                    {"step_id": "a_safety_0", "action_type": "tool_call"},
                ],
            }
        ],
    }


def test_trace_step_ids_collects_simple_and_safety_ids():
    assert citation_gate.trace_step_ids(_trace()) == {"a0", "a4", "a_safety_0"}


def test_extract_step_refs_finds_step_ids_and_ignores_words():
    text = "The issue is in a4 and a_safety_0, not in agent actions or alpha words. a4 repeats."

    assert citation_gate.extract_step_refs(text) == ["a4", "a_safety_0"]


def test_check_passes_when_all_cited_ids_are_real():
    verdict = {
        "explanation": "Step a4 reads too much.",
        "proposed_fix": "Remove a_safety_0 if present.",
    }

    assert citation_gate.check(verdict, _trace()) == {
        "passed": True,
        "checked": ["a4", "a_safety_0"],
        "fabricated": [],
    }


def test_check_fails_with_fabricated_step_id():
    verdict = {
        "explanation": "Step a4 is real but a12 is fabricated.",
        "proposed_fix": "Fix a12.",
    }

    assert citation_gate.check(verdict, _trace()) == {
        "passed": False,
        "checked": ["a4", "a12"],
        "fabricated": ["a12"],
    }


def test_check_passes_when_no_step_refs():
    verdict = {
        "explanation": "The tests were skipped.",
        "proposed_fix": "Run tests before submitting.",
    }

    assert citation_gate.check(verdict, _trace()) == {
        "passed": True,
        "checked": [],
        "fabricated": [],
    }
