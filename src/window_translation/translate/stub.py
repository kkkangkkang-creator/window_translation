"""Offline stub translator — useful for tests and demo runs without an API key."""

from __future__ import annotations

from typing import Optional

from .base import Translator


class StubTranslator(Translator):
    """Return the source text unchanged, with a tag that signals it's a stub.

    This is not intended for real use — it lets the rest of the pipeline
    exercise end-to-end without requiring network access or an API key.
    """

    def translate(
        self,
        text: str,
        target_language: str = "Korean",
        source_language: Optional[str] = None,
    ) -> str:
        if not text or not text.strip():
            return ""
        return f"[stub → {target_language}] {text}"


__all__ = ["StubTranslator"]
