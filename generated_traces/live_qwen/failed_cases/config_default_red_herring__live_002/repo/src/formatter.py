from __future__ import annotations

from .config_loader import load_config


def render_title(raw_config: dict[str, str] | None = None) -> str:
    config = load_config(raw_config)
    title = config["title"].strip().title()
    separator = config["separator"]
    return f"{separator} {title} {separator}"
