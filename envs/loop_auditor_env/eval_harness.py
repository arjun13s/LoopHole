"""Base/trained eval over a taskset -> eval-result JSONL.

OWNER: Claude. Runs the auditor across a taskset, emits one record per trace
conforming to schemas/eval_result.json, aggregates, and writes config.EVAL_OUTPUT
for Person 3's dashboard. Honors the held-out split (no leakage into training).
"""

from __future__ import annotations

from . import config  # noqa: F401


def run_eval(split: str = "heldout", model_tag: str = "base") -> dict:
    """Run the eval and return aggregates (also writes per-record JSONL).

    model_tag is one of {"base", "trained"} (eval_result.json enum).
    """
    raise NotImplementedError


if __name__ == "__main__":
    run_eval()
