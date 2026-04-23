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
