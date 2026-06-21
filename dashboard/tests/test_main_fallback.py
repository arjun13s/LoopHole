"""The interactive entry point must degrade to the static render when the
interactive module can't be imported (missing OR broken Textual install)."""

from __future__ import annotations

import sys

from dashboard import __main__ as main_mod


def test_main_falls_back_to_static_when_interactive_import_fails(monkeypatch, capsys):
    # Remove the already-imported interactive module from sys.modules so the
    # lazy import inside main() re-executes and can be intercepted.
    monkeypatch.delitem(sys.modules, "dashboard.interactive", raising=False)

    # Inject a broken sentinel so the re-import raises ImportError.
    import types
    broken = types.ModuleType("dashboard.interactive")

    def _boom(*_a, **_kw):
        raise ImportError("simulated broken textual install")

    broken.run_interactive = _boom
    # Replace with a module whose import itself raises by using a finder.
    import importlib.abc
    import importlib.machinery

    class _BrokenFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "dashboard.interactive":
                raise ImportError("simulated broken textual install")
            return None

    monkeypatch.setattr(sys, "meta_path", [_BrokenFinder()] + sys.meta_path)

    # Pretend we're at an interactive terminal so main() tries the TUI path.
    monkeypatch.setattr(main_mod.sys.stdout, "isatty", lambda: True)

    rc = main_mod.main(["--mock"])  # no --render, isatty True -> interactive branch

    assert rc == 0
    out = capsys.readouterr().out
    assert "LOOPHOLE" in out  # static render banner proves the fallback ran
