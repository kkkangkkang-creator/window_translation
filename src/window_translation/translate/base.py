"""Base interface for translation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TranslationError(RuntimeError):
    """Raised when a translator fails to produce a translation."""


class Translator(ABC):
    """Abstract translation backend.

    Concrete implementations are expected to be side-effect free beyond the
    outbound network call and should raise :class:`TranslationError` on
    failure (including HTTP errors, rate-limit exhaustion, and empty
    responses).
    """

    @abstractmethod
    def translate(
        self,
        text: str,
        target_language: str = "Korean",
        source_language: Optional[str] = None,
    ) -> str:
        """Translate ``text`` into ``target_language``.

        Parameters
        ----------
        text:
            Source text (already OCR-cleaned).
        target_language:
            Human-readable name of the target language ("Korean", "English"...).
        source_language:
            Optional hint for the source language (short tag like ``"ja"`` or
            a human-readable name). ``None`` lets the backend auto-detect.
        """


def build_system_prompt(target_language: str) -> str:
    """Return the shared system prompt used by AI-based translators."""
    return (
        "You are a professional translator for video games and live chat. "
        f"Translate the user's text into natural, fluent {target_language}. "
        "Preserve proper nouns, character names, place names, and game-specific "
        "terminology. Keep the original line breaks. Do NOT add explanations, "
        "quotation marks, or prefixes — output only the translation."
    )


__all__ = ["Translator", "TranslationError", "build_system_prompt"]
