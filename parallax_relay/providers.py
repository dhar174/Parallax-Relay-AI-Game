"""Three small async adapters to documented provider REST endpoints.

No remote tools, server-side conversations, automatic HTTP retries, or arbitrary
base URLs. This keeps network behavior inspectable with httpx.MockTransport.
"""
from __future__ import annotations

import base64
import json
import re
import httpx

from .protocol import AgentRequest, ModelReply, Usage, response_schema
from .prompts import SYSTEM_RULES

ENDPOINTS = {
    'openai': 'https://api.openai.com/v1/responses',
    'anthropic': 'https://api.anthropic.com/v1/messages',
    'gemini': 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
}
MAX_BODY_BYTES = 262144


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool, status_code: int | None = None, retry_after: float = 0):
        self.code = code if re.fullmatch(r'[a-z_]{1,48}', code) else 'provider_error'
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = max(0, min(30, retry_after))
        super().__init__(self.code + (f' (HTTP {status_code})' if status_code else ''))


def _tokens(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _usage(provider: str, data: dict) -> Usage:
    if provider == 'gemini':
        u = data.get('usageMetadata') or {}
        inp, out = _tokens(u.get('promptTokenCount')), _tokens(u.get('candidatesTokenCount'))
        thought = _tokens(u.get('thoughtsTokenCount')) or 0
        return Usage(inp, None if out is None else out + thought,
                     _tokens(u.get('cachedContentTokenCount')) or 0, thought)
    u = data.get('usage') or {}
    inp, out = _tokens(u.get('input_tokens')), _tokens(u.get('output_tokens'))
    if provider == 'anthropic':
        cached = _tokens(u.get('cache_read_input_tokens')) or 0
        written = _tokens(u.get('cache_creation_input_tokens')) or 0
        return Usage(None if inp is None else inp + cached + written, out, cached)
    cached = _tokens((u.get('input_tokens_details') or {}).get('cached_tokens')) or 0
    thought = _tokens((u.get('output_tokens_details') or {}).get('reasoning_tokens')) or 0
    return Usage(inp, out, cached, thought)  # OpenAI output already includes reasoning.


def _decode(provider: str, data: dict) -> ModelReply:
    usage = _usage(provider, data)
    if provider == 'openai':
        parts = [p for item in data.get('output', []) if item.get('type') == 'message'
                 for p in item.get('content', [])]
        if any(p.get('type') == 'refusal' for p in parts):
            return ModelReply('', usage, 'refusal')
        text = ''.join(p.get('text', '') for p in parts if p.get('type') == 'output_text')
        return ModelReply(text, usage, 'ok' if data.get('status') == 'completed' else 'incomplete')
    if provider == 'anthropic':
        stop = data.get('stop_reason')
        text = ''.join(p.get('text', '') for p in data.get('content', []) if p.get('type') == 'text')
        status = 'refusal' if stop == 'refusal' else 'ok' if stop == 'end_turn' else 'incomplete'
        return ModelReply(text, usage, status)
    candidates = data.get('candidates') or []
    if not candidates:
        status = 'refusal' if (data.get('promptFeedback') or {}).get('blockReason') else 'incomplete'
        return ModelReply('', usage, status)
    candidate = candidates[0]
    reason = candidate.get('finishReason')
    status = ('ok' if reason == 'STOP' else 'refusal' if reason in {
        'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY'
    } else 'incomplete')
    text = ''.join(p.get('text', '') for p in (candidate.get('content') or {}).get('parts', [])
                   if not p.get('thought', False))
    return ModelReply(text, usage, status)


class HTTPAgent:
    def __init__(self, provider: str, model: str, api_key: str, *,
                 timeout_seconds: float = 60, client: httpx.AsyncClient | None = None):
        if provider not in ENDPOINTS:
            raise ValueError('Unsupported provider')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', model):
            raise ValueError('Use a bare model ID, not a path or URL')
        if not api_key or '\r' in api_key or '\n' in api_key:
            raise ValueError('Invalid credential format')
        self.provider, self.model = provider, model
        self._key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)

    def _wire_request(self, request: AgentRequest) -> tuple[str, dict, dict]:
        png = base64.b64encode(request.observation.image_png).decode('ascii')
        text, schema = request.prompt_text(), response_schema(request.phase)
        headers = {'content-type': 'application/json'}
        if self.provider == 'openai':
            headers['authorization'] = 'Bearer ' + self._key
            body = {
                'model': self.model, 'instructions': SYSTEM_RULES, 'store': False,
                'max_output_tokens': request.max_output_tokens,
                'input': [{'role': 'user', 'content': [
                    {'type': 'input_image', 'image_url': 'data:image/png;base64,' + png, 'detail': 'high'},
                    {'type': 'input_text', 'text': text},
                ]}],
                'text': {'format': {'type': 'json_schema', 'name': 'parallax_' + request.phase,
                                    'schema': schema, 'strict': True}},
            }
        elif self.provider == 'anthropic':
            headers.update({'x-api-key': self._key, 'anthropic-version': '2026-10-21'})
            body = {
                'model': self.model, 'system': SYSTEM_RULES, 'max_tokens': request.max_output_tokens,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': png}},
                    {'type': 'text', 'text': text},
                ]}],
                'output_config': {'format': {'type': 'json_schema', 'schema': schema}},
            }
        else:
            headers['x-goog-api-key'] = self._key  # Never in a query-string URL/log.
            body = {
                'systemInstruction': {'parts': [{'text': SYSTEM_RULES}]},
                'contents': [{'role': 'user', 'parts': [
                    {'inlineData': {'mimeType': 'image/png', 'data': png}}, {'text': text},
                ]}],
                'generationConfig': {'maxOutputTokens': request.max_output_tokens,
                                     'responseMimeType': 'application/json',
                                     'responseJsonSchema': schema, 'candidateCount': 1},
            }
        return ENDPOINTS[self.provider].format(model=self.model), headers, body

    async def respond(self, request: AgentRequest) -> ModelReply:
        url, headers, body = self._wire_request(request)
        try:
            async with self._client.stream('POST', url, headers=headers, json=body,
                                           follow_redirects=False) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BODY_BYTES:
                        raise ProviderError('response_too_large', False)
                status = response.status_code
                if not 200 <= status < 300:
                    # Only allowlisted metadata; never include provider error text.
                    quota = False
                    try:
                        quota = json.loads(content).get('error', {}).get('code') in {'insufficient_quota', 'billing_hard_limit_reached'}
                    except (ValueError, AttributeError, TypeError):
                        pass
                    retryable = (status in {408, 409, 429} or status >= 500) and not quota
                    try:
                        delay = float(response.headers.get('retry-after', '0'))
                    except ValueError:
                        delay = 0
                    raise ProviderError('quota_exhausted' if quota else 'http_error', retryable, status, delay)
                try:
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise ValueError('expected object')
                    return _decode(self.provider, data)
                except (ValueError, TypeError, AttributeError, KeyError):
                    raise ProviderError('invalid_provider_response', True) from None
        except httpx.TimeoutException:
            raise ProviderError('timeout', True) from None
        except httpx.TransportError:
            raise ProviderError('network_error', True) from None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
