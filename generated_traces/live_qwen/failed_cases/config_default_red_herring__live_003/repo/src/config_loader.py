from __future__ import annotations


DEFAULTS = {
    "title": "untitled",
    "separator": "-",
}


def load_config(raw: dict[str, str] | None = None) -> dict[str, str]:
    config = DEFAULTS.copy()
    if raw:
        config.update(raw)
    return config
