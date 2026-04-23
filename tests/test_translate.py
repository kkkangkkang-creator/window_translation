"""Tests for the translation backends (no network)."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from window_translation.config.settings import AppSettings
from window_translation.translate import (
    OpenAITranslator,
    StubTranslator,
    TranslationError,
    build_translator,
)
from window_translation.translate.base import (
    DEFAULT_SYSTEM_PROMPT,
    build_system_prompt,
)


# ----------------------------------------------------------------- stub


def test_stub_translator_returns_tagged_copy() -> None:
    t = StubTranslator()
    assert t.translate("hello", target_language="Korean").startswith("[stub → Korean]")


def test_stub_translator_empty_input() -> None:
    assert StubTranslator().translate("") == ""
    assert StubTranslator().translate("   ") == ""


# ----------------------------------------------------------------- factory


def test_factory_returns_stub_when_provider_stub() -> None:
    t = build_translator(AppSettings(provider="stub"))
    assert isinstance(t, StubTranslator)


def test_factory_falls_back_to_stub_without_key() -> None:
    t = build_translator(AppSettings(provider="openai"), api_key="")
    assert isinstance(t, StubTranslator)


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(TranslationError):
        build_translator(AppSettings(provider="not-a-thing"))


def test_factory_builds_openai_when_key_present() -> None:
    t = build_translator(AppSettings(provider="openai"), api_key="sk-test")
    assert isinstance(t, OpenAITranslator)


# ----------------------------------------------------------------- openai


class _FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any] | str) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self) -> Any:
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_request: Dict[str, Any] = {}

    def post(self, url: str, headers: Dict[str, str], data: str, timeout: float) -> _FakeResponse:
        self.last_request = {
            "url": url,
            "headers": headers,
            "data": json.loads(data),
            "timeout": timeout,
        }
        return self._response


def test_openai_translator_happy_path() -> None:
    session = _FakeSession(
        _FakeResponse(
            200,
            {"choices": [{"message": {"content": "안녕하세요"}}]},
        )
    )
    t = OpenAITranslator(api_key="sk-test", session=session)  # type: ignore[arg-type]
    out = t.translate("hello", target_language="Korean", source_language="en")
    assert out == "안녕하세요"

    # Authorization header should be present and carry the key.
    assert session.last_request["headers"]["Authorization"] == "Bearer sk-test"
    body = session.last_request["data"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0]["role"] == "system"
    assert "Korean" in body["messages"][0]["content"]
    assert "hello" in body["messages"][1]["content"]


def test_openai_translator_rate_limit() -> None:
    session = _FakeSession(_FakeResponse(429, {"error": "rate"}))
    t = OpenAITranslator(api_key="sk-test", session=session)  # type: ignore[arg-type]
    with pytest.raises(TranslationError, match="Rate limit"):
        t.translate("hello")


def test_openai_translator_http_error() -> None:
    session = _FakeSession(_FakeResponse(500, "internal boom"))
    t = OpenAITranslator(api_key="sk-test", session=session)  # type: ignore[arg-type]
    with pytest.raises(TranslationError, match="HTTP 500"):
        t.translate("hello")


def test_openai_translator_empty_choice() -> None:
    session = _FakeSession(
        _FakeResponse(200, {"choices": [{"message": {"content": "   "}}]})
    )
    t = OpenAITranslator(api_key="sk-test", session=session)  # type: ignore[arg-type]
    with pytest.raises(TranslationError, match="Empty translation"):
        t.translate("hello")


def test_openai_translator_requires_key() -> None:
    with pytest.raises(TranslationError):
        OpenAITranslator(api_key="")


def test_openai_translator_skips_empty_input() -> None:
    session = _FakeSession(_FakeResponse(200, {"choices": [{"message": {"content": "x"}}]}))
    t = OpenAITranslator(api_key="sk-test", session=session)  # type: ignore[arg-type]
    assert t.translate("") == ""
    assert session.last_request == {}  # no call was made


# ----------------------------------------------------------------- prompts


def test_build_system_prompt_uses_default_when_no_template() -> None:
    out = build_system_prompt("Korean")
    assert "Korean" in out
    # No stray unreplaced placeholders.
    assert "{target_language}" not in out
    assert "{source_language}" not in out


def test_build_system_prompt_substitutes_placeholders() -> None:
    tmpl = "Translate {source_language} to {target_language}, no commentary."
    out = build_system_prompt("Korean", source_language="ja", template=tmpl)
    assert out == "Translate ja to Korean, no commentary."


def test_build_system_prompt_auto_when_source_missing() -> None:
    tmpl = "src={source_language} tgt={target_language}"
    out = build_system_prompt("Korean", template=tmpl)
    assert out == "src=auto tgt=Korean"


def test_build_system_prompt_falls_back_on_invalid_template() -> None:
    # Missing key — must fall back to default rather than raise.
    out = build_system_prompt("Korean", template="hi {unknown_key} there")
    assert "Korean" in out
    assert "{unknown_key}" not in out


def test_build_system_prompt_empty_template_uses_default() -> None:
    assert build_system_prompt("Korean", template="   ") == build_system_prompt("Korean")


def test_default_prompt_mentions_placeholders() -> None:
    # Sanity: the default prompt must itself be template-friendly.
    assert "{target_language}" in DEFAULT_SYSTEM_PROMPT


def test_openai_translator_uses_custom_prompt_template() -> None:
    session = _FakeSession(
        _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    t = OpenAITranslator(
        api_key="sk-test",
        session=session,  # type: ignore[arg-type]
        system_prompt_template="Just say 'ok' in {target_language} ({source_language}).",
    )
    t.translate("hello", target_language="Korean", source_language="en")
    system_msg = session.last_request["data"]["messages"][0]["content"]
    assert system_msg == "Just say 'ok' in Korean (en)."


def test_factory_passes_system_prompt_to_openai() -> None:
    custom = "Translate into {target_language} only."
    t = build_translator(
        AppSettings(provider="openai", system_prompt=custom),
        api_key="sk-test",
    )
    assert isinstance(t, OpenAITranslator)
    # The stored template should be what we configured.
    assert t._system_prompt_template == custom  # type: ignore[attr-defined]
