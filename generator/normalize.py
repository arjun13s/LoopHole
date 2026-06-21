"""Future raw-trace normalization hook."""

from __future__ import annotations


def normalize_trace(raw_trace: dict) -> dict:
    """Normalize a live worker trace into one-span-per-tool ActionSpans.

    TODO: When live workers are enabled, split any raw turn that contains
    multiple tool calls into separate ActionSpans before fault planting.
    The deterministic planter and validator operate only on normalized traces.
    """
    raise NotImplementedError("live worker trace normalization is not implemented yet")
