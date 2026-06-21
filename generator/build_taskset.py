"""Build deterministic train and held-out JSONL trace splits."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from fault_specs import FAULT_TYPES, fault_spec_for
from mutate import mutate
from validate import validate_trace


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_TRACES_DIR = REPO_ROOT / "tasks" / "base_traces"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Total traces to generate. Expected range: 40-60.")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "taskset")
    args = parser.parse_args()

    if not 40 <= args.n <= 60:
        raise ValueError("--n must be between 40 and 60")

    train, heldout = build_taskset(args.n)
    out_dir = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "heldout.jsonl", heldout)

    train_counts = _fault_counts(train)
    heldout_counts = _fault_counts(heldout)
    total_counts = _fault_counts(train + heldout)
    print(f"wrote {len(train)} train traces to {out_dir / 'train.jsonl'}")
    print(f"wrote {len(heldout)} held-out traces to {out_dir / 'heldout.jsonl'}")
    print(f"train counts: {dict(sorted(train_counts.items()))}")
    print(f"heldout counts: {dict(sorted(heldout_counts.items()))}")
    print(f"total counts: {dict(sorted(total_counts.items()))}")


def build_taskset(n: int) -> tuple[list[dict], list[dict]]:
    base_traces = _load_base_traces()
    if len(base_traces) < 4:
        raise ValueError("expected at least four clean base traces")

    for trace in base_traces:
        validate_trace(trace)

    train_bases = base_traces[:-1]
    heldout_bases = base_traces[-1:]
    train_count = int(n * 0.8)
    heldout_count = n - train_count

    train = _make_split(train_count, train_bases, split_name="train")
    heldout = _make_split(heldout_count, heldout_bases, split_name="heldout")

    _assert_disjoint(train, heldout)
    for trace in train + heldout:
        validate_trace(trace)
    return train, heldout


def _load_base_traces() -> list[dict]:
    traces = []
    for path in sorted(BASE_TRACES_DIR.glob("clean_*.json")):
        with path.open() as f:
            traces.append(json.load(f))
    return traces


def _make_split(count: int, bases: list[dict], split_name: str) -> list[dict]:
    traces = []
    category_counts = _balanced_counts(count, FAULT_TYPES)
    serial = 0
    for category in FAULT_TYPES:
        for variant in range(category_counts[category]):
            base = bases[(serial + variant) % len(bases)]
            if category == "clean":
                trace = _clone_clean(base, split_name, variant)
            else:
                trace, _label = mutate(base, fault_spec_for(category, variant))
                trace["id"] = f"{trace['id']}__{split_name}_{variant:03d}"
            validate_trace(trace)
            traces.append(trace)
        serial += category_counts[category]
    return traces


def _clone_clean(base: dict, split_name: str, variant: int) -> dict:
    trace = deepcopy(base)
    trace["id"] = f"{base['id']}__clean__{split_name}_{variant:03d}"
    validate_trace(trace)
    return trace


def _balanced_counts(count: int, categories: tuple[str, ...]) -> dict[str, int]:
    base_count, remainder = divmod(count, len(categories))
    return {
        category: base_count + (1 if index < remainder else 0)
        for index, category in enumerate(categories)
    }


def _write_jsonl(path: Path, traces: list[dict]) -> None:
    with path.open("w") as f:
        for trace in traces:
            f.write(json.dumps(trace, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _fault_counts(traces: list[dict]) -> Counter:
    counts = Counter()
    for trace in traces:
        planted_failure = trace.get("planted_failure")
        counts["clean" if planted_failure is None else planted_failure["failure_type"]] += 1
    return counts


def _assert_disjoint(train: list[dict], heldout: list[dict]) -> None:
    train_ids = {trace["id"] for trace in train}
    heldout_ids = {trace["id"] for trace in heldout}
    overlap = train_ids & heldout_ids
    if overlap:
        raise ValueError(f"train and heldout trace ids overlap: {sorted(overlap)}")

    train_task_ids = {trace["task_id"] for trace in train}
    heldout_task_ids = {trace["task_id"] for trace in heldout}
    task_overlap = train_task_ids & heldout_task_ids
    if task_overlap:
        raise ValueError(f"heldout base tasks appear in train: {sorted(task_overlap)}")


if __name__ == "__main__":
    main()
