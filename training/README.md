# `training` — Modal b1: base-model inference + base-eval baseline (Person 3)

Produces the **`base` baseline** for the base-vs-trained money-shot, **independently of
HUD**: run the base auditor (Qwen2.5-7B) over the held-out traces on Modal, score with the
frozen reward spec, and emit dashboard-ready `eval_results` + `verdicts` JSONL.

Person 2 owns the HUD-trained side (`trained`); this is the genuine **Modal** sponsor
integration *and* a de-risk — we get a real base baseline even if HUD only serves the
trained checkpoint.

## Design (decoupled, mock-first)
| Module | Role | Deps |
|---|---|---|
| `scoring.py` | Pure reward/verdict core — **implements the frozen `schemas/reward_spec.json` directly** (no `hud`/`anthropic` coupling) | stdlib |
| `backends.py` | `InferenceBackend` protocol + `DummyBackend` (tests/mocks, no GPU) + `ModalBackend` (vLLM OpenAI endpoint) | `openai` (lazy, real only) |
| `prompt.py` | Auditor serialization + system prompt (injectable) | stdlib |
| `base_eval.py` | Orchestrator: traces → backend → parse → score → JSONL; validates each record against the frozen `eval_result` schema | `jsonschema` |
| `modal_infer.py` | Modal app serving base Qwen2.5-7B via vLLM (A100-80GB) | `modal`, `vllm` |

The whole pipeline runs/tests with **no GPU, network, or `hud`** via `DummyBackend` — the
real `ModalBackend` swaps in at the same seam.

## Run

```bash
# tests (pure pipeline, no creds):
cd training && ../dashboard/.venv/bin/python -m pytest -q

# real base baseline (after you set the Modal token yourself — never committed):
modal token new
modal deploy training/modal_infer.py        # prints the vLLM base_url
```
```python
from training.backends import ModalBackend
from training.base_eval import run_base_eval
backend = ModalBackend(base_url="https://<workspace>--loophole-base-vllm-serve.modal.run/v1",
                       model="Qwen/Qwen2.5-7B-Instruct")
run_base_eval(traces, backend, model_tag="base", judge=anthropic_judge, out_dir="results")
# -> results/eval_results.base.jsonl + results/verdicts.base.jsonl  (dashboard reads these)
```

## Real run (after `modal deploy training/modal_infer.py`)
```bash
python -m training.run_base_eval \
  --traces dashboard/fixtures/traces \
  --base-url https://<workspace>--loophole-base-vllm-serve.modal.run/v1 \
  --out results            # -> results/eval_results.base.jsonl + verdicts.base.jsonl
```
The trained side comes from Person 2's `run_eval` (HUD); the dashboard reads both.

## Notes / open seams
- **Explanation scoring is DETERMINISTIC by default** — `deterministic_explanation_scorer`
  reuses Person 2's pure `fix_grader.grade_fix` (fix-by-comparison) + `citation_gate.check`,
  so the base baseline is scored byte-identically to the trained side (no LLM judge in the
  loop — cost). An LLM-judge scorer can be injected for *eval-time refinement only*.
- `run_base_eval.py` validates traces against the frozen `trace.json` — it will reject
  Person 1's still-divergent traces (issue #3) loudly rather than silently misscoring.
- **Fair comparison:** `serialize_fn` is injectable so we can match Person 2's HUD
  serialization at real-run time (so base & trained auditors see identical prompts).
- **Verdict schema:** emits main's current format (`"NONE"`/`"none"`). When the
  `agent_traces` change (`fault_present` + `null`) merges, update `scoring.NO_FAULT_*`.
- `modal_infer.py` has a **VERIFY-against-docs** header — confirm Modal's current API
  (`gpu`, `web_server`, `scaledown_window`, vllm pin) before `modal deploy`.
