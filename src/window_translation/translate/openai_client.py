"""OpenAI Chat Completions translator.

The client talks to the OpenAI REST API directly through :mod:`requests` so
we don't take on the large ``openai`` SDK as a hard dependency. The endpoint
is configurable to support OpenAI-compatible providers (Azure OpenAI, local
LLM gateways, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

import requests

from .base import Translator, TranslationError, build_system_prompt

log = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT = 30.0

# Known OpenAI-compatible endpoints. Users can select one of these or enter
# a custom URL (e.g. a LiteLLM / proxy server) in settings.
ENDPOINT_PRESETS = {
    "openai":       "https://api.openai.com/v1/chat/completions",
    "openrouter":   "https://openrouter.ai/api/v1/chat/completions",
    "groq":         "https://api.groq.com/openai/v1/chat/completions",
    "ollama":       "http://localhost:11434/v1/chat/completions",
    "lm-studio":    "http://localhost:1234/v1/chat/completions",
    # Azure OpenAI uses a deployment-specific URL; we provide a template
    # placeholder users must customise.
    "azure-openai": "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT/chat/completions?api-version=2024-02-15-preview",
    "custom":       "",
}


class OpenAITranslator(Translator):
    """Translate via an OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
        system_prompt_template: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise TranslationError("Missing OpenAI API key.")
        self._api_key = api_key
        self.model = model
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.timeout = timeout
        self._session = session or requests.Session()
        self._system_prompt_template = system_prompt_template or None
        self._few_shot_examples: List[Tuple[str, str]] = []

    def set_few_shot_examples(self, examples: List[Tuple[str, str]]) -> None:
        """Register ``(source, translation)`` pairs to prepend as examples."""
        self._few_shot_examples = list(examples or [])

    def translate(
        self,
        text: str,
        target_language: str = "Korean",
        source_language: Optional[str] = None,
    ) -> str:
        if not text or not text.strip():
            return ""

        user_prefix = ""
        if source_language:
            user_prefix = f"[source language hint: {source_language}]\n"

        system_prompt = build_system_prompt(
            target_language,
            source_language=source_language,
            template=self._system_prompt_template,
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        # Inject prior translations as few-shot demonstrations for
        # terminology / tone consistency.
        for src, tgt in self._few_shot_examples:
            if not src.strip() or not tgt.strip():
                continue
            messages.append({"role": "user", "content": src})
            messages.append({"role": "assistant", "content": tgt})
        messages.append({"role": "user", "content": user_prefix + text})

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = self._session.post(
                self.endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TranslationError(f"Network error: {exc}") from exc

        if resp.status_code == 429:
            raise TranslationError("Rate limit exceeded. Please slow down.")
        if resp.status_code >= 400:
            # Don't leak the full body (it may echo prompt content) — keep a
            # short excerpt for debugging.
            snippet = resp.text[:200].replace("\n", " ")
            raise TranslationError(
                f"Translation API returned HTTP {resp.status_code}: {snippet}"
            )

        try:
            data = resp.json()
            choice = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f"Unexpected API response: {exc}") from exc

        result = (choice or "").strip()
        if not result:
            raise TranslationError("Empty translation from API.")
        return result


__all__ = ["OpenAITranslator", "DEFAULT_ENDPOINT", "ENDPOINT_PRESETS"]
