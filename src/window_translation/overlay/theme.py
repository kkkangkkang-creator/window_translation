"""Color palettes for the overlay and settings UI.

Centralising theme colors makes it easy to toggle between light and dark
(or add new themes) without touching widget code.
"""

from __future__ import annotations

from typing import Dict


LIGHT: Dict[str, str] = {
    "window_bg":       "#f7f7fa",
    "window_fg":       "#1a1a1f",
    "title_fg":        "#4a5568",
    "close_fg":        "#6b7280",
    "close_fg_hover":  "#111827",
    "source_bg":       "#ffffff",
    "source_fg":       "#4b5563",
    "source_border":   "#d1d5db",
    "trans_bg":        "#ffffff",
    "trans_fg":        "#0f172a",
    "trans_border":    "#cbd5e1",
}


DARK: Dict[str, str] = {
    "window_bg":       "#191920",
    "window_fg":       "#ebebf0",
    "title_fg":        "#b0b8c8",
    "close_fg":        "#dddddd",
    "close_fg_hover":  "#ffffff",
    "source_bg":       "#1a1a1f",
    "source_fg":       "#9fb3c8",
    "source_border":   "#2a2a33",
    "trans_bg":        "#15151a",
    "trans_fg":        "#f1f1f4",
    "trans_border":    "#2a2a33",
}


THEMES = {"light": LIGHT, "dark": DARK}


def get_theme(name: str) -> Dict[str, str]:
    """Return the requested theme, falling back to light for unknown names."""
    return THEMES.get((name or "").lower(), LIGHT)


__all__ = ["LIGHT", "DARK", "THEMES", "get_theme"]
