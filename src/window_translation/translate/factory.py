"""Pick a translator implementation based on :class:`AppSettings`."""

from __future__ import annotations

import logging
from typing import Optional

from ..config import AppSettings, load_api_key
from .base import Translator, TranslationError
from .openai_client import OpenAITranslator
from .stub import StubTranslator

log = logging.getLogger(__name__)


def build_translator(settings: AppSettings, api_key: Optional[str] = None) -> Translator:
    """Return a translator configured from ``settings``.

    Falls back to :class:`StubTranslator` when the chosen provider cannot be
    instantiated (e.g. missing API key). Callers should surface this to the
    user so they know translations are not real.
    """
    provider = (settings.provider or "openai").lower()

    if provider == "stub":
        return StubTranslator()

    if provider == "openai":
        key = api_key if api_key is not None else load_api_key()
        if not key:
            log.warning(
                "No API key available for provider %r; falling back to stub translator.",
                provider,
            )
            return StubTranslator()
        return OpenAITranslator(
            api_key=key,
            model=settings.model,
            system_prompt_template=settings.system_prompt or None,
        )

    raise TranslationError(f"Unknown translation provider: {provider!r}")


__all__ = ["build_translator"]
