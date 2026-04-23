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


def test_new_overlay_and_prompt_fields_round_trip(tmp_path: Path) -> None:
    settings = AppSettings(
        system_prompt="Translate into {target_language} with flair.",
        overlay_font_family="Consolas",
        overlay_font_size=18,
        overlay_line_spacing=160,
    )
    path = tmp_path / "settings.json"
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.system_prompt == "Translate into {target_language} with flair."
    assert loaded.overlay_font_family == "Consolas"
    assert loaded.overlay_font_size == 18
    assert loaded.overlay_line_spacing == 160


def test_default_new_fields() -> None:
    s = AppSettings()
    assert s.system_prompt == ""  # empty → use built-in default
    assert s.overlay_font_family == ""  # empty → Qt default
    assert s.overlay_line_spacing >= 100
    # 새로 추가된 OCR 엔진 설정의 기본값.
    assert s.ocr_engine == "tesseract"


def test_ocr_engine_round_trip(tmp_path: Path) -> None:
    s = AppSettings(ocr_engine="paddleocr")
    path = tmp_path / "settings.json"
    save_settings(s, path)
    assert load_settings(path).ocr_engine == "paddleocr"
