#!/usr/bin/env bash
# run_demo.sh — Person 3's end-to-end demo orchestration.
#
#   ./scripts/run_demo.sh            # MOCK: render the dashboard on bundled fixtures (works today, no HUD)
#   ./scripts/run_demo.sh --mock     # explicit mock
#   ./scripts/run_demo.sh --from DIR # render an existing results dir (eval_results.{base,trained}.jsonl)
#   ./scripts/run_demo.sh --real     # REAL: run Person 2's eval harness for base+trained, then render
#
# Conflict-free by construction: this script only INVOKES other streams through
# their documented CLI/JSON contracts — it never imports or edits their source.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Dashboard runs in its own venv (decoupled package); fall back to python3.
DASH_PY="$REPO_ROOT/dashboard/.venv/bin/python"
[ -x "$DASH_PY" ] || DASH_PY="python3"

MODE="${1:---mock}"
RESULTS_DIR="$REPO_ROOT/results"

render_mock() {
  echo ">> [mock] rendering dashboard on bundled fixtures"
  "$DASH_PY" -m dashboard --render --mock
}

# Render base-vs-trained from an EXISTING results dir — the decoupled seam: drop
# Person 2's two HUD eval_results files in a dir and render, no HUD on this side.
# Accepts either eval_results.<tag>.jsonl (base_eval/live_eval convention) or
# <tag>.jsonl (run_demo --real convention). Verdicts/traces are optional.
render_from() {
  local dir="${1:?usage: run_demo.sh --from <results_dir>}"
  local base trained
  base="$dir/eval_results.base.jsonl";    [ -f "$base" ]    || base="$dir/base.jsonl"
  trained="$dir/eval_results.trained.jsonl"; [ -f "$trained" ] || trained="$dir/trained.jsonl"
  [ -f "$base" ]    || { echo "missing base eval_results in $dir" >&2; exit 1; }
  [ -f "$trained" ] || { echo "missing trained eval_results in $dir" >&2; exit 1; }

  local extra=()
  for v in "$dir/verdicts.base.jsonl" "$dir/verdicts.trained.jsonl" "$dir/verdicts.jsonl"; do
    [ -f "$v" ] && extra+=(--verdicts "$v") && break
  done
  [ -d "$dir/traces" ] && extra+=(--traces "$dir/traces")
  [ -n "${LOOP_AUDITOR_TRACES:-}" ] && [ -d "$LOOP_AUDITOR_TRACES" ] && extra+=(--traces "$LOOP_AUDITOR_TRACES")

  echo ">> [from] rendering dashboard from $dir"
  "$DASH_PY" -m dashboard --render --results "$base" "$trained" "${extra[@]}"
}

render_real() {
  # --- REAL PATH (gated; needs Person 2's HUD eval wired + base/trained slugs) ---
  #
  # Contract with Person 2 (envs/loop_auditor_env/eval_harness.py):
  #   - eval_harness.run_eval(split, model_tag) runs the auditor over the held-out
  #     split and writes config.EVAL_OUTPUT (a JSONL of eval_result records).
  #   - The MODEL is selected by env var LOOP_AUDITOR_MODEL (see config.py).
  #
  # We therefore run it twice with the two slugs, capturing each output per model.
  : "${LOOP_AUDITOR_BASE_MODEL:?set LOOP_AUDITOR_BASE_MODEL (base auditor slug)}"
  : "${LOOP_AUDITOR_TRAINED_MODEL:?set LOOP_AUDITOR_TRAINED_MODEL (HUD-forked trained slug)}"

  # run_eval(split) requires the env to have LOADED that split (config.DATASET);
  # it raises if they disagree. The real audit set is Person 1's rich held-out
  # split. Override both together via LOOP_AUDITOR_SPLIT if needed.
  SPLIT="${LOOP_AUDITOR_SPLIT:-rich_heldout}"

  # Team env (hud-python etc.) — prefer uv if present, else python3.
  TEAM_RUN=(python3)
  command -v uv >/dev/null 2>&1 && TEAM_RUN=(uv run python)

  mkdir -p "$RESULTS_DIR"
  EVAL_OUT="$REPO_ROOT/envs/loop_auditor_env/eval_results.jsonl"

  for pair in "base:$LOOP_AUDITOR_BASE_MODEL" "trained:$LOOP_AUDITOR_TRAINED_MODEL"; do
    tag="${pair%%:*}"; slug="${pair#*:}"
    echo ">> [real] eval ($tag) on $slug (split=$SPLIT)"
    LOOP_AUDITOR_MODEL="$slug" LOOP_AUDITOR_DATASET="$SPLIT" "${TEAM_RUN[@]}" -c \
      "from envs.loop_auditor_env import eval_harness as e; e.run_eval(split='$SPLIT', model_tag='$tag')"
    cp "$EVAL_OUT" "$RESULTS_DIR/eval_results.$tag.jsonl"
  done

  # Optional verdict sidecar (graceful if Person 2 has not added it yet).
  VERDICTS_ARG=()
  [ -f "$RESULTS_DIR/verdicts.jsonl" ] && VERDICTS_ARG=(--verdicts "$RESULTS_DIR/verdicts.jsonl")

  # Trace source for replay: Person 1's held-out set when available, else bundled.
  TRACES="${LOOP_AUDITOR_TRACES:-$REPO_ROOT/dashboard/fixtures/traces}"

  echo ">> [real] rendering dashboard"
  "$DASH_PY" -m dashboard --render \
    --results "$RESULTS_DIR/eval_results.base.jsonl" "$RESULTS_DIR/eval_results.trained.jsonl" \
    --traces "$TRACES" "${VERDICTS_ARG[@]}"
}

case "$MODE" in
  --mock|"") render_mock ;;
  --from)    render_from "${2:?usage: $0 --from <results_dir>}" ;;
  --real)    render_real ;;
  *) echo "usage: $0 [--mock|--from <dir>|--real]" >&2; exit 2 ;;
esac
