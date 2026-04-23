"""Caching + consistency-boosting decorator around a :class:`Translator`.

This wrapper does two things:

1. **Exact-match cache** — consult :class:`HistoryStore` for an existing
   translation with the same ``(source_hash, target_language, model)``;
   return it immediately if found, skipping the API call entirely.
2. **Recent-context few-shot (opt-in)** — when ``recent_context`` > 0, the
   N most recent entries for the same target language are shown to the
   underlying translator as prior ``(original → translation)`` examples.
   This nudges the model toward consistent terminology and tone across
   consecutive captures (game dialogue, chat, etc.).

The wrapper is intentionally generic: it works with any :class:`Translator`
subclass. For the recent-context injection, we pass the examples via a
private sidecar method only :class:`OpenAITranslator` understands. Other
translators simply ignore the extra context.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from ..history import HistoryStore
from .base import Translator, TranslationError

log = logging.getLogger(__name__)


class CachingTranslator(Translator):
    """Decorator that adds persistent caching + optional few-shot context."""

    def __init__(
        self,
        inner: Translator,
        store: HistoryStore,
        *,
        model: str = "",
        provider: str = "",
        recent_context: int = 0,
        enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._store = store
        self._model = model
        self._provider = provider
        # Clamp to a sensible upper bound — more examples rarely helps and
        # costs real tokens.
        self._recent_context = max(0, min(int(recent_context), 10))
        self._enabled = bool(enabled)

    @property
    def inner(self) -> Translator:
        return self._inner

    # ------------------------------------------------------------ public API
    def translate(
        self,
        text: str,
        target_language: str = "Korean",
        source_language: Optional[str] = None,
    ) -> str:
        if not text or not text.strip():
            return ""

        # 1) Exact cache hit.
        if self._enabled:
            try:
                hit = self._store.lookup(text, target_language, model=self._model)
            except Exception as exc:  # DB corruption, locked, etc. — keep translating.
                log.warning("History lookup failed, falling through: %s", exc)
                hit = None
            if hit is not None:
                log.info("Cache hit for source_hash=%s", hit.source_hash[:12])
                return hit.translated_text

        # 2) Inject recent context, if supported by the inner translator.
        examples = self._recent_examples(target_language) if self._enabled else []
        previous_examples = None
        if examples and hasattr(self._inner, "set_few_shot_examples"):
            previous_examples = getattr(self._inner, "_few_shot_examples", None)
            self._inner.set_few_shot_examples(examples)  # type: ignore[attr-defined]

        try:
            translated = self._inner.translate(
                text,
                target_language=target_language,
                source_language=source_language,
            )
        finally:
            # Always clear to avoid leaking context into unrelated calls.
            if examples and hasattr(self._inner, "set_few_shot_examples"):
                self._inner.set_few_shot_examples(previous_examples or [])  # type: ignore[attr-defined]

        # 3) Persist.
        if self._enabled and translated.strip():
            try:
                self._store.add(
                    text,
                    translated,
                    source_language=source_language or "",
                    target_language=target_language,
                    provider=self._provider,
                    model=self._model,
                )
            except Exception as exc:
                # Never let a history write failure break a translation.
                log.warning("Failed to persist translation to history: %s", exc)

        return translated

    # ------------------------------------------------------------- internals
    def _recent_examples(self, target_language: str) -> List[Tuple[str, str]]:
        if self._recent_context <= 0:
            return []
        try:
            rows = self._store.recent(
                limit=self._recent_context,
                target_language=target_language,
            )
        except Exception as exc:
            log.warning("History recent() failed, skipping few-shot: %s", exc)
            return []
        # Reverse so oldest → newest (chronological demo).
        rows = list(reversed(rows))
        return [(r.source_text, r.translated_text) for r in rows]


__all__ = ["CachingTranslator"]


# Re-export TranslationError for convenience.
__all__.append("TranslationError")
