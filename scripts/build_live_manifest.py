"""Build a rich-format manifest (train/heldout .jsonl) for the live_qwen taskset.

Person 1's `trace_harness/live_modal_worker.py` writes the live_qwen case dirs +
per-case ground_truth + summary.json, but NOT a manifest — so the env can't serve
them (env.select_traces only loads rich traces through a `<split>.jsonl` manifest).
This emits that manifest so `LOOP_AUDITOR_DATASET=live_train|live_heldout` works.

Rows match the rich manifest shape rich_loader expects:
  {case_id, case_dir, failure_type, ground_truth, split}

Only GRADEABLE cases are included: the labeled (planted-fault) + clean cases.
`failed_cases/` are excluded — they have no ground truth, so the reward can't
score them as audit tasks.

Split: by live instance (default heldout = the highest-numbered instance), so
train/heldout are disjoint at the case level. NOTE: all labeled cases derive from
ONE base task (date_range_boundary), so heldout is a near-duplicate of train — a
known diversity limit of this taskset, not of the wiring.

Run:  python scripts/build_live_manifest.py [--heldout-instance live_003]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE = REPO_ROOT / "generated_traces" / "live_qwen"
REL = "generated_traces/live_qwen"

# Fault types whose injected fault is RECOVERED in-trace (error -> fix -> tests
# pass -> submit), making the trace indistinguishable from healthy self-correction.
# Per the auditor rubric ("a failing test the agent then fixes is CLEAN") these are
# mislabeled as buggy and would train the model to over-flag healthy recovery. We
# keep the trace as a CLEAN hard negative (auditor must NOT flag it) by pointing the
# row at the instance's clean ground truth instead of the buggy label.
CLEAN_RELABEL_TYPES = {"tool_misuse"}


def _instance(case_id: str) -> str:
    """date_range_boundary__live_003__routing -> live_003 ; ...__live_003 -> live_003."""
    for part in case_id.split("__"):
        if part.startswith("live_"):
            return part
    return case_id


def build_rows() -> list[dict]:
    rows: list[dict] = []
    # clean cases: clean_cases/<cid>/ + clean_ground_truth/<cid>.json
    for gt in sorted((LIVE / "clean_ground_truth").glob("*.json")):
        cid = gt.stem
        rows.append({
            "case_id": cid,
            "case_dir": f"{REL}/clean_cases/{cid}",
            "failure_type": "clean",
            "ground_truth": f"{REL}/clean_ground_truth/{cid}.json",
        })
    # labeled cases: labeled_cases/<base>/<type>/ + labeled_ground_truth/<base>__<type>.json
    for gt in sorted((LIVE / "labeled_ground_truth").glob("*.json")):
        cid = gt.stem  # date_range_boundary__live_000__resource_misuse
        base, ftype = cid.rsplit("__", 1)
        if ftype in CLEAN_RELABEL_TYPES:
            rows.append({
                "case_id": cid,
                "case_dir": f"{REL}/labeled_cases/{base}/{ftype}",
                "failure_type": "clean",
                "relabeled_from": ftype,  # traceability: was a (recovered) tool_misuse
                "ground_truth": f"{REL}/clean_ground_truth/{base}.json",
            })
        else:
            rows.append({
                "case_id": cid,
                "case_dir": f"{REL}/labeled_cases/{base}/{ftype}",
                "failure_type": ftype,
                "ground_truth": f"{REL}/labeled_ground_truth/{cid}.json",
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout-instance", default=None,
                    help="instance slug to hold out (default: the highest live_NNN present)")
    args = ap.parse_args()

    rows = build_rows()
    instances = sorted({_instance(r["case_id"]) for r in rows})
    heldout_inst = args.heldout_instance or (instances[-1] if instances else "")

    train, heldout = [], []
    for r in rows:
        (heldout if _instance(r["case_id"]) == heldout_inst else train).append(
            {**r, "split": "heldout" if _instance(r["case_id"]) == heldout_inst else "train"}
        )

    for split, recs in (("train", train), ("heldout", heldout)):
        path = LIVE / f"{split}.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in recs))
        n_clean = sum(1 for r in recs if r["failure_type"] == "clean")
        print(f"{split}: {len(recs)} cases ({n_clean} clean, {len(recs) - n_clean} buggy) -> {path}")
    print(f"instances={instances}; heldout={heldout_inst!r}")


if __name__ == "__main__":
    main()
