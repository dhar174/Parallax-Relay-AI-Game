"""Three small async adapters to documented provider REST endpoints.

No remote tools, server-side conversations, automatic HTTP retries, or arbitrary
base URLs. This keeps network behavior inspectable with httpx.MockTransport.
"""
from __future__ import annotations

import base64
import json
import math
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
ANTHROPIC_API_VERSION = '2026-10-21'


def provider_contract(provider: str) -> dict | None:
    """Safe implemented contract, not evidence of remote/model compatibility."""
    if provider not in ENDPOINTS:
        return None
    return {'endpoint': ENDPOINTS[provider],
            'family': {'openai': 'responses', 'anthropic': 'messages', 'gemini': 'generateContent'}[provider],
            'namespace': 'v1beta' if provider == 'gemini' else 'v1',
            'version_header': ANTHROPIC_API_VERSION if provider == 'anthropic' else None}


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool, status_code: int | None = None, retry_after: float = 0):
        self.code = code if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,48}', code) else 'provider_error'
        self.retryable = retryable
        self.status_code = status_code
        finite = isinstance(retry_after, int) or math.isfinite(retry_after)
        self.retry_after = max(0, min(30, retry_after)) if finite else 0
        super().__init__(self.code + (f' (HTTP {status_code})' if status_code else ''))


def _tokens(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _optional_tokens(usage: dict, name: str) -> int | None:
    # Omitted optional breakdowns retain legacy zero semantics. Explicit null or
    # malformed values cannot establish a complete sum for conservative pricing.
    return _tokens(usage[name]) if name in usage else 0


def _object(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Expected provider object')
    return value


def _items(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError('Expected provider object list')
    return value


def _error_code(value) -> str | None:
    code = value.get('code') if isinstance(value, dict) else None
    return code if isinstance(code, str) else None


def _source_usage(provider: str, data: dict) -> dict[str, dict]:
    """Only allowlisted counter states/counts, never arbitrary provider values."""
    paths = {
        'openai': ('usage.input_tokens', 'usage.output_tokens',
                   'usage.input_tokens_details.cached_tokens',
                   'usage.output_tokens_details.reasoning_tokens'),
        'anthropic': ('usage.input_tokens', 'usage.output_tokens',
                      'usage.cache_read_input_tokens', 'usage.cache_creation_input_tokens',
                      'usage.output_tokens_details.thinking_tokens'),
        'gemini': ('usageMetadata.promptTokenCount', 'usageMetadata.candidatesTokenCount',
                   'usageMetadata.cachedContentTokenCount', 'usageMetadata.thoughtsTokenCount'),
    }
    result = {}
    for path in paths[provider]:
        value = data
        state = 'count'
        for key in path.split('.'):
            if value is None:
                state = 'null'
                break
            if not isinstance(value, dict):
                state = 'invalid'
                break
            if key not in value:
                state = 'omitted'
                break
            value = value[key]
        if state == 'count':
            state = 'null' if value is None else 'count' if _tokens(value) is not None else 'invalid'
        result[path] = {'state': state, 'value': value if state == 'count' else None}
    return result


def _usage(provider: str, data: dict) -> Usage:
    source = _source_usage(provider, data)
    if provider == 'gemini':
        u = _object(data.get('usageMetadata'))
        inp, out = _tokens(u.get('promptTokenCount')), _tokens(u.get('candidatesTokenCount'))
        thought = _optional_tokens(u, 'thoughtsTokenCount')
        return Usage(inp, None if out is None or thought is None else out + thought,
                     _tokens(u.get('cachedContentTokenCount')) or 0, thought or 0, source)
    u = _object(data.get('usage'))
    inp, out = _tokens(u.get('input_tokens')), _tokens(u.get('output_tokens'))
    if provider == 'anthropic':
        cached = _optional_tokens(u, 'cache_read_input_tokens')
        written = _optional_tokens(u, 'cache_creation_input_tokens')
        thought = _tokens(_object(u.get('output_tokens_details')).get('thinking_tokens')) or 0
        return Usage(None if any(n is None for n in (inp, cached, written)) else inp + cached + written,
                     out, cached or 0, thought, source)
    cached = _tokens(_object(u.get('input_tokens_details')).get('cached_tokens')) or 0
    thought = _tokens(_object(u.get('output_tokens_details')).get('reasoning_tokens')) or 0
    return Usage(inp, out, cached, thought, source)  # OpenAI output already includes reasoning.


def _decode(provider: str, data: dict) -> ModelReply:
    # Explicit failure is authoritative even when accompanying telemetry is bad.
    if provider == 'openai' and (data.get('status') == 'failed' or data.get('error') is not None):
        raise ProviderError('response_failed', _error_code(data.get('error')) in {'server_error', 'rate_limit_exceeded'})
    usage = _usage(provider, data)
    if provider == 'openai':
        if _object(data.get('incomplete_details')).get('reason') == 'content_filter':
            return ModelReply('', usage, 'refusal')
        messages = [item for item in _items(data.get('output')) if item.get('type') == 'message']
        if any(p.get('type') == 'refusal' for item in messages for p in _items(item.get('content'))):
            return ModelReply('', usage, 'refusal')
        messages = [item for item in messages if item.get('phase') in (None, 'final_answer')]
        parts = [p for item in messages for p in _items(item.get('content'))]
        text = ''.join(p.get('text', '') for p in parts if p.get('type') == 'output_text')
        complete = data.get('status') == 'completed' and bool(messages) and all(
            item.get('status', 'completed') == 'completed' for item in messages)
        return ModelReply(text, usage, 'ok' if complete else 'incomplete')
    if provider == 'anthropic':
        stop = data.get('stop_reason')
        if stop == 'refusal':
            return ModelReply('', usage, 'refusal')
        text = ''.join(p.get('text', '') for p in _items(data.get('content')) if p.get('type') == 'text')
        status = 'ok' if stop == 'end_turn' else 'incomplete'
        return ModelReply(text, usage, status)
    if _object(data.get('promptFeedback')).get('blockReason'):
        return ModelReply('', usage, 'refusal')
    candidates = _items(data.get('candidates'))
    if not candidates:
        return ModelReply('', usage, 'incomplete')
    candidate = candidates[0]
    reason = candidate.get('finishReason')
    status = ('ok' if reason == 'STOP' else 'refusal' if reason in {
        'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY'
    } else 'incomplete')
    if status == 'refusal':
        return ModelReply('', usage, status)
    text = ''.join(p.get('text', '') for p in _items(_object(candidate.get('content')).get('parts'))
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
        png = base64.b64encode(request.observation.image_png).decode('ascii') if request.include_image else ''
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
            headers.update({'x-api-key': self._key, 'anthropic-version': ANTHROPIC_API_VERSION})
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
        if not request.include_image:
            if self.provider == 'openai':
                body['input'][0]['content'] = [p for p in body['input'][0]['content'] if p['type'] != 'input_image']
            elif self.provider == 'anthropic':
                body['messages'][0]['content'] = [p for p in body['messages'][0]['content'] if p['type'] != 'image']
            else:
                body['contents'][0]['parts'] = [p for p in body['contents'][0]['parts'] if 'inlineData' not in p]
        return ENDPOINTS[self.provider].format(model=self.model), headers, body

    async def respond(self, request: AgentRequest) -> ModelReply:
        url, headers, body = self._wire_request(request)
        try:
            async with self._client.stream('POST', url, headers=headers, json=body,
                                           follow_redirects=False) as response:
                status = response.status_code
                successful = 200 <= status < 300
                content = bytearray()
                try:
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > MAX_BODY_BYTES:
                            if successful:
                                raise ProviderError('response_too_large', False)
                            # Error-body details are optional. Stop reading an
                            # oversized proxy page and retain its HTTP policy.
                            content.clear()
                            break
                        content.extend(chunk)
                except httpx.DecodingError:
                    if successful:
                        raise
                    content.clear()  # A corrupt error body cannot change its status.
                if not successful:
                    # Only allowlisted metadata; never include provider error text.
                    quota = False
                    try:
                        data = json.loads(content)
                        quota = _error_code(data.get('error') if isinstance(data, dict) else None) in {
                            'insufficient_quota', 'billing_hard_limit_reached'}
                    except (ValueError, RecursionError):
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
                except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
                    raise ProviderError('invalid_provider_response', True) from None
        except httpx.TimeoutException:
            raise ProviderError('timeout', True) from None
        except httpx.DecodingError:
            raise ProviderError('invalid_provider_response', True) from None
        except httpx.TransportError:
            raise ProviderError('network_error', True) from None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
