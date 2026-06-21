"""Read-only artifact context for rich Loop-Auditor traces.

These helpers expose the generated case files (repo snapshots, test outputs,
patches, prompts, transcripts) without exposing audit labels or ground truth.
They are pure aside from local filesystem reads and never import HUD/network
packages.
"""

from __future__ import annotations

from pathlib import Path

try:  # package (pytest) | flat (hud `env:env`)
    from . import config
except ImportError:
    import config

DEFAULT_MAX_CHARS = 4000
MAX_READ_CHARS = 20000
MAX_RESULTS = 200
EXCLUDED_BASENAMES = {"audit.md"}
EXCLUDED_SUBSTRINGS = ("ground_truth", "answer_key", "expected_verdict")


def _as_int(value, default: int, lower: int, upper: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lower, min(upper, n))


def _metadata_case_dirs(trace: dict) -> list[Path]:
    meta = trace.get("metadata") if isinstance(trace, dict) else None
    raw_values = []
    if isinstance(meta, dict):
        raw_values.extend(meta.get(k) for k in ("case_dir", "artifact_root"))
    if isinstance(trace, dict):
        raw_values.extend(trace.get(k) for k in ("case_dir", "artifact_root"))

    out = []
    for raw in raw_values:
        if not isinstance(raw, str) or not raw.strip():
            continue
        p = Path(raw)
        if p.is_absolute():
            out.append(p)
        else:
            out.extend((config.REPO_ROOT / p, config.PKG_DIR / p))
    return out


def _inferred_case_dirs(trace: dict) -> list[Path]:
    run_id = trace.get("run_id") if isinstance(trace, dict) else None
    if not isinstance(run_id, str) or "__" not in run_id:
        return []
    task, variant = run_id.split("__", 1)
    if not task or not variant or "/" in task or "/" in variant:
        return []
    return [
        config.PKG_DIR / "rich_cases" / task / variant,
        config.REPO_ROOT / "generated_traces" / "rich_cases" / task / variant,
    ]


def resolve_case_dir(trace: dict) -> "Path | None":
    """Return the rich case artifact directory for a trace, if available."""
    for candidate in _metadata_case_dirs(trace) + _inferred_case_dirs(trace):
        if candidate.is_dir():
            return candidate
    return None


def is_public_artifact(path: Path) -> bool:
    """Return whether a relative artifact path can be shown to the auditor."""
    rel = path.as_posix().lower()
    if path.name.startswith(".") or any(part.startswith(".") for part in path.parts):
        return False
    if path.name.lower() in EXCLUDED_BASENAMES:
        return False
    return not any(marker in rel for marker in EXCLUDED_SUBSTRINGS)


def _iter_public_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root)
            if is_public_artifact(rel):
                files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def list_artifacts(trace: dict, max_results: int = MAX_RESULTS) -> list[str]:
    """List readable artifact paths for the trace, relative to the case root."""
    root = resolve_case_dir(trace)
    if root is None:
        return []
    limit = _as_int(max_results, MAX_RESULTS, 1, 1000)
    return [p.relative_to(root).as_posix() for p in _iter_public_files(root)[:limit]]


def _safe_artifact_path(root: Path, artifact_path: str) -> Path:
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ValueError("artifact path must be a non-empty string")
    rel = Path(artifact_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe artifact path: {artifact_path}")
    candidate = (root / rel).resolve()
    resolved_root = root.resolve()
    if resolved_root not in candidate.parents and candidate != resolved_root:
        raise ValueError(f"unsafe artifact path: {artifact_path}")
    if not candidate.is_file():
        raise FileNotFoundError(f"artifact not found: {artifact_path}")
    if not is_public_artifact(candidate.relative_to(resolved_root)):
        raise PermissionError(f"artifact is not exposed: {artifact_path}")
    return candidate


def read_artifact(trace: dict, path: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    """Read a text artifact by relative path with deterministic truncation."""
    root = resolve_case_dir(trace)
    if root is None:
        return {"ok": False, "path": path, "content": "", "truncated": False, "error": "artifacts unavailable"}
    try:
        artifact = _safe_artifact_path(root, path)
        limit = _as_int(max_chars, DEFAULT_MAX_CHARS, 1, MAX_READ_CHARS)
        text = artifact.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError, PermissionError) as exc:
        return {"ok": False, "path": path, "content": "", "truncated": False, "error": str(exc)}
    truncated = len(text) > limit
    return {
        "ok": True,
        "path": artifact.relative_to(root).as_posix(),
        "content": text[:limit],
        "truncated": truncated,
        "error": None,
    }


def search_artifacts(trace: dict, query: str, max_results: int = 20, max_chars: int = 240) -> list[dict]:
    """Search public text artifacts for a case-insensitive query string."""
    root = resolve_case_dir(trace)
    if root is None or not isinstance(query, str) or not query.strip():
        return []
    needle = query.lower()
    limit = _as_int(max_results, 20, 1, 200)
    snippet_limit = _as_int(max_chars, 240, 40, 1000)
    hits = []
    for artifact in _iter_public_files(root):
        rel = artifact.relative_to(root).as_posix()
        try:
            lines = artifact.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            if needle in line.lower():
                snippet = line.strip()
                if len(snippet) > snippet_limit:
                    snippet = snippet[:snippet_limit]
                hits.append({"path": rel, "line": line_no, "snippet": snippet})
                if len(hits) >= limit:
                    return hits
    return hits
