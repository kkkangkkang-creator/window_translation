"""Pick a translator implementation based on :class:`AppSettings`."""

from __future__ import annotations

import logging
from typing import Optional

from ..config import AppSettings, default_history_path, load_api_key
from ..history import HistoryStore
from .base import Translator, TranslationError
from .cache import CachingTranslator
from .openai_client import DEFAULT_ENDPOINT, ENDPOINT_PRESETS, OpenAITranslator
from .stub import StubTranslator

log = logging.getLogger(__name__)


def _resolve_endpoint(settings: AppSettings) -> str:
    """Return the effective endpoint URL for the configured provider."""
    # Explicit override always wins (handles the "custom" provider or any
    # user-edited URL).
    if settings.endpoint and settings.endpoint.strip():
        return settings.endpoint.strip()
    preset = ENDPOINT_PRESETS.get((settings.provider or "").lower())
    return preset or DEFAULT_ENDPOINT


def build_translator(
    settings: AppSettings,
    api_key: Optional[str] = None,
    *,
    history_store: Optional[HistoryStore] = None,
) -> Translator:
    """Return a translator configured from ``settings``.

    Falls back to :class:`StubTranslator` when the chosen provider cannot be
    instantiated (e.g. missing API key). When ``settings.history_enabled``
    the translator is wrapped in :class:`CachingTranslator`.
    """
    provider = (settings.provider or "openai").lower()

    if provider == "stub":
        inner: Translator = StubTranslator()
    else:
        key = api_key if api_key is not None else load_api_key()
        if not key:
            raise TranslationError("API 키가 설정되어 있지 않습니다. 설정에서 API 키를 입력해주세요.")
        else:
            endpoint = _resolve_endpoint(settings)
            inner = OpenAITranslator(
                api_key=key,
                model=settings.model,
                endpoint=endpoint,
                system_prompt_template=settings.system_prompt or None,
            )

    if not settings.history_enabled:
        return inner

    store = history_store or HistoryStore(default_history_path())
    return CachingTranslator(
        inner,
        store,
        model=settings.model if provider != "stub" else "",
        provider=provider,
        recent_context=settings.history_recent_context,
        enabled=True,
    )


# Backward compat: some callers may not have a TranslationError import path
# other than via this module.
__all__ = ["build_translator", "TranslationError"]
