"""Modal entrypoint for live coding-model trace generation.

Usage:
    modal run trace_harness/live_modal_worker.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct --max-successes 5

The live model only generates clean base traces. Deterministic injectors are
then applied to each clean trace outside the model loop.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import modal


HOURS = 3600
REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = REPO_ROOT / "generated_traces" / "live_qwen"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "accelerate",
        "pytest",
        "torch",
        "transformers",
        "sentencepiece",
        "protobuf",
    )
    .add_local_python_source("trace_harness")
)

hf_cache = modal.Volume.from_name("loophole-hf-cache", create_if_missing=True)
app = modal.App("loophole-live-trace-worker")


class TransformersWorker:
    def __init__(self, model_id: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            trust_remote_code=True,
        )

    def complete(self, messages: list[dict[str, str]]) -> str:
        import torch

        if hasattr(self.tokenizer, "apply_chat_template"):
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            text = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=700,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = out[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


@app.function(
    image=image,
    gpu="A100",
    timeout=2 * HOURS,
    volumes={"/root/.cache/huggingface": hf_cache},
    secrets=[modal.Secret.from_name("huggingface-secret")],
)
def generate_clean_live_traces(model_id: str, max_successes: int, attempts_per_template: int) -> list[dict[str, Any]]:
    from trace_harness.live_worker_loop import run_live_trace_batch

    worker = TransformersWorker(model_id)
    results = run_live_trace_batch(
        model=worker,
        output_root="/tmp/loophole_live",
        max_successes=max_successes,
        attempts_per_template=attempts_per_template,
    )
    packed = []
    for result in results:
        item = result.__dict__.copy()
        if result.case_dir:
            item["bundle"] = _pack_dir(Path(result.case_dir))
        if result.success and result.ground_truth_path:
            item["ground_truth"] = json.loads(Path(result.ground_truth_path).read_text())
        packed.append(item)
    return packed


@app.local_entrypoint()
def main(
    model_id: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
    max_successes: int = 5,
    attempts_per_template: int = 4,
) -> None:
    results = generate_clean_live_traces.remote(model_id, max_successes, attempts_per_template)
    if LIVE_ROOT.exists():
        shutil.rmtree(LIVE_ROOT)
    (LIVE_ROOT / "clean_cases").mkdir(parents=True)
    (LIVE_ROOT / "clean_ground_truth").mkdir(parents=True)
    (LIVE_ROOT / "failed_cases").mkdir(parents=True)
    summary = []
    for result in results:
        summary.append({k: v for k, v in result.items() if k not in {"bundle", "ground_truth"}})
        if not result.get("success"):
            if result.get("bundle"):
                _unpack_dir(result["bundle"], LIVE_ROOT / "failed_cases" / result["case_id"])
            continue
        case_id = result["case_id"]
        case_dir = LIVE_ROOT / "clean_cases" / case_id
        _unpack_dir(result["bundle"], case_dir)
        _write_json(LIVE_ROOT / "clean_ground_truth" / f"{case_id}.json", result["ground_truth"])
    _write_json(LIVE_ROOT / "summary.json", {"model_id": model_id, "results": summary})
    _apply_injectors_to_live_clean_cases()
    print(json.dumps(summary, indent=2))
    print(f"wrote live traces to {LIVE_ROOT}")


def _apply_injectors_to_live_clean_cases() -> None:
    from trace_harness.injectors import INJECTORS
    from trace_harness.validator import load_trace_jsonl, validate_case_dir

    out_cases = LIVE_ROOT / "labeled_cases"
    out_gt = LIVE_ROOT / "labeled_ground_truth"
    out_cases.mkdir(parents=True, exist_ok=True)
    out_gt.mkdir(parents=True, exist_ok=True)
    for clean_dir in sorted((LIVE_ROOT / "clean_cases").iterdir()):
        if not clean_dir.is_dir():
            continue
        trace = load_trace_jsonl(clean_dir / "trace.jsonl")
        base = {
            "case_id": clean_dir.name,
            "task": (clean_dir / "prompt.md").read_text(),
            "trace": trace,
            "metadata": _infer_metadata(trace),
        }
        for fault_type, injector in INJECTORS.items():
            mutated, gt = injector(base)
            case_dir = out_cases / clean_dir.name / fault_type
            if case_dir.exists():
                shutil.rmtree(case_dir)
            shutil.copytree(clean_dir, case_dir)
            _write_trace(case_dir / "trace.jsonl", mutated["trace"])
            payload = gt.to_json()
            payload["case_id"] = f"{clean_dir.name}__{fault_type}"
            gt_path = out_gt / f"{clean_dir.name}__{fault_type}.json"
            _write_json(gt_path, payload)
            validate_case_dir(case_dir, gt_path)


def _infer_metadata(trace: list[dict[str, Any]]) -> dict[str, str]:
    failing_test = next(step for step in trace if step["tool_name"] == "run_tests" and step["result"]["status"] == "error")
    final_test = next(step for step in reversed(trace) if step["tool_name"] == "run_tests" and step["result"]["status"] == "ok")
    submit = next(step for step in reversed(trace) if step["tool_name"] == "submit")
    failing_idx = trace.index(failing_test)
    inspect = next(step for step in trace[failing_idx + 1:] if step["tool_name"] == "read_file")
    fix = next(step for step in trace[failing_idx + 1:] if step["tool_name"] == "write_file")
    correct_path = fix["args"]["path"]
    wrong_path = _neighbor_wrong_path(correct_path)
    return {
        "inspect_step_id": inspect["step_id"],
        "failing_test_step_id": failing_test["step_id"],
        "final_test_step_id": final_test["step_id"],
        "fix_step_id": fix["step_id"],
        "submit_step_id": submit["step_id"],
        "correct_edit_path": correct_path,
        "wrong_edit_path": wrong_path,
        "failure_output_ref": failing_test["result"]["stdout_ref"],
        "large_context_path": "repo/README.md",
    }


def _neighbor_wrong_path(correct_path: str) -> str:
    path = Path(correct_path)
    candidate = path.with_name(path.stem + "_helpers" + path.suffix)
    return str(candidate)


def _pack_dir(path: Path) -> dict[str, str]:
    out = {}
    for item in path.rglob("*"):
        if item.is_file():
            out[str(item.relative_to(path))] = item.read_text(encoding="utf-8", errors="replace")
    return out


def _unpack_dir(bundle: dict[str, str], dst: Path) -> None:
    for rel, text in bundle.items():
        path = dst / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _write_trace(path: Path, trace: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in trace:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
