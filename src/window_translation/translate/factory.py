"""Pick a translator implementation based on :class:`AppSettings`."""

from __future__ import annotations

import logging
import hashlib
import json
from typing import Optional

from ..config import AppSettings, default_history_path, load_api_key
from ..history import HistoryStore
from .base import Translator, TranslationError
from .cache import CachingTranslator
from .openai_client import DEFAULT_ENDPOINT, ENDPOINT_PRESETS, OpenAITranslator
from .stub import StubTranslator
from .providers import AnthropicTranslator, api_endpoint
from ..config.secrets import load_provider_key

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

    Cloud providers require an API key. Local providers accept an empty key.
    Stub translation must be selected explicitly. History enables caching.
    """
    provider = (settings.provider or "openai").lower()

    if provider == "stub":
        inner: Translator = StubTranslator()
    else:
        if not settings.model.strip():
            raise TranslationError("설정에서 모델 목록을 불러와 선택하거나 모델명을 직접 입력해주세요.")
        key = api_key if api_key is not None else load_provider_key(provider)
        if not key and provider in {"ollama", "lm-studio"}:
            key = "local"
        if not key:
            raise TranslationError("API 키가 설정되어 있지 않습니다. 설정에서 API 키를 입력해주세요.")
        else:
            endpoint = api_endpoint(provider, _resolve_endpoint(settings))
            client = AnthropicTranslator if provider == "anthropic" else OpenAITranslator
            inner = client(
                api_key=key,
                model=settings.model,
                endpoint=endpoint,
                system_prompt_template=settings.system_prompt or None,
            )

    if settings.assistant_prefill.strip() and provider != 'stub':
        if provider not in {'custom', 'ollama', 'lm-studio', 'openrouter', 'anthropic'}:
            raise TranslationError('이 제공자의 프리필은 지원하지 않습니다. 프롬프트 탭의 프리필을 비워주세요.')
        if provider == 'anthropic' and not any(tag in settings.model for tag in ('-3-', '-3-5-', '-3-7-', '-4-2025', '-4-1-', '-4-5-')):
            raise TranslationError('이 Claude 모델은 프리필 지원이 확인되지 않았습니다. 프리필을 비우고 시스템 프롬프트를 사용해주세요.')
        inner._assistant_prefill = settings.assistant_prefill
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
        project=settings.library_project.strip() or '기본',
        cache_scope=hashlib.sha256(json.dumps([provider, _resolve_endpoint(settings), settings.model,
            settings.system_prompt, settings.assistant_prefill, settings.history_recent_context],
            ensure_ascii=False).encode()).hexdigest(),
    )


# Backward compat: some callers may not have a TranslationError import path
# other than via this module.
__all__ = ["build_translator", "TranslationError"]
