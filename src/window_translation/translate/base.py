"""Base interface for translation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional translator for video games and live chat. "
    "Translate the user's text into natural, fluent {target_language}. "
    "Preserve proper nouns, character names, place names, and game-specific "
    "terminology. Keep the original line breaks. Do NOT add explanations, "
    "quotation marks, or prefixes — output only the translation."
)


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


def build_system_prompt(
    target_language: str,
    source_language: Optional[str] = None,
    template: Optional[str] = None,
) -> str:
    """Render a system prompt.

    The ``template`` may use ``{target_language}`` and ``{source_language}``
    placeholders. Unknown placeholders (including stray braces from a
    user-authored template) are tolerated — we fall back to the default
    prompt in that case so that a malformed template never crashes the app.
    """
    tmpl = template if template and template.strip() else DEFAULT_SYSTEM_PROMPT
    src = source_language or "auto"
    try:
        return tmpl.format(target_language=target_language, source_language=src)
    except (KeyError, IndexError, ValueError):
        # Fall back to defaults so a broken user template can never break translation.
        return DEFAULT_SYSTEM_PROMPT.format(
            target_language=target_language,
            source_language=src,
        )


__all__ = [
    "Translator",
    "TranslationError",
    "build_system_prompt",
    "DEFAULT_SYSTEM_PROMPT",
]
