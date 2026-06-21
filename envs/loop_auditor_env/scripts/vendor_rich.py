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


def _vendored_case_dir(run_id: str) -> str:
    """Vendored, deploy-resolvable case path for ``<task>__<variant>``.

    Relative to the env package, so it resolves under BOTH config.REPO_ROOT and
    config.PKG_DIR — including the flattened deploy image where PKG_DIR == /app
    and only rich_cases/ is COPY'd (the source generated_traces/ tree is not).
    """
    task, variant = run_id.split("__", 1)
    return f"rich_cases/{task}/{variant}"


def main() -> None:
    out = config.PKG_DIR / "rich"
    out.mkdir(exist_ok=True)
    case_out = config.PKG_DIR / "rich_cases"
    if case_out.exists():
        shutil.rmtree(case_out)
    case_out.mkdir(exist_ok=True)

    # Copy the public case artifacts first, so every trace can be verified to
    # resolve against the vendored tree before we commit the manifests.
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

    for split in ("train", "heldout"):
        traces = rich_loader.load_rich_taskset(
            config.RICH_TASKSET_DIR / f"{split}.jsonl", config.REPO_ROOT
        )
        for t in traces:
            # Repoint at the vendored tree (the source generated_traces/ prefix is
            # NOT shipped to the deploy image) so the metadata resolution channel
            # is live in deploy, not just the run_id-inference fallback.
            t.setdefault("metadata", {})["case_dir"] = _vendored_case_dir(t["run_id"])
            # FAIL LOUD: a case the auditor can't open is a guaranteed 0-reward
            # trap. Verify the metadata path itself resolves and is non-empty.
            meta_dir = config.PKG_DIR / t["metadata"]["case_dir"]
            if not meta_dir.is_dir():
                raise SystemExit(f"vendor_rich: {t['run_id']}: case dir missing: {meta_dir}")
            if artifacts.resolve_case_dir(t) is None or not artifacts.list_artifacts(t):
                raise SystemExit(f"vendor_rich: {t['run_id']}: no readable artifacts under {meta_dir}")
        path = out / f"{split}.jsonl"
        path.write_text("".join(json.dumps(t) + "\n" for t in traces))
        print(f"wrote {len(traces)} traces -> {path} (all case dirs resolve, non-empty)")


if __name__ == "__main__":
    main()
