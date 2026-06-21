## a001
model_action:
```json
{
  "tool_name": "read_file",
  "args": {
    "path": "repo/tests/test_report_title.py"
  }
}
```
observation:
```
from src.config_loader import load_config
from src.formatter import render_title


def test_custom_title_rendered():
    assert render_title({"title": "weekly revenue"}) == "- Weekly Revenue -"


def test_default_title_uses_report_label():
    assert render_title({}) == "- Report -"


def test_loader_supplies_default_title():
    assert load_config({})["title"] == "report"


def test_custom_separator_rendered():
    assert render_title({"title": "alerts", "separator": "*"}) == "* Alerts *"
```

## a002
model_action:
```json
{
  "tool_name": "read_file",
  "args": {
    "path": "repo/src/formatter.py"
  }
}
```
observation:
```
from __future__ import annotations

from .config_loader import load_config


def render_title(raw_config: dict[str, str] | None = None) -> str:
    config = load_config(raw_config)
    title = config["title"].strip().title()
    separator = config["separator"]
    return f"{separator} {title} {separator}"
```

## a003
model_action:
```json
{
  "tool_name": "read_file",
  "args": {
    "path": "repo/src/config_loader.py"
  }
}
```
observation:
```
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
```

## a004
model_action:
```json
{
  "tool_name": "write_file",
  "args": {
    "path": "repo/src/formatter.py",
    "content": """
from __future__ import annotations

from .config_loader import load_config


DEFAULTS = {
    \"title\": \"untitled\",
    \"separator\": \"-\",
}


def load_config(raw: dict[str, str] | None = None) -> dict[str, str]:
    config = DEFAULTS.copy()
    if raw:
        config.update(raw)
    return config


def render_title(raw_config: dict[str, str] | None = None) -> str:
    config = load_config(raw_config)
    title = config.get(\"title\", DEFAULTS[\"title\"]).strip().title()
    separator = config.get(\"separator\", DEFAULTS[\"separator\"])
    return f\"{separator} {title} {separator}\"
"""
  }
}
```
observation:
```
submit accepted for files=[]
```

