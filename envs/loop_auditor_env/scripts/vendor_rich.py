"""Vendor Person 1's rich taskset into self-contained normalized JSONL.

The deploy container (Dockerfile.hud build context = the env dir) has neither the
repo-root manifest nor the 812-file case tree. This pre-normalizes the rich
manifest into PKG_DIR/rich/{train,heldout}.jsonl — one full normalized trace per
line (iterations + planted_failure incl. the structured fix) — which the Dockerfile
copies and env._load_rich loads directly. Re-run after Person 1 updates
generated_traces/rich_taskset/.

    python envs/loop_auditor_env/scripts/vendor_rich.py
"""

import json
import shutil
import sys
from pathlib import Path

ENV_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENV_ROOT))

import config  # noqa: E402
import artifacts  # noqa: E402
import rich_loader  # noqa: E402


def main() -> None:
    out = config.PKG_DIR / "rich"
    out.mkdir(exist_ok=True)
    case_out = config.PKG_DIR / "rich_cases"
    if case_out.exists():
        shutil.rmtree(case_out)
    case_out.mkdir(exist_ok=True)

    for split in ("train", "heldout"):
        traces = rich_loader.load_rich_taskset(
            config.RICH_TASKSET_DIR / f"{split}.jsonl", config.REPO_ROOT
        )
        path = out / f"{split}.jsonl"
        path.write_text("".join(json.dumps(t) + "\n" for t in traces))
        print(f"wrote {len(traces)} traces -> {path}")

    copied = 0
    src_root = config.REPO_ROOT / "generated_traces" / "rich_cases"
    for src in sorted(src_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if not artifacts.is_public_artifact(rel):
            continue
        dest = case_out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    print(f"wrote {copied} public artifact files -> {case_out}")


if __name__ == "__main__":
    main()
