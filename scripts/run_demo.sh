#!/usr/bin/env bash
# run_demo.sh — Person 3's end-to-end demo orchestration.
#
#   ./scripts/run_demo.sh            # MOCK: render the dashboard on bundled fixtures (works today, no HUD)
#   ./scripts/run_demo.sh --mock     # explicit mock
#   ./scripts/run_demo.sh --tui      # interactive Textual TUI on bundled fixtures (needs a real terminal)
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

render_tui() {
  echo ">> [tui] launching interactive dashboard on bundled fixtures"
  # No --render -> __main__ launches the Textual TUI (needs a real terminal;
  # falls back to the static render if Textual is absent or stdout isn't a TTY).
  "$DASH_PY" -m dashboard --mock
}

# Render base-vs-trained from an EXISTING results dir — the decoupled seam: drop
# Person 2's two HUD eval_results files in a dir and render, no HUD on this side.
# Accepts either eval_results.<tag>.jsonl (base_eval/live_eval convention) or
# <tag>.jsonl (run_demo --real convention). Verdicts/traces are optional.
render_from() {
  local dir="${1:?usage: run_demo.sh --from <results_dir>}"
  local base trained
  base="$dir/eval_results.base.jsonl";       [ -f "$base" ]    || base="$dir/base.jsonl"
  trained="$dir/eval_results.trained.jsonl"; [ -f "$trained" ] || trained="$dir/trained.jsonl"
  [ -f "$base" ] || { echo "missing base eval_results in $dir (run scripts/money_shot_eval.sh first)" >&2; exit 1; }

  # Base is required; trained is OPTIONAL — money_shot_eval.sh produces base-only
  # until a trained slug exists, and the dashboard renders trained as "pending".
  local results=("$base")
  [ -f "$trained" ] && results+=("$trained") || echo ">> [from] no trained eval_results — rendering base-only (trained pending)"

  local extra=()
  for v in "$dir/verdicts.base.jsonl" "$dir/verdicts.trained.jsonl" "$dir/verdicts.jsonl"; do
    [ -f "$v" ] && extra+=(--verdicts "$v") && break
  done
  [ -d "$dir/traces" ] && extra+=(--traces "$dir/traces")
  [ -n "${LOOP_AUDITOR_TRACES:-}" ] && [ -d "$LOOP_AUDITOR_TRACES" ] && extra+=(--traces "$LOOP_AUDITOR_TRACES")

  echo ">> [from] rendering dashboard from $dir"
  "$DASH_PY" -m dashboard --render --results "${results[@]}" "${extra[@]}"
}

render_real() {
  # --- REAL PATH: produce the HUD eval, then render. ---
  #
  # The eval driver is Person 2's scripts/money_shot_eval.sh — the SINGLE source
  # of truth for running eval_harness.run_eval per model (it loads .env, awaits
  # the async run_eval with asyncio.run, and writes the dashboard-named files
  # results/eval_results.<tag>.jsonl + results/verdicts.<tag>.jsonl over the rich
  # held-out split). We don't reimplement it here — we invoke it and render its
  # output, so there's no second, divergent eval path to keep in sync.
  #
  #   ./scripts/run_demo.sh --real                       # slugs from .env
  #   ./scripts/run_demo.sh --real BASE_SLUG             # base only
  #   ./scripts/run_demo.sh --real BASE_SLUG TRAINED_SLUG
  echo ">> [real] producing eval via scripts/money_shot_eval.sh"
  "$REPO_ROOT/scripts/money_shot_eval.sh" "$@"
  render_from "$RESULTS_DIR"
}

case "$MODE" in
  --mock|"") render_mock ;;
  --tui)     render_tui ;;
  --from)    render_from "${2:?usage: $0 --from <results_dir>}" ;;
  --real)    render_real "${@:2}" ;;
  *) echo "usage: $0 [--mock|--tui|--from <dir>|--real]" >&2; exit 2 ;;
esac
