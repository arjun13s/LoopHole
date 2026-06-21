"""Vendor the live_qwen taskset into a self-contained, deploy-resolvable tree.

Mirror of vendor_rich.py for Person 1's live_qwen set. The deploy container
(Dockerfile.hud, build context = the env dir) has neither the repo-root manifest
nor the generated_traces/ case tree, so this:

  * copies the PUBLIC case artifacts referenced by the live manifests into
    PKG_DIR/live_cases/ (preserving clean_cases/ vs labeled_cases/ structure),
  * normalizes each manifest row and REPOINTS metadata.case_dir at the vendored
    tree (relative to PKG_DIR, so it resolves under /app in the image),
  * FAIL-LOUD verifies every case resolves + has readable artifacts (an
    unopenable case is a guaranteed 0-reward trap),
  * writes PKG_DIR/live/{train,heldout}.jsonl, which env._load_live loads directly.

Re-run after scripts/build_live_manifest.py (or after Person 1 updates live_qwen):

    python envs/loop_auditor_env/scripts/vendor_live.py
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

_SRC_PREFIX = "generated_traces/live_qwen/"


def _vendored_case_dir(orig_case_dir: str) -> str:
    """generated_traces/live_qwen/clean_cases/X -> live_cases/clean_cases/X."""
    rel = orig_case_dir.split(_SRC_PREFIX, 1)[-1]
    return f"live_cases/{rel}"


def _copy_public(src_dir: Path, dest_dir: Path) -> int:
    copied = 0
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        if not artifacts.is_public_artifact(rel):
            continue
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied


def main() -> None:
    out = config.PKG_DIR / "live"
    out.mkdir(exist_ok=True)
    case_out = config.PKG_DIR / "live_cases"
    if case_out.exists():
        shutil.rmtree(case_out)
    case_out.mkdir(exist_ok=True)

    total_files = 0
    for split in ("train", "heldout"):
        manifest = config.LIVE_TASKSET_DIR / f"{split}.jsonl"
        if not manifest.exists():
            raise SystemExit(f"vendor_live: manifest missing: {manifest} (run scripts/build_live_manifest.py)")
        traces = rich_loader.load_rich_taskset(manifest, config.REPO_ROOT)
        for t in traces:
            orig = t.get("metadata", {}).get("case_dir")
            if not orig:
                raise SystemExit(f"vendor_live: {t['run_id']}: manifest row has no case_dir")
            # copy this case's public artifacts into the vendored tree
            total_files += _copy_public(config.REPO_ROOT / orig, case_out / _vendored_case_dir(orig).split("live_cases/", 1)[1])
            # repoint at the vendored tree (resolves under PKG_DIR == /app in deploy)
            t.setdefault("metadata", {})["case_dir"] = _vendored_case_dir(orig)
            meta_dir = config.PKG_DIR / t["metadata"]["case_dir"]
            if not meta_dir.is_dir():
                raise SystemExit(f"vendor_live: {t['run_id']}: vendored case dir missing: {meta_dir}")
            if artifacts.resolve_case_dir(t) is None or not artifacts.list_artifacts(t):
                raise SystemExit(f"vendor_live: {t['run_id']}: no readable artifacts under {meta_dir}")
        path = out / f"{split}.jsonl"
        path.write_text("".join(json.dumps(t) + "\n" for t in traces))
        print(f"wrote {len(traces)} traces -> {path} (all case dirs resolve, non-empty)")
    print(f"copied {total_files} public artifact files -> {case_out}")


if __name__ == "__main__":
    main()
