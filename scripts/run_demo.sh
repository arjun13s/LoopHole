#!/usr/bin/env bash
# run_demo.sh — Person 3's end-to-end demo orchestration.
#
#   ./scripts/run_demo.sh            # MOCK: render the dashboard on bundled fixtures (works today, no HUD)
#   ./scripts/run_demo.sh --mock     # explicit mock
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

render_tui() {
  echo ">> [tui] launching interactive dashboard on bundled fixtures"
  # No --render -> __main__ launches the Textual TUI (needs a real terminal;
  # falls back to the static render if Textual is absent or stdout isn't a TTY).
  "$DASH_PY" -m dashboard --mock
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

  # Team env (hud-python etc.) — prefer uv if present, else python3.
  TEAM_RUN=(python3)
  command -v uv >/dev/null 2>&1 && TEAM_RUN=(uv run python)

  mkdir -p "$RESULTS_DIR"
  EVAL_OUT="$REPO_ROOT/envs/loop_auditor_env/eval_results.jsonl"

  for pair in "base:$LOOP_AUDITOR_BASE_MODEL" "trained:$LOOP_AUDITOR_TRAINED_MODEL"; do
    tag="${pair%%:*}"; slug="${pair#*:}"
    echo ">> [real] eval ($tag) on $slug"
    LOOP_AUDITOR_MODEL="$slug" "${TEAM_RUN[@]}" -c \
      "from envs.loop_auditor_env import eval_harness as e; e.run_eval(split='heldout', model_tag='$tag')"
    cp "$EVAL_OUT" "$RESULTS_DIR/$tag.jsonl"
  done

  # Optional verdict sidecar (graceful if Person 2 has not added it yet).
  VERDICTS_ARG=()
  [ -f "$RESULTS_DIR/verdicts.jsonl" ] && VERDICTS_ARG=(--verdicts "$RESULTS_DIR/verdicts.jsonl")

  # Trace source for replay: Person 1's held-out set when available, else bundled.
  TRACES="${LOOP_AUDITOR_TRACES:-$REPO_ROOT/dashboard/fixtures/traces}"

  echo ">> [real] rendering dashboard"
  "$DASH_PY" -m dashboard --render \
    --results "$RESULTS_DIR/base.jsonl" "$RESULTS_DIR/trained.jsonl" \
    --traces "$TRACES" "${VERDICTS_ARG[@]}"
}

case "$MODE" in
  --mock|"") render_mock ;;
  --tui)     render_tui ;;
  --real)    render_real ;;
  *) echo "usage: $0 [--mock|--tui|--real]" >&2; exit 2 ;;
esac
