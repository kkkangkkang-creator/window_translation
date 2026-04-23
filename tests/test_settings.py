"""Tests for :mod:`window_translation.config.settings`."""

from __future__ import annotations

import json
from pathlib import Path

from window_translation.config.settings import (
    AppSettings,
    load_settings,
    save_settings,
)


def test_defaults_round_trip(tmp_path: Path) -> None:
    settings = AppSettings()
    path = tmp_path / "settings.json"
    save_settings(settings, path)
    assert path.exists()

    loaded = load_settings(path)
    assert loaded == settings


def test_load_missing_returns_defaults(tmp_path: Path) -> None:
    loaded = load_settings(tmp_path / "does_not_exist.json")
    assert loaded == AppSettings()


def test_load_invalid_json_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_settings(path) == AppSettings()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"provider": "stub", "not_a_setting": 123}),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded.provider == "stub"
