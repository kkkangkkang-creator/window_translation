"""Protocol and provider isolation regressions; no external API calls."""
import json
import pytest

from window_translation.translate.providers import api_endpoint, list_models, AnthropicTranslator
from window_translation.translate import TranslationError, build_translator
from window_translation.config import AppSettings


class Response:
    status_code = 200
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
    def json(self):
        return self.data


class Session:
    def __init__(self, data):
        self.response = Response(data)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.mark.parametrize('provider,base,expected', [
    ('anthropic', '', 'https://api.anthropic.com/v1/messages'),
    ('anthropic', 'https://example.com/v1/', 'https://example.com/v1/messages'),
    ('custom', 'https://example.com', 'https://example.com/v1/chat/completions'),
    ('custom', 'https://example.com/proxy/v1', 'https://example.com/proxy/v1/chat/completions'),
])
def test_api_address_normalization(provider, base, expected):
    assert api_endpoint(provider, base) == expected


def test_anthropic_models_uses_native_key_header_and_route():
    session = Session({'data': [{'id': 'claude-test-b'}, {'id': 'claude-test-a'}]})
    assert list_models('anthropic', '', 'test-key', session) == ['claude-test-a', 'claude-test-b']
    url, call = session.calls[0]
    assert url == 'https://api.anthropic.com/v1/models'
    assert call['headers']['x-api-key'] == 'test-key'
    assert call['headers']['anthropic-version'] == '2023-06-01'
    assert 'Authorization' not in call['headers']
    assert call['allow_redirects'] is False


def test_openrouter_checks_key_before_catalogue():
    session = Session({'data': [{'id': 'vendor/model'}]})
    list_models('openrouter', '', 'test-key', session)
    assert [url for url, _ in session.calls] == ['https://openrouter.ai/api/v1/key', 'https://openrouter.ai/api/v1/models']


def test_anthropic_translation_protocol():
    session = Session({'content': [{'type': 'thinking', 'thinking': 'hidden'}, {'type': 'text', 'text': '안녕하세요'}], 'stop_reason': 'end_turn'})
    t = AnthropicTranslator(api_key='test-key', model='claude-test', endpoint='https://api.anthropic.com/v1/messages', session=session)
    assert t.translate('Hello', 'Korean', 'en') == '안녕하세요'
    url, call = session.calls[0]
    assert call['json']['system']
    assert call['json']['messages'] == [{'role': 'user', 'content': 'Hello'}]
    assert call['json']['max_tokens'] == 4096
    assert call['headers']['x-api-key'] == 'test-key'
    assert 'temperature' not in call['json']


def test_factory_selects_native_anthropic():
    t = build_translator(AppSettings(provider='anthropic', model='claude-test', history_enabled=False), api_key='test')
    assert isinstance(t, AnthropicTranslator)
    assert t.endpoint == 'https://api.anthropic.com/v1/messages'


def test_bad_key_is_reported_without_echo():
    session = Session({'error': 'private details'})
    session.response.status_code = 401
    with pytest.raises(TranslationError, match='인증 실패') as err:
        list_models('anthropic', '', 'secret-key', session)
    assert 'secret-key' not in str(err.value)
    assert 'private details' not in str(err.value)


def test_legacy_hotkey_migrates_but_explicit_custom_survives():
    assert AppSettings.from_dict({'hotkey': '<ctrl>+<shift>+t'}).hotkey == '<ctrl>+<alt>+<f9>'
    assert AppSettings.from_dict({'hotkey': '<alt>+q'}).hotkey == '<alt>+q'
    assert AppSettings.from_dict({'hotkey': '<ctrl>+<shift>+t', 'hotkey_version': 1}).hotkey == '<ctrl>+<shift>+t'


def test_provider_keys_are_isolated_and_legacy_migrates(tmp_path, monkeypatch):
    from window_translation.config import secrets, save_settings
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    save_settings(AppSettings(provider='openai'))
    secrets.save_api_key('old-openai-key')
    assert secrets.load_provider_key('openai') == 'old-openai-key'
    assert secrets.load_provider_key('anthropic') is None
    secrets.save_provider_keys({'anthropic': 'claude-key'})
    assert secrets.load_provider_key('openai') == 'old-openai-key'
    assert secrets.load_provider_key('anthropic') == 'claude-key'
    secrets.save_provider_keys({'anthropic': ''})
    assert secrets.load_provider_key('anthropic') is None
