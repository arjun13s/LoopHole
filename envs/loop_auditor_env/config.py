"""Shared configuration + contract constants for the Loop-Auditor env.

OWNER: Claude (Person 2 critical path). Codex imports from here but MUST NOT edit it.
Everything overridable via env var so slugs/knobs change without code edits (model-agnostic).
"""

from __future__ import annotations

import os
from pathlib import Path

# --- paths -------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
# Repo root in the monorepo; falls back to PKG_DIR when the env is flattened into
# a container (e.g. /app on `hud deploy`, where PKG_DIR has no grandparent).
REPO_ROOT = PKG_DIR.parents[1] if len(PKG_DIR.parents) >= 2 else PKG_DIR
FIXTURES_DIR = PKG_DIR / "fixtures"


def _resolve_schemas_dir() -> Path:
    """Locate schemas/: env override, then the canonical repo-root copy (local
    dev), then a vendored copy beside the env (deploy/container build context)."""
    override = os.environ.get("LOOP_AUDITOR_SCHEMAS_DIR")
    if override:
        return Path(override)
    for candidate in (REPO_ROOT / "schemas", PKG_DIR / "schemas"):
        if (candidate / "verdict.json").exists():
            return candidate
    return PKG_DIR / "schemas"


SCHEMAS_DIR = _resolve_schemas_dir()
# Person 3's dashboard reads this file. Agree the path with Person 3 at H0.
EVAL_OUTPUT = PKG_DIR / "eval_results.jsonl"


def _resolve_taskset_dir() -> Path:
    """Locate Person 1's taskset/ (train.jsonl + heldout.jsonl): env override,
    then repo-root (local dev), then a vendored copy beside the env (deploy)."""
    override = os.environ.get("LOOP_AUDITOR_TASKSET_DIR")
    if override:
        return Path(override)
    for candidate in (REPO_ROOT / "taskset", PKG_DIR / "taskset"):
        if (candidate / "heldout.jsonl").exists():
            return candidate
    return REPO_ROOT / "taskset"


TASKSET_DIR = _resolve_taskset_dir()
# Which traces the env serves as tasks. Default "fixtures" (the 3 local sanity
# traces, keeps tests stable); "train"/"heldout"/"all" load Person 1's dataset;
# any other value is treated as a path to a .jsonl file or a dir of *.json.
DATASET = os.environ.get("LOOP_AUDITOR_DATASET", "fixtures")


def _resolve_base_traces_dir() -> Path:
    """Locate the clean base traces (tasks/base_traces/<base>.json) used by the
    deterministic fix-by-comparison grader: env override, then repo-root (local
    dev), then a vendored copy beside the env (deploy)."""
    override = os.environ.get("LOOP_AUDITOR_BASE_TRACES_DIR")
    if override:
        return Path(override)
    for candidate in (REPO_ROOT / "tasks" / "base_traces", PKG_DIR / "base_traces"):
        if candidate.is_dir():
            return candidate
    return REPO_ROOT / "tasks" / "base_traces"


# Source of known-correct actions for fix_grader.grade_fix (deterministic reward).
BASE_TRACES_DIR = _resolve_base_traces_dir()


def _resolve_rich_taskset_dir() -> Path:
    """Locate Person 1's rich taskset manifest dir (generated_traces/rich_taskset/
    {train,heldout}.jsonl): env override, repo-root, then a vendored copy."""
    override = os.environ.get("LOOP_AUDITOR_RICH_TASKSET_DIR")
    if override:
        return Path(override)
    for candidate in (REPO_ROOT / "generated_traces" / "rich_taskset", PKG_DIR / "rich_taskset"):
        if (candidate / "heldout.jsonl").exists():
            return candidate
    return REPO_ROOT / "generated_traces" / "rich_taskset"


# Manifest rows reference case/ground-truth paths relative to the repo root.
RICH_TASKSET_DIR = _resolve_rich_taskset_dir()

# --- model (single source of truth; chosen at H0) ----------------------------
# The trainable fork (Qwen3-8B via Tinker), created with `hud models fork`. Used
# for BOTH the rollout agent and TrainingClient. Override with LOOP_AUDITOR_MODEL
# (e.g. "claude" for a strong base eval, or another forked slug).
MODEL = os.environ.get("LOOP_AUDITOR_MODEL", "loophole-evalagent")

# --- auditor output controls (keep the verdict from being cut off) -----------
# The verdict is a tiny JSON object, but Qwen3-style models can emit <think>
# tokens. Training/GRPO wants cheap, parse-stable JSON. Eval can spend more
# auditor tokens to reduce expensive coding-agent escalation. Mode-specific env
# vars win; the old LOOP_AUDITOR_THINK / LOOP_AUDITOR_MAX_TOKENS remain broad
# overrides for both modes.
_TRUE_VALUES = ("1", "true", "yes", "on")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


_GLOBAL_AUDITOR_THINK = os.environ.get("LOOP_AUDITOR_THINK")
_GLOBAL_AUDITOR_MAX_TOKENS = os.environ.get("LOOP_AUDITOR_MAX_TOKENS")

AUDITOR_TRAIN_THINK = _env_bool(
    "LOOP_AUDITOR_TRAIN_THINK",
    (_GLOBAL_AUDITOR_THINK or "0").strip().lower() in _TRUE_VALUES,
)
AUDITOR_EVAL_THINK = _env_bool(
    "LOOP_AUDITOR_EVAL_THINK",
    (_GLOBAL_AUDITOR_THINK or "1").strip().lower() in _TRUE_VALUES,
)
AUDITOR_TRAIN_MAX_TOKENS = _env_int(
    "LOOP_AUDITOR_TRAIN_MAX_TOKENS",
    int(_GLOBAL_AUDITOR_MAX_TOKENS or (2048 if AUDITOR_TRAIN_THINK else 512)),
)
AUDITOR_EVAL_MAX_TOKENS = _env_int(
    "LOOP_AUDITOR_EVAL_MAX_TOKENS",
    int(_GLOBAL_AUDITOR_MAX_TOKENS or (4096 if AUDITOR_EVAL_THINK else 1024)),
)

# Back-compat aliases for older tests/scripts that read the single-mode knobs.
AUDITOR_THINK = AUDITOR_TRAIN_THINK
AUDITOR_MAX_TOKENS = AUDITOR_TRAIN_MAX_TOKENS


def auditor_output_controls(profile: str) -> dict:
    """Return think/max_tokens controls for the train or eval auditor profile."""
    if profile == "train":
        return {"think": AUDITOR_TRAIN_THINK, "max_tokens": AUDITOR_TRAIN_MAX_TOKENS}
    if profile == "eval":
        return {"think": AUDITOR_EVAL_THINK, "max_tokens": AUDITOR_EVAL_MAX_TOKENS}
    raise ValueError(f"unknown auditor profile: {profile!r}")

# --- GRPO knobs --------------------------------------------------------------
GROUP_SIZE = int(os.environ.get("LOOP_AUDITOR_GROUP_SIZE", "8"))
LR = float(os.environ.get("LOOP_AUDITOR_LR", "1e-5"))

# --- judge (separate strong model; NEVER the trained eval agent) -------------
JUDGE_MODEL = os.environ.get("LOOP_AUDITOR_JUDGE_MODEL", "claude-sonnet-4-6")
# Optional hard threshold applied to the 0..1 judge score (0.0 = pass-through).
EXPLANATION_SCORE_THRESHOLD = float(os.environ.get("LOOP_AUDITOR_EXPL_THRESHOLD", "0.0"))

# --- contract constants ------------------------------------------------------
NO_FAULT_STEP_ID = None  # verdict.predicted_step_id value for a clean trace
NO_FAULT_TYPE = None     # verdict.failure_type value for a clean trace
# Additive: wrong_file_edit comes from Person 1's rich taskset; safety is retained
# for the original taskset. The verdict.json enum mirrors this set.
FAILURE_TYPES = ("resource_misuse", "tool_misuse", "routing", "safety", "wrong_file_edit")

# Map common model phrasings onto the canonical enum. The auditor often names the
# SYMPTOM ("test_failure") rather than the cause ("tool_misuse"), or varies the
# spelling/casing. Normalizing here (a) lets a near-miss earn type credit instead
# of a hard 0, and (b) keeps grading robust without retraining. Edit freely; an
# unknown type is never coerced (it stays as-is and simply scores as a mismatch).
FAILURE_TYPE_ALIASES = {
    "test_failure": "tool_misuse",
    "tests_failed": "tool_misuse",
    "failed_tests": "tool_misuse",
    "failing_test": "tool_misuse",
    "tool": "tool_misuse",
    "tool_error": "tool_misuse",
    "resource": "resource_misuse",
    "resource_waste": "resource_misuse",
    "wasted_context": "resource_misuse",
    "context_misuse": "resource_misuse",
    "wrong_file": "wrong_file_edit",
    "wrong_edit": "wrong_file_edit",
    "edited_wrong_file": "wrong_file_edit",
    "route": "routing",
    "routing_error": "routing",
    "skipped_step": "routing",
    "missing_step": "routing",
}

_CANON_FAILURE_TYPES = {t.lower(): t for t in FAILURE_TYPES}


def normalize_failure_type(value):
    """Best-effort map a model-emitted failure_type onto the canonical enum.

    Returns the canonical string when the value is a known alias or a
    case-variant of an enum member; otherwise returns the original (stripped)
    value unchanged. Callers treat an unknown non-null type as a soft mismatch
    (it costs only the type term), never a hard rejection that would discard an
    otherwise-correct localization.
    """
    if not isinstance(value, str):
        return value
    key = "_".join(value.strip().lower().replace("-", " ").split())
    return FAILURE_TYPE_ALIASES.get(key) or _CANON_FAILURE_TYPES.get(key, value.strip())

# --- reward weights (mirror schemas/reward_spec.json §1.4) -------------------
W_LOCALIZATION = 1.0
W_FAILURE_TYPE = 0.3
W_EXPLANATION = 0.5

# --- gate (Design Y) + cost knobs (env-overridable) --------------------------
# Token COST term for the gate reward (reward = detection - LAMBDA_TOKENS*tokens).
# Default 0.0: tokens do NOT factor into reward (removes the negative gate rewards
# the cost penalty produced). Re-enable the cost-aware gate by setting
# LOOP_AUDITOR_LAMBDA_TOKENS (e.g. 0.0001) once detection is solid.
LAMBDA_TOKENS = float(os.environ.get("LOOP_AUDITOR_LAMBDA_TOKENS", "0.0"))
LAMBDA_X = float(os.environ.get("LOOP_AUDITOR_LAMBDA_X", "0.0"))  # 0 honors frozen §1.4
SOLUTION_COST = int(os.environ.get("LOOP_AUDITOR_SOLUTION_COST", "300"))
GATE_TURN_LIMIT = int(os.environ.get("LOOP_AUDITOR_GATE_TURN_LIMIT", "32"))

DEFAULT_ENABLED_TOOLS = frozenset({
    "get_trace_summary", "get_iteration", "get_step",
    "search_steps", "get_errors", "get_step_io",
    "list_artifacts", "read_artifact", "search_artifacts",
    "get_budget", "observe_next", "gate",
})  # get_solution OFF by default; scenarios opt it in
