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
