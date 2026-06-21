# `dashboard` — Loop-Auditor TUI dashboard (Person 3)

The demo **money-shot**: base-vs-trained auditor on held-out traces, trace replay with the
planted-failure step highlighted, verdict drill-down, and an honest auditor-token-cost chart.

**Rich static-render is the primary surface** — it prints to stdout, so it is fully visible
**inside Claude Code / Codex / any CLI agent** and screenshots cleanly. An interactive Textual
TUI is a *stretch* layer (needs a real terminal; not visible inside agent panes).

## Run

```bash
# from the repo root
python3 -m venv dashboard/.venv
dashboard/.venv/bin/pip install rich jsonschema           # + pytest for tests
dashboard/.venv/bin/python -m dashboard --render --mock   # bundled demo fixtures

# or the one-liner orchestration:
./scripts/run_demo.sh --mock
```

### Interactive TUI (demo surface)

Needs a real terminal (not visible inside a CLI agent pane). Install the extra,
then launch with no `--render` flag:

```bash
dashboard/.venv/bin/pip install -e '.[interactive]'   # or: pip install 'textual>=0.60'
dashboard/.venv/bin/python -m dashboard               # opens the TUI on bundled fixtures
# or:
./scripts/run_demo.sh --tui
```

Keys: `↑/↓` (or `j`/`k`) move between Summary and traces · `s` jump to Summary ·
`enter` scroll the detail pane to top · `q` quit. The TUI reuses the exact same
Rich panels as the static render, so the two surfaces look identical.

Real data (after Person 2's HUD eval is wired):

```bash
dashboard/.venv/bin/python -m dashboard --render \
  --results results/base.jsonl results/trained.jsonl \
  --traces /path/to/heldout/traces/ \
  --verdicts results/verdicts.jsonl      # optional sidecar
```

## Data contract (what it reads)

| Input | Source | Required? | Schema |
|---|---|---|---|
| eval-result JSONL | Person 2 `eval_harness` (`config.EVAL_OUTPUT`) | yes | `schemas/eval_result.json` |
| verdict sidecar JSONL | Person 2 (proposed — see `CONTRACT_verdict_sidecar.md`) | **optional** | `schemas/verdict.json` + `{run_id, model}` |
| trace JSON | Person 1 held-out set (bundled mocks until then) | yes | `schemas/trace.json` |

The dashboard is a **standalone, read-only consumer** — it has **no Python dependency on
`loop_auditor_env`** and never edits another stream's files (own `pyproject.toml`, own venv,
nested `.gitignore`). Every record is validated against the frozen schemas before rendering.

## Tests

```bash
cd dashboard && .venv/bin/python -m pytest -q
```

Pure layers (`model.py` aggregation/deltas, `loader.py` schema validation) are covered;
`render.py` has a recorded-console smoke test asserting the money-shot facts are present.
