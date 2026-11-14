"""Offline integration through all three real HTTP serializers and the engine.

Synthetic HTTP responses exercise infrastructure, not any model's intelligence.
"""
import base64
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import run_match
from parallax_relay.protocol import ROLES
from parallax_relay.providers import HTTPAgent
from parallax_relay.recording import Recorder
from parallax_relay.scripted import PLAN
from test_providers import response_for


class HTTPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_wire_adapters_complete_match_with_one_rate_limit_retry(self):
        providers = dict(zip(ROLES, ('openai', 'anthropic', 'gemini')))
        seen = []
        throttled = False

        def handler(req):
            nonlocal throttled
            body = json.loads(req.content)
            if req.url.host == 'api.openai.com':
                provider = 'openai'
                content = body['input'][0]['content']
                image = content[0]['image_url'].split(',', 1)[1]
                payload = json.loads(content[1]['text'])
            elif req.url.host == 'api.anthropic.com':
                provider = 'anthropic'
                content = body['messages'][0]['content']
                image = content[0]['source']['data']
                payload = json.loads(content[1]['text'])
            else:
                provider = 'gemini'
                content = body['contents'][0]['parts']
                image = content[0]['inlineData']['data']
                payload = json.loads(content[1]['text'])
            self.assertTrue(base64.b64decode(image).startswith(b'\x89PNG'))
            role, phase, turn = payload['role'], payload['phase'], payload['turn']
            self.assertEqual(provider, providers[role])
            self.assertNotIn('state_after', payload)
            self.assertNotIn('PRIVATE_KEY_FIXTURE', json.dumps(payload))
            for other in set(ROLES) - {role}:
                self.assertNotIn('note-for-' + other, json.dumps(payload))
            seen.append((role, phase, turn))
            if provider == 'anthropic' and not throttled:
                throttled = True
                return httpx.Response(429, json={'error': {'type': 'rate_limit_error'}}, headers={'retry-after': '0'})
            if phase == 'commit':
                reply = {'turn': turn, 'action': asdict(PLAN[turn][role]), 'notes': 'note-for-' + role}
            else:
                reply = {'turn': turn, 'message': role + ' ' + phase}
            return httpx.Response(200, json=response_for(provider, json.dumps(reply)))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agents = {r: HTTPAgent(p, 'test-model', 'PRIVATE_KEY_FIXTURE', client=client)
                      for r, p in providers.items()}
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'
                result = await run_match(agents, MatchSettings(retry_delay_seconds=0),
                                         recorder=Recorder(out, {'mode': 'mock'}))
                self.assertTrue(result.world.win)
                self.assertEqual(result.world.turn, 7)
                self.assertEqual(len(seen), 64)
                self.assertEqual(result.budget['calls_started'], 64)
                self.assertEqual(result.budget['reported_input_tokens'], 6300)
                self.assertEqual(result.budget['reported_output_tokens'], 1260)
                self.assertEqual(result.budget['unknown_usage_calls'], 1)
                for file in out.glob('*'):
                    if file.suffix in {'.json', '.jsonl', '.html'}:
                        self.assertNotIn('PRIVATE_KEY_FIXTURE', file.read_text(encoding='utf-8'))
