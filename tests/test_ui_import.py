"""Headless smoke tests for the optional GTK UI module."""

from __future__ import annotations

import importlib

import pytest


def test_window_module_imports_without_initialising_gtk() -> None:
    module = importlib.import_module("uthyagent.ui.window")
    assert hasattr(module, "UthyWindow")


def test_brand_asset_theme_palettes_and_provider_indicator_are_available() -> None:
    from pathlib import Path

    module = importlib.import_module("uthyagent.ui.window")
    logo = Path(module.__file__).parent.parent / "resources" / "app-logo.png"
    assert logo.is_file()
    assert "#f2f6f4" in module.CSS_LIGHT
    assert "#0d1512" in module.CSS
    assert "Remote inference" in module.__doc__ or hasattr(module.UthyWindow, "set_provider_status")


def test_missing_gi_fails_only_when_window_is_created(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("uthyagent.ui.window")
    real_import = __import__

    def blocked_import(name: str, *args: object, **kwargs: object):
        if name == "gi":
            raise ImportError("GI intentionally unavailable in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    with pytest.raises(RuntimeError, match="GTK4/PyGObject"):
        module.UthyWindow()
