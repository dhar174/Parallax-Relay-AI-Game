"""Independent wire expectations; sources/pins and coverage in docs/API_SOURCES.md.

Only the HTTP boundary is intercepted. No provider SDK or live service is used.
"""
import base64
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from parallax_relay.config import MatchSettings, Rates
from parallax_relay.budget import Budget
from parallax_relay.observations import observe
from parallax_relay.protocol import AgentRequest, ROLES
from parallax_relay.providers import HTTPAgent, ProviderError
from parallax_relay.state import initial_world
from parallax_relay.agents import ScriptedAgent
from parallax_relay.orchestrator import run_match
from parallax_relay.recording import Recorder

TEXT = '{"turn":0,"message":"hello"}'
SECRET = 'PRIVATE_PROVIDER_SENTINEL'


def envelope(provider):
    # Independent minimal REST examples, not _wire_request/_decode output.
    if provider == 'openai':
        return {'status': 'completed', 'error': None, 'output': [
            {'type': 'message', 'role': 'assistant', 'status': 'completed',
             'content': [{'type': 'output_text', 'text': TEXT}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 20}}
    if provider == 'anthropic':
        return {'type': 'message', 'role': 'assistant', 'stop_reason': 'end_turn',
                'content': [{'type': 'text', 'text': TEXT}],
                'usage': {'input_tokens': 80, 'output_tokens': 20}}
    return {'candidates': [{'finishReason': 'STOP', 'content': {
        'role': 'model', 'parts': [{'text': TEXT}]}}],
        'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 15,
                          'thoughtsTokenCount': 5}}


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def reply(self, provider, payload, *, request=None, status=200, headers=None):
        def handle(req):
            return httpx.Response(status, json=payload, headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            agent = HTTPAgent(provider, 'test-model', SECRET, client=client)
            return await agent.respond(request or AgentRequest(observe(initial_world(), 'SPECTRA'), 'broadcast'))

    async def test_openai_failed_envelopes_are_sanitized_provider_errors(self):
        for code, retryable in [('server_error', True), ('rate_limit_exceeded', True),
                                ('invalid_prompt', False), ('invalid_image', False), (SECRET, False)]:
            with self.subTest(code=code):
                data = envelope('openai')
                data.update(status='failed', error={'code': code, 'message': SECRET}, output=[])
                with self.assertRaises(ProviderError) as caught:
                    await self.reply('openai', data)
                self.assertEqual(caught.exception.code, 'response_failed')
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertNotIn(SECRET, repr(caught.exception))

    async def test_openai_content_filter_is_refusal_not_truncation(self):
        data = envelope('openai')
        data.update(status='incomplete', incomplete_details={'reason': 'content_filter'})
        reply = await self.reply('openai', data)
        self.assertEqual(reply.status, 'refusal')
        self.assertEqual(reply.text, '')
        self.assertEqual(reply.usage.output_tokens, 20)

    async def test_openai_refusal_is_not_hidden_by_commentary_filtering(self):
        data = envelope('openai')
        data['output'].insert(0, {'type': 'message', 'phase': 'commentary',
            'content': [{'type': 'refusal', 'refusal': SECRET}]})
        reply = await self.reply('openai', data)
        self.assertEqual(reply.status, 'refusal')
        self.assertEqual(reply.text, '')

    async def test_openai_explicit_unfinished_messages_never_become_actions(self):
        for status in ('incomplete', 'in_progress'):
            with self.subTest(status=status):
                data = envelope('openai'); data['output'][0]['status'] = status
                reply = await self.reply('openai', data)
                self.assertEqual(reply.status, 'incomplete')

    async def test_openai_commentary_and_reasoning_are_excluded_from_final_reply(self):
        data = envelope('openai'); data['output'][0]['phase'] = 'final_answer'
        data['output'][:0] = [
            {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': SECRET}]},
            {'type': 'message', 'phase': 'commentary', 'status': 'completed',
             'content': [{'type': 'output_text', 'text': SECRET}]}]
        reply = await self.reply('openai', data)
        self.assertEqual(reply.text, TEXT)
        self.assertEqual(reply.status, 'ok')
        data['output'] = data['output'][:2]
        self.assertEqual((await self.reply('openai', data)).status, 'incomplete')

    async def test_invalid_additive_token_counters_keep_the_aggregate_unknown(self):
        for provider, field, total in [('gemini', 'thoughtsTokenCount', 'output_tokens'),
                                       ('anthropic', 'cache_read_input_tokens', 'input_tokens'),
                                       ('anthropic', 'cache_creation_input_tokens', 'input_tokens')]:
            for invalid in (None, True, -1, 1.5, '5'):
                with self.subTest(provider=provider, field=field, invalid=invalid):
                    data = envelope(provider)
                    data['usageMetadata' if provider == 'gemini' else 'usage'][field] = invalid
                    reply = await self.reply(provider, data)
                    self.assertIsNone(getattr(reply.usage, total))
                    self.assertEqual(reply.status, 'ok')

    async def test_anthropic_thinking_usage_is_metadata_not_added_to_output(self):
        data = envelope('anthropic')
        data['usage'].update(cache_read_input_tokens=20, cache_creation_input_tokens=10,
                             output_tokens_details={'thinking_tokens': 5})
        data['content'].insert(0, {'type': 'thinking', 'thinking': SECRET})
        reply = await self.reply('anthropic', data)
        self.assertEqual(reply.text, TEXT)
        self.assertEqual(reply.usage.input_tokens, 110)
        self.assertEqual(reply.usage.output_tokens, 20)
        self.assertEqual(reply.usage.reasoning_output_tokens, 5)

    async def test_unknown_aggregates_retain_real_budget_reservations(self):
        for provider in ('gemini', 'anthropic'):
            with self.subTest(provider=provider):
                data = envelope(provider)
                if provider == 'gemini': data['usageMetadata']['thoughtsTokenCount'] = 'bad'
                else: data['usage']['cache_creation_input_tokens'] = 'bad'
                request = AgentRequest(observe(initial_world(), 'SPECTRA'), 'broadcast')
                rates = {r: Rates(input_per_million=1, output_per_million=2) for r in ROLES}
                budget = Budget(MatchSettings(), rates)
                tickets = budget.reserve_phase({r: request for r in ROLES})
                ticket = tickets['SPECTRA']; estimate = ticket.quote
                ticket.start(); ticket.settle((await self.reply(provider, data)).usage)
                for item in tickets.values(): item.release()
                self.assertEqual(budget.spent, estimate)
                self.assertEqual(budget.unknown_usage_calls, 1)
                self.assertEqual(budget.calls_started, 1)
                self.assertEqual(budget.reserved_calls, 0)
                self.assertEqual(budget.reserved_usd, 0)

    async def test_all_phases_use_the_documented_request_contract(self):
        # Minimal shared keyword subset corroborated by all three references.
        for provider in ('openai', 'anthropic', 'gemini'):
            for phase in ('broadcast', 'negotiate', 'commit'):
                with self.subTest(provider=provider, phase=phase):
                    observation = observe(initial_world(), 'FLUX')
                    request = AgentRequest(observation, phase, max_output_tokens=3072)
                    seen = []
                    def handle(req):
                        seen.append(req)
                        return httpx.Response(200, json=envelope(provider))
                    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                        await HTTPAgent(provider, 'test-model', SECRET, client=client).respond(request)
                    req = seen[0]; body = json.loads(req.content)
                    self.assertEqual(req.method, 'POST')
                    self.assertEqual(req.url.query, b'')
                    self.assertNotIn(SECRET, json.dumps(body))
                    for key in ('tools', 'previous_response_id', 'conversation', 'temperature', 'top_p', 'seed'):
                        self.assertNotIn(key, body)
                    if provider == 'openai':
                        self.assertEqual(str(req.url), 'https://api.openai.com/v1/responses')
                        self.assertEqual(req.headers['authorization'], 'Bearer ' + SECRET)
                        self.assertEqual(body['model'], 'test-model')
                        self.assertIs(body['store'], False)
                        self.assertEqual(body['max_output_tokens'], 3072)
                        content = body['input'][0]['content']; self.assertEqual(body['input'][0]['role'], 'user')
                        self.assertEqual(content[0]['type'], 'input_image')
                        self.assertEqual(content[0]['detail'], 'high')
                        self.assertTrue(content[0]['image_url'].startswith('data:image/png;base64,'))
                        image = content[0]['image_url'].split(',', 1)[1]
                        prompt = content[1]['text']; self.assertEqual(content[1]['type'], 'input_text')
                        fmt = body['text']['format']; self.assertEqual(fmt['type'], 'json_schema')
                        self.assertIs(fmt['strict'], True)
                        self.assertEqual(fmt['name'], 'parallax_' + phase)
                        schema = fmt['schema']
                    elif provider == 'anthropic':
                        self.assertEqual(str(req.url), 'https://api.anthropic.com/v1/messages')
                        self.assertEqual(req.headers['x-api-key'], SECRET)
                        self.assertEqual(req.headers['anthropic-version'], '2026-10-21')
                        self.assertEqual(body['model'], 'test-model')
                        self.assertEqual(body['max_tokens'], 3072)
                        content = body['messages'][0]['content']; self.assertEqual(body['messages'][0]['role'], 'user')
                        self.assertEqual(content[0]['type'], 'image')
                        self.assertEqual(content[0]['source']['type'], 'base64')
                        self.assertEqual(content[0]['source']['media_type'], 'image/png')
                        image = content[0]['source']['data']; prompt = content[1]['text']
                        self.assertEqual(body['output_config']['format']['type'], 'json_schema')
                        schema = body['output_config']['format']['schema']
                        self.assertNotIn('anthropic-beta', req.headers)
                    else:
                        self.assertEqual(str(req.url), 'https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent')
                        self.assertEqual(req.headers['x-goog-api-key'], SECRET)
                        content = body['contents'][0]['parts']; self.assertEqual(body['contents'][0]['role'], 'user')
                        self.assertEqual(content[0]['inlineData']['mimeType'], 'image/png')
                        image = content[0]['inlineData']['data']; prompt = content[1]['text']
                        config = body['generationConfig']
                        self.assertEqual(config['maxOutputTokens'], 3072)
                        self.assertEqual(config['candidateCount'], 1)
                        self.assertEqual(config['responseMimeType'], 'application/json')
                        self.assertNotIn('responseFormat', config)
                        self.assertNotIn('responseSchema', config)
                        schema = config['responseJsonSchema']
                    self.assertEqual(base64.b64decode(image), observation.image_png)
                    self.assertEqual(json.loads(prompt)['role'], 'FLUX')
                    self.assertEqual(json.loads(prompt)['phase'], phase)
                    expected = {'type': 'object', 'additionalProperties': False,
                                'properties': {'turn': {'type': 'integer'}}}
                    if phase == 'commit':
                        expected['properties'].update(action={
                            'type': 'object', 'additionalProperties': False,
                            'properties': {'kind': {'type': 'string', 'enum': ['MOVE', 'WAIT', 'VENT', 'REROUTE', 'COLLECT', 'UNLOCK']},
                                           'direction': {'type': 'integer'}, 'steps': {'type': 'integer'}},
                            'required': ['kind', 'direction', 'steps']}, notes={'type': 'string'})
                    else: expected['properties']['message'] = {'type': 'string'}
                    expected['required'] = list(expected['properties'])
                    def without_descriptions(value):
                        if isinstance(value, dict):
                            return {k: without_descriptions(v) for k, v in value.items() if k != 'description'}
                        if isinstance(value, list): return [without_descriptions(v) for v in value]
                        return value
                    self.assertEqual(without_descriptions(schema), expected)

    async def test_documented_stops_and_legacy_openai_messages(self):
        for provider, field, cases in [
            ('openai', 'status', [('completed', 'ok'), ('incomplete', 'incomplete'), ('in_progress', 'incomplete')]),
            ('anthropic', 'stop_reason', [('end_turn', 'ok'), ('max_tokens', 'incomplete'), ('refusal', 'refusal'),
                                         ('tool_use', 'incomplete'), ('pause_turn', 'incomplete')]),
            ('gemini', 'finishReason', [('STOP', 'ok'), ('MAX_TOKENS', 'incomplete'), ('SAFETY', 'refusal'),
                                       ('RECITATION', 'refusal'), ('BLOCKLIST', 'refusal'), ('SPII', 'refusal'),
                                       ('PROHIBITED_CONTENT', 'refusal'), ('IMAGE_SAFETY', 'refusal'), ('OTHER', 'incomplete')])]:
            for stop, expected in cases:
                with self.subTest(provider=provider, stop=stop):
                    data = envelope(provider)
                    target = data['candidates'][0] if provider == 'gemini' else data
                    target[field] = stop
                    reply = await self.reply(provider, data)
                    self.assertEqual(reply.status, expected)
        legacy = envelope('openai'); legacy['output'][0].pop('status')
        self.assertEqual((await self.reply('openai', legacy)).text, TEXT)
        for feedback, status in [({}, 'incomplete'), ({'blockReason': 'SAFETY'}, 'refusal')]:
            reply = await self.reply('gemini', {'promptFeedback': feedback})
            self.assertEqual(reply.status, status)

    async def test_usage_totals_do_not_double_count_breakdowns(self):
        data = envelope('openai')
        data['usage'].update(input_tokens_details={'cached_tokens': 10},
                             output_tokens_details={'reasoning_tokens': 5})
        reply = await self.reply('openai', data)
        self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens,
                          reply.usage.cached_input_tokens, reply.usage.reasoning_output_tokens), (100, 20, 10, 5))
        data = envelope('gemini'); data['usageMetadata']['cachedContentTokenCount'] = 10
        reply = await self.reply('gemini', data)
        self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens,
                          reply.usage.cached_input_tokens, reply.usage.reasoning_output_tokens), (100, 20, 10, 5))

    async def test_missing_null_and_invalid_core_usage_stays_unknown(self):
        for provider, container, fields in [('openai', 'usage', ('input_tokens', 'output_tokens')),
                                           ('anthropic', 'usage', ('input_tokens', 'output_tokens')),
                                           ('gemini', 'usageMetadata', ('promptTokenCount', 'candidatesTokenCount'))]:
            for field, aggregate in zip(fields, ('input_tokens', 'output_tokens')):
                for invalid in (None, True, -1, 1.5, '5'):
                    with self.subTest(provider=provider, field=field, invalid=invalid):
                        data = envelope(provider); data[container][field] = invalid
                        self.assertIsNone(getattr((await self.reply(provider, data)).usage, aggregate))
                data = envelope(provider); data[container].pop(field)
                self.assertIsNone(getattr((await self.reply(provider, data)).usage, aggregate))

    async def test_malformed_envelopes_are_safe_retryable_errors(self):
        for provider, invalid in [('openai', []), ('openai', {'output': [None]}),
                                  ('anthropic', {'content': [None]}), ('gemini', {'candidates': [None]}),
                                  ('gemini', {'usageMetadata': SECRET})]:
            with self.subTest(provider=provider, invalid=invalid):
                with self.assertRaises(ProviderError) as caught: await self.reply(provider, invalid)
                self.assertEqual(caught.exception.code, 'invalid_provider_response')
                self.assertTrue(caught.exception.retryable)
                self.assertNotIn(SECRET, repr(caught.exception))

    async def test_http_and_transport_failures_follow_bounded_safe_policy(self):
        for provider in ('openai', 'anthropic', 'gemini'):
            for status in (400, 401, 403, 404, 422, 307, 408, 409, 429, 500, 503, 529):
                with self.subTest(provider=provider, status=status):
                    with self.assertRaises(ProviderError) as caught:
                        await self.reply(provider, {'error': {'message': SECRET}}, status=status,
                                         headers={'retry-after': '60', 'location': 'https://example.invalid'})
                    error = caught.exception
                    self.assertEqual(error.retryable, status in (408, 409, 429, 500, 503, 529))
                    self.assertEqual(error.retry_after, 30)
                    self.assertNotIn(SECRET, repr(error))
            for exception, code in [(httpx.ReadTimeout(SECRET), 'timeout'), (httpx.ConnectError(SECRET), 'network_error')]:
                def handle(req): raise exception
                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    with self.assertRaises(ProviderError) as caught:
                        await HTTPAgent(provider, 'test-model', SECRET, client=client).respond(
                            AgentRequest(observe(initial_world(), 'SPECTRA'), 'broadcast'))
                self.assertEqual(caught.exception.code, code)
                self.assertTrue(caught.exception.retryable)
                self.assertNotIn(SECRET, repr(caught.exception))

    async def test_oversize_and_invalid_json_responses_close_streams(self):
        for content, code in [(b'x' * 262145, 'response_too_large'), (b'not json', 'invalid_provider_response')]:
            closed = []
            class Stream(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield content[:131072]
                    yield content[131072:]
                async def aclose(self): closed.append(True)
            def handle(req): return httpx.Response(200, stream=Stream())
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                with self.assertRaises(ProviderError) as caught:
                    await HTTPAgent('openai', 'test-model', SECRET, client=client).respond(
                        AgentRequest(observe(initial_world(), 'SPECTRA'), 'broadcast'))
            self.assertEqual(caught.exception.code, code)
            self.assertTrue(closed)

    async def test_failed_responses_have_bounded_driver_retries_and_safe_artifacts(self):
        for code, stop, attempts, turns in [('server_error', 'turn_limit', 6, 1),
                                            ('invalid_prompt', 'provider_error', 1, 0)]:
            with self.subTest(code=code):
                def handle(req):
                    return httpx.Response(200, json={'status': 'failed', 'output': [],
                        'error': {'code': code, 'message': SECRET}})
                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    agents = {r: ScriptedAgent(r) for r in ROLES}
                    agents['SPECTRA'] = HTTPAgent('openai', 'test-model', SECRET, client=client)
                    with tempfile.TemporaryDirectory() as tmp:
                        out = Path(tmp) / 'run'
                        result = await run_match(agents, MatchSettings(max_turns=1, max_consecutive_failures=20,
                                                  retry_delay_seconds=0), recorder=Recorder(out, {'mode': 'intercepted'}))
                        self.assertEqual(result.stop_reason, stop)
                        self.assertEqual(result.world.turn, turns)
                        failures = [c for c in result.calls if c['role'] == 'SPECTRA']
                        self.assertEqual(len(failures), attempts)
                        self.assertTrue(all(c['status'] == 'response_failed' for c in failures))
                        self.assertEqual(result.budget['calls_started'], attempts + (6 if turns else 2))
                        self.assertEqual(result.budget['unknown_usage_calls'], attempts)
                        for file in out.iterdir():
                            if file.suffix in ('.json', '.jsonl', '.html'):
                                self.assertNotIn(SECRET, file.read_text(encoding='utf-8'))
