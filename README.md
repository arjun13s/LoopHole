# LoopHole

> _A short description of what LoopHole does goes here._

## Getting started

```bash
git clone https://github.com/arjun13s/LoopHole.git
cd LoopHole
```

## Self-improvement CLI

Install the terminal tool from a checkout:

```bash
python -m pip install -e .
```

Or run it directly from GitHub:

```bash
uvx --from git+https://github.com/arjun13s/LoopHole.git loop-auditor --split heldout --report report.md
```

Local checkout usage is the same one-liner:

```bash
loop-auditor --split heldout --report report.md
```

By default, `loop-auditor` calls `loop_auditor_env.eval_harness.run_eval`, which runs the HUD
auditor agent and writes `eval_results.jsonl` plus `verdicts.jsonl`; the CLI then analyzes those
artifacts. The explicit form is also available:

```bash
loop-auditor run --split heldout --model-tag base --out improvement_records.jsonl --report report.md
```

If you already have eval artifacts, use analyze-only mode:

```bash
python -m self_improve analyze \
  --results envs/loop_auditor_env/eval_results.jsonl \
  --verdicts envs/loop_auditor_env/verdicts.jsonl \
  --out improvement_records.jsonl \
  --report
```

Agents that prefer MCP can launch the stdio server:

```bash
loop-auditor-self-improve-mcp
```

It exposes `classify_run`, `analyze_files`, and `markdown_report`. The analyzer is eval-time only:
the `run` command invokes the HUD eval agent upstream, while the analysis layer reads
`eval_results.jsonl` plus `verdicts.jsonl`, never calls a model itself, and never touches reward
semantics.

## Stop-and-resume supervisor demo

For the live-loop behavior, use `supervise`. It runs a coding CLI, watches tests fail, then either:

- `baseline`: resumes the coding agent with its own logs/context
- `assisted`: asks an eval agent for a diagnosis, then resumes the coding agent with that hint
- `both`: runs both and writes a side-by-side comparison

Deterministic demo:

```bash
loop-auditor supervise \
  --task self_improve/fixtures/supervisor_demo/task.json \
  --agent "{python} {package}/fixtures/supervisor_demo/fake_coding_agent.py" \
  --mode both \
  --out-dir supervision_runs/demo
```

Outputs:

```text
supervision_runs/demo/baseline/transcript.md
supervision_runs/demo/assisted/transcript.md
supervision_runs/demo/side_by_side.md
```

To wrap a real coding CLI, replace `--agent` with the command to run. The supervisor passes:
`LOOP_AUDITOR_REPO`, `LOOP_AUDITOR_TASK_FILE`, `LOOP_AUDITOR_ATTEMPT`,
`LOOP_AUDITOR_HINT_FILE`, and `LOOP_AUDITOR_MODE`.

To use a real eval-agent command instead of the built-in deterministic demo evaluator, pass
`--eval-agent "...command..."`. The eval command receives `LOOP_AUDITOR_EVAL_CONTEXT`,
`LOOP_AUDITOR_REPO`, and `LOOP_AUDITOR_TASK_FILE` and should print a diagnosis without editing
files.

## License

[MIT](./LICENSE)
