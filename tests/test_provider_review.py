"""Adversarial provider envelopes, bounded retries and real stream cleanup."""
import unittest

import httpx

from parallax_relay.observations import observe
from parallax_relay.protocol import AgentRequest
from parallax_relay.providers import HTTPAgent, ProviderError
from parallax_relay.state import initial_world
from test_provider_contracts import envelope, SECRET


class ProviderReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = AgentRequest(observe(initial_world(), 'SPECTRA'), 'broadcast')

    async def reply(self, provider, payload, *, status=200, headers=None):
        def handle(request):
            return httpx.Response(status, json=payload, headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await HTTPAgent(provider, 'test-model', SECRET, client=client).respond(self.request)

    async def stream_error(self, status, body, *, headers=None):
        closed = []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield body
            async def aclose(self):
                closed.append(True)
        def handle(request):
            return httpx.Response(status, stream=Stream(), headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(ProviderError) as error:
                await HTTPAgent('openai', 'test-model', SECRET, client=client).respond(self.request)
        self.assertTrue(closed)
        self.assertNotIn(SECRET, repr(error.exception))
        return error.exception

    async def test_explicit_failure_with_malformed_error_is_fatal(self):
        for status in ('failed', 'completed'):
            errors = [SECRET, [], False, 0, {}, {'code': []}, {'code': {}}, {'code': None}]
            if status == 'failed': errors.append(None)
            for value in errors:
                with self.subTest(status=status, error=value):
                    data = envelope('openai')
                    data.update(status=status, error=value)
                    with self.assertRaises(ProviderError) as caught:
                        await self.reply('openai', data)
                    self.assertEqual(caught.exception.code, 'response_failed')
                    self.assertFalse(caught.exception.retryable)
                    self.assertNotIn(SECRET, repr(caught.exception))

    async def test_failure_classification_precedes_malformed_usage(self):
        # A known terminal/transient failure cannot be masked by unrelated telemetry.
        for code, retryable in [('invalid_prompt', False), ('server_error', True)]:
            with self.subTest(code=code):
                data = {'status': 'failed', 'error': {'code': code}, 'usage': SECRET}
                with self.assertRaises(ProviderError) as caught:
                    await self.reply('openai', data)
                self.assertEqual(caught.exception.code, 'response_failed')
                self.assertEqual(caught.exception.retryable, retryable)

    async def test_null_collections_preserve_refusal_and_usage(self):
        cases = [
            ('openai', {'status': 'incomplete', 'output': None,
                        'incomplete_details': {'reason': 'content_filter'}}),
            ('openai', {'status': 'incomplete', 'output': [{'type': 'message', 'content': None}],
                        'incomplete_details': {'reason': 'content_filter'}}),
            ('anthropic', {'stop_reason': 'refusal', 'content': None}),
            ('gemini', {'candidates': [{'finishReason': 'SAFETY', 'content': {'parts': None}}]}),
            ('gemini', {'candidates': None, 'promptFeedback': {'blockReason': 'SAFETY'}}),
        ]
        for provider, changes in cases:
            with self.subTest(provider=provider, changes=changes):
                data = envelope(provider); data.update(changes)
                reply = await self.reply(provider, data)
                self.assertEqual(reply.status, 'refusal')
                self.assertEqual(reply.text, '')
                self.assertEqual(reply.usage.output_tokens, 20)

    async def test_null_optional_collections_without_refusal_remain_readable(self):
        for provider, changes in [
            ('openai', {'output': None}), ('anthropic', {'content': None}),
            ('gemini', {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': None}}]})
        ]:
            with self.subTest(provider=provider):
                data = envelope(provider); data.update(changes)
                reply = await self.reply(provider, data)
                self.assertEqual(reply.text, '')
                self.assertEqual(reply.usage.output_tokens, 20)

    async def test_wrong_type_containers_are_not_silently_treated_as_empty(self):
        paths = [
            ('openai', ('usage',)), ('anthropic', ('usage',)), ('gemini', ('usageMetadata',)),
            ('openai', ('output',)), ('openai', ('output', 0, 'content')),
            ('openai', ('incomplete_details',)), ('openai', ('usage', 'input_tokens_details')),
            ('anthropic', ('content',)), ('anthropic', ('usage', 'output_tokens_details')),
            ('gemini', ('candidates',)), ('gemini', ('promptFeedback',)),
            ('gemini', ('candidates', 0, 'content')), ('gemini', ('candidates', 0, 'content', 'parts')),
        ]
        for provider, path in paths:
            for value in ('', False, 0):
                with self.subTest(provider=provider, path=path, value=value):
                    data = envelope(provider)
                    target = data
                    for key in path[:-1]: target = target[key]
                    target[path[-1]] = value
                    with self.assertRaises(ProviderError) as caught:
                        await self.reply(provider, data)
                    self.assertEqual(caught.exception.code, 'invalid_provider_response')
                    self.assertTrue(caught.exception.retryable)
        for provider, path, value in [('openai', ('usage',), []), ('openai', ('output',), {}),
                                      ('anthropic', ('content',), {}), ('gemini', ('usageMetadata',), []),
                                      ('gemini', ('candidates',), {})]:
            with self.subTest(provider=provider, path=path, value=value):
                data = envelope(provider); data[path[0]] = value
                with self.assertRaises(ProviderError) as caught:
                    await self.reply(provider, data)
                self.assertEqual(caught.exception.code, 'invalid_provider_response')

    async def test_gemini_prompt_block_overrides_a_successful_candidate(self):
        data = envelope('gemini')
        data['promptFeedback'] = {'blockReason': 'SAFETY'}
        reply = await self.reply('gemini', data)
        self.assertEqual(reply.status, 'refusal')
        self.assertEqual(reply.text, '')
        self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens), (100, 20))

    async def test_refusal_text_is_empty_for_direct_callers_on_all_providers(self):
        for provider in ('openai', 'anthropic', 'gemini'):
            with self.subTest(provider=provider):
                data = envelope(provider)
                if provider == 'openai':
                    data['output'][0]['content'] = [{'type': 'refusal', 'refusal': SECRET}]
                elif provider == 'anthropic':
                    data.update(stop_reason='refusal', content=[{'type': 'text', 'text': SECRET}])
                else:
                    data['candidates'][0].update(finishReason='SAFETY', content={'parts': [{'text': SECRET}]})
                reply = await self.reply(provider, data)
                self.assertEqual((reply.status, reply.text), ('refusal', ''))
                self.assertEqual(reply.usage.output_tokens, 20)

    async def test_retry_after_unsupported_and_nonfinite_values_use_backoff(self):
        for value, expected in [('nan', 0), ('NaN', 0), ('inf', 0), ('-inf', 0),
                                ('invalid', 0), ('Wed, 21 Oct 2026 07:28:00 GMT', 0),
                                ('-3', 0), ('0', 0), ('2.5', 2.5), ('60', 30)]:
            with self.subTest(value=value):
                with self.assertRaises(ProviderError) as caught:
                    await self.reply('openai', {}, status=503, headers={'retry-after': value})
                self.assertEqual(caught.exception.code, 'http_error')
                self.assertEqual(caught.exception.status_code, 503)
                self.assertTrue(caught.exception.retryable)
                self.assertEqual(caught.exception.retry_after, expected)

    def test_provider_error_sanitizes_invalid_codes_and_nonfinite_delays(self):
        for code in ('UNSAFE ' + SECRET, SECRET + '\n', None, [], 42):
            with self.subTest(code=code):
                error = ProviderError(code, True)
                self.assertEqual(error.code, 'provider_error')
                self.assertNotIn(SECRET, repr(error))
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=value):
                self.assertEqual(ProviderError('http_error', True, retry_after=value).retry_after, 0)

    def test_programmatic_large_integer_delays_still_clamp_without_overflow(self):
        self.assertEqual(ProviderError('http_error', True, retry_after=10 ** 1000).retry_after, 30)
        self.assertEqual(ProviderError('http_error', True, retry_after=-(10 ** 1000)).retry_after, 0)

    async def test_corrupt_compressed_response_is_retryable_and_closes_stream(self):
        error = await self.stream_error(200, b'not a gzip stream ' + SECRET.encode(),
                                        headers={'content-encoding': 'gzip'})
        self.assertEqual(error.code, 'invalid_provider_response')
        self.assertTrue(error.retryable)

    async def test_corrupt_compressed_error_retains_http_status(self):
        for status, retryable in ((401, False), (503, True)):
            with self.subTest(status=status):
                error = await self.stream_error(status, b'not a gzip stream',
                                                headers={'content-encoding': 'gzip'})
                self.assertEqual((error.code, error.status_code, error.retryable),
                                 ('http_error', status, retryable))

    async def test_deep_json_keeps_success_and_http_error_classifications(self):
        body = b'[' * 2000 + b']' * 2000
        for status, code, retryable in [(200, 'invalid_provider_response', True),
                                         (502, 'http_error', True), (400, 'http_error', False)]:
            with self.subTest(status=status):
                error = await self.stream_error(status, body)
                self.assertEqual((error.code, error.retryable), (code, retryable))
                self.assertEqual(error.status_code, None if status == 200 else status)

    async def test_http_html_errors_and_billing_quota_are_safe(self):
        for status in (400, 502):
            with self.subTest(status=status):
                error = await self.stream_error(status, b'<html>' + SECRET.encode() + b'</html>')
                self.assertEqual((error.code, error.status_code, error.retryable),
                                 ('http_error', status, status == 502))
        for code in ('insufficient_quota', 'billing_hard_limit_reached'):
            with self.subTest(code=code), self.assertRaises(ProviderError) as caught:
                await self.reply('openai', {'error': {'code': code, 'message': SECRET}}, status=429)
            self.assertEqual((caught.exception.code, caught.exception.status_code, caught.exception.retryable),
                             ('quota_exhausted', 429, False))

    async def test_large_http_error_keeps_status_policy_with_bounded_body(self):
        for status, retryable in ((401, False), (503, True)):
            with self.subTest(status=status):
                error = await self.stream_error(status, b'x' * 262145)
                self.assertEqual((error.code, error.status_code, error.retryable),
                                 ('http_error', status, retryable))

    async def test_large_http_error_stops_reading_and_closes_the_stream(self):
        closed = []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'x' * 262144
                yield b'x'
                raise AssertionError('The bounded error body must stop here')
            async def aclose(self): closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(503, stream=Stream()))) as client:
            with self.assertRaises(ProviderError) as caught:
                await HTTPAgent('openai', 'test-model', SECRET, client=client).respond(self.request)
        self.assertEqual((caught.exception.code, caught.exception.retryable), ('http_error', True))
        self.assertTrue(closed)

    async def test_missing_or_null_usage_does_not_reconstruct_totals(self):
        for provider in ('openai', 'anthropic', 'gemini'):
            field = 'usageMetadata' if provider == 'gemini' else 'usage'
            for missing in (False, True):
                with self.subTest(provider=provider, missing=missing):
                    data = envelope(provider)
                    if missing: del data[field]
                    else: data[field] = None
                    reply = await self.reply(provider, data)
                    self.assertIsNone(reply.usage.input_tokens)
                    self.assertIsNone(reply.usage.output_tokens)
        data = envelope('gemini'); data['usageMetadata'] = {'totalTokenCount': 999}
        reply = await self.reply('gemini', data)
        self.assertIsNone(reply.usage.input_tokens)
        self.assertIsNone(reply.usage.output_tokens)

    async def test_invalid_nonadditive_breakdowns_preserve_known_totals(self):
        for provider, path, attribute in [
            ('openai', ('input_tokens_details', 'cached_tokens'), 'cached_input_tokens'),
            ('openai', ('output_tokens_details', 'reasoning_tokens'), 'reasoning_output_tokens'),
            ('anthropic', ('output_tokens_details', 'thinking_tokens'), 'reasoning_output_tokens'),
            ('gemini', ('cachedContentTokenCount',), 'cached_input_tokens'),
        ]:
            for invalid in (None, True, False, -1, '5', 1.5, []):
                with self.subTest(provider=provider, path=path, invalid=invalid):
                    data = envelope(provider)
                    usage = data['usageMetadata' if provider == 'gemini' else 'usage']
                    if len(path) == 2: usage[path[0]] = {path[1]: invalid}
                    else: usage[path[0]] = invalid
                    reply = await self.reply(provider, data)
                    self.assertEqual(getattr(reply.usage, attribute), 0)
                    self.assertEqual(reply.usage.output_tokens, 20)
                    self.assertEqual(reply.usage.input_tokens, 80 if provider == 'anthropic' else 100)

    def test_invalid_credentials_fail_before_client_creation(self):
        for key in ('', 'key\rvalue', 'key\nvalue'):
            with self.subTest(key=key), self.assertRaises(ValueError) as error:
                HTTPAgent('openai', 'test-model', key)
            self.assertEqual(str(error.exception), 'Invalid credential format')

    async def test_close_respects_owned_and_borrowed_clients(self):
        owned = HTTPAgent('openai', 'test-model', SECRET)
        await owned.close()
        self.assertTrue(owned._client.is_closed)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=envelope('openai')))) as client:
            borrowed = HTTPAgent('openai', 'test-model', SECRET, client=client)
            await borrowed.close()
            self.assertFalse(client.is_closed)
            self.assertEqual((await borrowed.respond(self.request)).status, 'ok')
