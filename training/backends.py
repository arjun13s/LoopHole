"""Pluggable inference backends for the auditor.

`DummyBackend` runs the whole base-eval pipeline with no GPU/network (tests, mocks).
`ModalBackend` calls a Modal-hosted vLLM OpenAI-compatible endpoint; `openai` is
lazy-imported so the pure pipeline imports cleanly without it installed.
"""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class InferenceBackend(Protocol):
    def complete(self, messages: list[dict], *, max_tokens: int = 512) -> tuple[str, int]:
        """Return (assistant_text, completion_tokens) for one chat completion."""
        ...


class DummyBackend:
    """Deterministic backend that replays canned outputs in call order.

    `outputs` is a list of verdict dicts or raw strings; each `complete()` returns
    the next one (cycling). Used to drive/test the pipeline without a model.
    """

    def __init__(self, outputs: list):
        self._outputs = list(outputs)
        self._i = 0
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], *, max_tokens: int = 512) -> tuple[str, int]:
        if not self._outputs:
            raise ValueError("DummyBackend has no outputs to return")
        self.calls.append(messages)
        out = self._outputs[self._i % len(self._outputs)]
        self._i += 1
        text = out if isinstance(out, str) else json.dumps(out)
        return text, max(1, len(text.split()))


class ModalBackend:
    """Auditor backend over a Modal vLLM OpenAI-compatible endpoint.

    base_url like ``https://<workspace>--loophole-vllm-serve.modal.run/v1``.
    """

    def __init__(self, base_url: str, model: str, *, api_key: str = "EMPTY",
                 temperature: float = 0.0, timeout: float = 120.0):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, messages: list[dict], *, max_tokens: int = 512) -> tuple[str, int]:
        from openai import OpenAI  # lazy: only needed for the real backend

        client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        resp = client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=max_tokens, temperature=self.temperature
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return text, int(getattr(usage, "completion_tokens", 0) or 0)
