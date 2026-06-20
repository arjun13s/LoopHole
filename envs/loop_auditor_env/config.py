"""Shared configuration + contract constants for the Loop-Auditor env.

OWNER: Claude (Person 2 critical path). Codex imports from here but MUST NOT edit it.
Everything overridable via env var so slugs/knobs change without code edits (model-agnostic).
"""

from __future__ import annotations

import os
from pathlib import Path

# --- paths -------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = PKG_DIR / "fixtures"
# Person 3's dashboard reads this file. Agree the path with Person 3 at H0.
EVAL_OUTPUT = PKG_DIR / "eval_results.jsonl"

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
NO_FAULT_STEP_ID = "NONE"  # verdict.predicted_step_id sentinel for a clean trace
NO_FAULT_TYPE = "none"     # verdict.failure_type value for a clean trace
FAILURE_TYPES = ("resource_misuse", "tool_misuse", "routing", "safety")

# --- reward weights (mirror schemas/reward_spec.json §1.4) -------------------
W_LOCALIZATION = 1.0
W_FAILURE_TYPE = 0.3
W_EXPLANATION = 0.5
