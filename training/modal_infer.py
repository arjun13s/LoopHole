"""Modal app: serve base Qwen2.5-7B-Instruct via vLLM (OpenAI-compatible).

The model weights are baked into the IMAGE at build time (`run_function`), so the
runtime cold start has nothing to download and vLLM binds port 8000 well within
`startup_timeout`. (The earlier 1-hour hangs were a startup timeout: a 15 GB runtime
download + slow init exceeded the 15-min window.)

Verified against Modal 1.5.0. Deploy:
    training/.venv/bin/modal deploy training/modal_infer.py
Then point ModalBackend / run_base_eval --base-url at the printed
…--loophole-base-vllm-serve.modal.run/v1 URL.

Set your Modal token yourself (`modal token set …`) — never committed here.
Qwen2.5-7B-Instruct is open-weight (no HF gating).
"""

from __future__ import annotations

import subprocess

import modal

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"  # static: baked into the image at build
VLLM_PORT = 8000
GPU = "A100-80GB"  # Qwen2.5-7B + vLLM fits comfortably; cheaper than H100.


def _download_model() -> None:
    """Pre-download weights at build so they're committed into the image layer."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_NAME)


vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.21.0", "hf_transfer", "huggingface_hub")  # vllm pin: adjustable
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .run_function(_download_model)  # bakes the 15 GB of weights into the image
)

app = modal.App("loophole-base-vllm")


@app.function(image=vllm_image, gpu=GPU, timeout=30 * 60, scaledown_window=5 * 60)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=25 * 60)
def serve() -> None:
    """Launch vLLM's OpenAI server; weights load from the image (no download)."""
    # Inherit stdout/stderr so vLLM startup logs are visible in `modal app logs`.
    subprocess.Popen([
        "vllm", "serve", MODEL_NAME,
        "--host", "0.0.0.0", "--port", str(VLLM_PORT),
        "--served-model-name", MODEL_NAME,
        "--max-model-len", "8192",
    ])
