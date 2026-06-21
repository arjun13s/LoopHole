#!/usr/bin/env bash
# money_shot_eval.sh — produce the dashboard money-shot inputs (Person 3 contract).
#
# Runs eval_harness.run_eval once per model over the rich held-out split and names
# the outputs the dashboard expects:
#   results/eval_results.base.jsonl   + results/verdicts.base.jsonl
#   results/eval_results.trained.jsonl + results/verdicts.trained.jsonl   (if a trained slug is set)
#
# Reads keys/slugs from the gitignored project-root .env. Trained is OPTIONAL:
# if no trained slug is configured, it produces base-only (dashboard renders
# trained as "pending").
#
#   ./scripts/money_shot_eval.sh                 # uses slugs from .env
#   ./scripts/money_shot_eval.sh BASE_SLUG       # base only, explicit slug
#   ./scripts/money_shot_eval.sh BASE_SLUG TRAINED_SLUG
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Load .env (keys + slugs); never printed.
if [ -f .env ]; then set -a; . ./.env; set +a; fi

: "${HUD_API_KEY:?HUD_API_KEY is empty — set it in .env (the HUD gateway key)}"

SPLIT="rich_heldout"
PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

BASE_SLUG="${1:-${LOOP_AUDITOR_BASE_MODEL:-loophole-evalagent}}"
TRAINED_SLUG="${2:-${LOOP_AUDITOR_TRAINED_MODEL:-}}"

EVAL_OUT="$REPO_ROOT/envs/loop_auditor_env/eval_results.jsonl"
VERDICT_OUT="$REPO_ROOT/envs/loop_auditor_env/verdicts.jsonl"
mkdir -p "$REPO_ROOT/results"

run_one() {
  local tag="$1" slug="$2"
  echo ">> [$tag] eval over $SPLIT on slug: $slug"
  # run_eval is async — must be driven with asyncio.run (the bare coroutine never executes).
  LOOP_AUDITOR_MODEL="$slug" LOOP_AUDITOR_DATASET="$SPLIT" "$PY" -c \
    "import asyncio; from envs.loop_auditor_env import eval_harness as e; print('aggregate:', asyncio.run(e.run_eval(split='$SPLIT', model_tag='$tag')))"
  cp "$EVAL_OUT" "$REPO_ROOT/results/eval_results.$tag.jsonl"
  [ -f "$VERDICT_OUT" ] && cp "$VERDICT_OUT" "$REPO_ROOT/results/verdicts.$tag.jsonl"
  echo ">> [$tag] wrote results/eval_results.$tag.jsonl ($(wc -l < "$REPO_ROOT/results/eval_results.$tag.jsonl") records)"
}

run_one base "$BASE_SLUG"

if [ -n "$TRAINED_SLUG" ]; then
  run_one trained "$TRAINED_SLUG"
else
  echo ">> [trained] no trained slug set (LOOP_AUDITOR_TRAINED_MODEL / arg 2) — base-only, dashboard shows trained pending"
fi

echo ">> done. files in results/:"
ls -1 "$REPO_ROOT/results/" | sed 's/^/   /'
