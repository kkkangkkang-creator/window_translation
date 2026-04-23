"""User-editable application settings, persisted as JSON."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

APP_NAME = "window_translation"
SETTINGS_FILENAME = "settings.json"


def default_config_dir() -> Path:
    """Return the per-user config directory, creating it if necessary."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppSettings:
    """User-configurable settings for the application.

    Only non-secret values live here; the API key is stored separately via
    :mod:`window_translation.config.secrets`.
    """

    # Translation
    provider: str = "openai"  # "openai" | "stub"
    model: str = "gpt-4o-mini"
    target_language: str = "Korean"
    # OCR
    ocr_languages: str = "eng+jpn+chi_sim"  # Tesseract language codes
    tesseract_cmd: str = ""  # Optional explicit path to tesseract binary
    # UX
    hotkey: str = "<ctrl>+<shift>+t"  # pynput format
    overlay_font_size: int = 14
    overlay_opacity: float = 0.92
    # Region pin mode
    pin_mode_interval_ms: int = 1500
    pin_mode_change_threshold: int = 5  # perceptual-hash distance

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_settings(path: Path | None = None) -> AppSettings:
    """Load settings from disk; returns defaults if missing or invalid."""
    path = path or (default_config_dir() / SETTINGS_FILENAME)
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    if not isinstance(raw, dict):
        return AppSettings()
    return AppSettings.from_dict(raw)


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    """Persist settings atomically to disk."""
    path = path or (default_config_dir() / SETTINGS_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
