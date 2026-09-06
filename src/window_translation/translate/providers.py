"""Provider discovery and native Claude support.

Anthropic protocol: https://platform.claude.com/docs/en/api/models/list
and https://platform.claude.com/docs/en/api/messages/create
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
import requests

from .base import TranslationError, build_system_prompt
from .openai_client import OpenAITranslator, ENDPOINT_PRESETS

PROVIDER_LABELS = {
    'openai': 'OpenAI', 'anthropic': 'Anthropic · Claude',
    'openrouter': 'OpenRouter · 여러 회사의 모델', 'groq': 'Groq',
    'ollama': 'Ollama · 내 PC', 'lm-studio': 'LM Studio · 내 PC',
    'custom': '커스텀 · OpenAI 호환', 'azure-openai': 'Azure OpenAI',
    'stub': '테스트용 · 가짜 번역',
}


def api_endpoint(provider: str, endpoint: str = '') -> str:
    value = (endpoint or ENDPOINT_PRESETS.get(provider, '')).strip().rstrip('/')
    if not value:
        raise TranslationError('API 주소를 입력해주세요.')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise TranslationError('올바른 http/https API 주소를 입력해주세요.')
    # Accept both a base URL and the full route, as in SillyTavern.
    route = '/messages' if provider == 'anthropic' else '/chat/completions'
    path = parsed.path.rstrip('/')
    if not path:
        path = '/v1' + route
    elif path.endswith('/v1'):
        path += route
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ''))


def _json_response(response):
    if 300 <= response.status_code < 400:
        raise TranslationError('API 주소가 다른 페이지로 이동합니다. 최종 API 주소를 입력해주세요.')
    if response.status_code in (401, 403):
        raise TranslationError(f'인증 실패 (HTTP {response.status_code}). 선택한 제공자의 API 키인지 확인해주세요.')
    if response.status_code >= 400:
        raise TranslationError(f'서버 오류 (HTTP {response.status_code}). 모델·주소·사용 한도와 계정 상태를 확인해주세요.')
    try:
        data = response.json()
    except ValueError:
        raise TranslationError('서버가 JSON 대신 빈 응답 또는 웹페이지를 반환했습니다. API 주소를 확인해주세요.') from None
    if not isinstance(data, dict):
        raise TranslationError('서버의 응답 형식을 확인할 수 없습니다.')
    return data


def list_models(provider: str, endpoint: str, key: str, session=None) -> list[str]:
    if provider == 'stub':
        return ['stub']
    if provider == 'azure-openai':
        raise TranslationError('Azure는 배포 URL과 배포 이름을 직접 입력하고 번역 테스트를 사용해주세요.')
    if not key and provider not in {'ollama', 'lm-studio'}:
        raise TranslationError('먼저 API 키를 입력해주세요.')
    endpoint = api_endpoint(provider, endpoint)
    parsed = urlsplit(endpoint)
    suffix = '/messages' if provider == 'anthropic' else '/chat/completions'
    if not parsed.path.endswith(suffix):
        raise TranslationError('모델 목록을 찾으려면 API 기본 주소 또는 완전한 번역 API 주소를 입력해주세요.')
    models_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path[:-len(suffix)] + '/models', parsed.query, ''))
    headers = {'Accept': 'application/json'}
    if provider == 'anthropic':
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    elif key:
        headers['Authorization'] = 'Bearer ' + key
    own_session = session is None
    session = session or requests.Session()
    try:
        # OpenRouter's catalogue is public, so separately verify the key.
        if provider == 'openrouter':
            key_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path[:-len(suffix)] + '/key', parsed.query, ''))
            _json_response(session.get(key_url, headers=headers, timeout=15, allow_redirects=False))
        params = {'limit': 1000} if provider == 'anthropic' else {}
        data = _json_response(session.get(models_url, headers=headers, params=params, timeout=15, allow_redirects=False))
        rows = data.get('data')
        if not isinstance(rows, list):
            raise TranslationError('모델 목록 API가 없는 서버입니다. 모델명을 직접 입력하고 번역 테스트를 사용해주세요.')
        models = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                continue
            model = row['id']
            if provider == 'openai' and any(x in model.lower() for x in ('embedding', 'whisper', 'tts', 'dall-e', 'image', 'moderation', 'transcribe', 'realtime', 'audio', 'sora')):
                continue
            outputs = row.get('architecture', {}).get('output_modalities', []) if isinstance(row.get('architecture', {}), dict) else []
            if outputs and 'text' not in outputs:
                continue
            models.append(model)
        if data.get('has_more'):
            raise TranslationError('모델 목록이 한 페이지를 넘었습니다. 모델명을 직접 입력해주세요.')
        if not models:
            raise TranslationError('표시할 텍스트 모델이 없습니다. 모델명을 직접 입력할 수 있습니다.')
        return sorted(set(models))
    except requests.RequestException:
        raise TranslationError('서버에 연결하지 못했습니다. API 주소와 네트워크 상태를 확인해주세요.') from None
    finally:
        if own_session:
            session.close()


class AnthropicTranslator(OpenAITranslator):
    """Claude Messages API with native auth, system and content blocks."""
    def translate(self, text, target_language='Korean', source_language=None):
        if not text.strip():
            return ''
        messages = []
        for src, tgt in self._few_shot_examples:
            if src.strip() and tgt.strip():
                messages.extend([{'role': 'user', 'content': src}, {'role': 'assistant', 'content': tgt}])
        messages.append({'role': 'user', 'content': text})
        payload = {
            'model': self.model, 'max_tokens': 4096,
            'system': build_system_prompt(target_language, source_language=source_language, template=self._system_prompt_template),
            'messages': messages,
        }
        try:
            response = self._session.post(self.endpoint, headers={
                'x-api-key': self._api_key, 'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            }, json=payload, timeout=self.timeout, allow_redirects=False)
        except requests.RequestException:
            raise TranslationError('Claude 서버에 연결하지 못했습니다. 네트워크와 API 주소를 확인해주세요.') from None
        data = _json_response(response)
        content = data.get('content')
        if not isinstance(content, list):
            raise TranslationError('Claude Messages API 응답 형식이 아닙니다.')
        result = '\n'.join(item['text'] for item in content if isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str)).strip()
        if not result:
            raise TranslationError('Claude가 번역 텍스트를 반환하지 않았습니다.')
        if data.get('stop_reason') == 'max_tokens':
            raise TranslationError('번역이 길이 제한으로 잘렸습니다. 더 작은 영역을 선택해주세요.')
        return result
