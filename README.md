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

## License

[MIT](./LICENSE)
