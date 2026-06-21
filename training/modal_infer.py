"""Modal app: serve base Qwen2.5-7B-Instruct via vLLM (OpenAI-compatible).

This is the REAL backend behind `ModalBackend` (training/backends.py). It is the
ONLY piece that needs GPUs + your Modal token, so it's wired last; the rest of the
b1 pipeline (scoring, base_eval, DummyBackend) is fully built and tested on mocks.

!!! VERIFY against current Modal docs before `modal deploy` (API names drift across
versions). Confirm: (1) `gpu=` value format ("A100-80GB"), (2) `@modal.web_server`
vs asgi for serving, (3) the idle-timeout kwarg name (`scaledown_window` in recent
Modal; older: `container_idle_timeout`), (4) the pinned vllm version. Run:
    modal deploy training/modal_infer.py
Then point ModalBackend at the printed URL:
    base_url = "https://<workspace>--loophole-base-vllm-serve.modal.run/v1"

Secrets: set your Modal token yourself (`modal token new`) — never committed here.
Qwen2.5-7B-Instruct is open-weight (no HF gating), so no HF token is required.
"""

from __future__ import annotations

import os
import subprocess

import modal

MODEL_NAME = os.environ.get("LOOP_AUDITOR_MODEL", "Qwen/Qwen2.5-7B-Instruct")
VLLM_PORT = 8000
GPU = "A100-80GB"  # Qwen2.5-7B + vLLM fits comfortably; cheaper than H100.

# Persisted HF weights cache so the model is downloaded once, not per cold start.
hf_cache = modal.Volume.from_name("loophole-hf-cache", create_if_missing=True)

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.6.6", "huggingface_hub[hf_transfer]==0.26.2")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})
)

app = modal.App("loophole-base-vllm")


@app.function(
    image=vllm_image,
    gpu=GPU,
    volumes={"/root/.cache/huggingface": hf_cache},
    timeout=30 * 60,
    scaledown_window=5 * 60,  # VERIFY kwarg name for your Modal version
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=15 * 60)
def serve() -> None:
    """Launch vLLM's OpenAI-compatible server; exposes /v1/chat/completions."""
    # List form, no shell: MODEL_NAME comes from an env var, so this avoids any
    # shell-metacharacter / command-injection risk.
    subprocess.Popen([
        "vllm", "serve", MODEL_NAME,
        "--host", "0.0.0.0", "--port", str(VLLM_PORT),
        "--served-model-name", MODEL_NAME,
        "--max-model-len", "8192",
    ])
