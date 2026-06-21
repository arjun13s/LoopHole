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

# --- model (single source of truth; chosen at H0) ----------------------------
# NOTE: HUD-native training may require a forked slug (`hud models fork ... --name ...`);
# set LOOP_AUDITOR_MODEL to that slug once forked.
MODEL = os.environ.get("LOOP_AUDITOR_MODEL", "Qwen/Qwen2.5-7B-Instruct")

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
FAILURE_TYPES = ("resource_misuse", "tool_misuse", "routing", "safety")

# --- reward weights (mirror schemas/reward_spec.json §1.4) -------------------
W_LOCALIZATION = 1.0
W_FAILURE_TYPE = 0.3
W_EXPLANATION = 0.5

# --- gate (Design Y) + cost knobs (env-overridable) --------------------------
LAMBDA_TOKENS = float(os.environ.get("LOOP_AUDITOR_LAMBDA_TOKENS", "0.001"))
LAMBDA_X = float(os.environ.get("LOOP_AUDITOR_LAMBDA_X", "0.0"))  # 0 honors frozen §1.4
SOLUTION_COST = int(os.environ.get("LOOP_AUDITOR_SOLUTION_COST", "300"))
GATE_TURN_LIMIT = int(os.environ.get("LOOP_AUDITOR_GATE_TURN_LIMIT", "32"))

DEFAULT_ENABLED_TOOLS = frozenset({
    "get_trace_summary", "get_iteration", "get_step",
    "search_steps", "get_errors", "get_step_io",
    "get_budget", "observe_next", "gate",
})  # get_solution OFF by default; scenarios opt it in
