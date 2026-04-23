"""User-editable application settings, persisted as JSON."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

APP_NAME = "window_translation"
SETTINGS_FILENAME = "settings.json"
HISTORY_FILENAME = "history.sqlite3"


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


def default_history_path() -> Path:
    return default_config_dir() / HISTORY_FILENAME


@dataclass
class AppSettings:
    """User-configurable settings for the application.

    Only non-secret values live here; the API key is stored separately via
    :mod:`window_translation.config.secrets`.
    """

    # Translation
    provider: str = "openai"  # "openai" | "openrouter" | "groq" | "ollama" | "lm-studio" | "azure-openai" | "custom" | "stub"
    model: str = "gpt-4o-mini"
    endpoint: str = ""  # Empty = use provider preset default
    target_language: str = "Korean"
    # Custom system prompt. Empty = use the built-in default.
    # Supports {target_language} and {source_language} placeholders.
    system_prompt: str = ""
    # History / cache
    history_enabled: bool = True
    # How many recent translations to inject as few-shot examples for
    # consistency. 0 disables the feature.
    history_recent_context: int = 0
    # OCR
    ocr_engine: str = "tesseract"  # "tesseract" | "paddleocr"
    ocr_languages: str = "eng+jpn+chi_sim"  # Tesseract language codes
    tesseract_cmd: str = ""  # Optional explicit path to tesseract binary
    # UX
    hotkey: str = "<ctrl>+<shift>+t"  # pynput format
    theme: str = "light"  # "light" | "dark"
    overlay_font_family: str = ""  # Empty = Qt default
    overlay_font_size: int = 14
    overlay_line_spacing: int = 140  # percent (100 = single spacing)
    overlay_opacity: float = 0.95
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
