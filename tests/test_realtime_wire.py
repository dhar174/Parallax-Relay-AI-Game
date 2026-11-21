"""Real HTTP encoders, role isolation, reservation identity and strict game replies."""
import base64
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import time
import unittest

import httpx

from parallax_relay.config import Rates
from parallax_relay.protocol import (
    AgentRequest, MAX_MESSAGE_CHARS, MAX_NOTES_CHARS, MAX_REPLY_CHARS, Observation,
    ReplyValidationError, ROLES,
)
from parallax_relay.provenance import canonical_hash, input_identities
from parallax_relay.providers import HTTPAgent
from parallax_relay.realtime import physics, wire
from parallax_relay.realtime.coordination import Coordinator
from parallax_relay.realtime.observations import observe
from parallax_relay.realtime.settings import Settings
from parallax_relay.state import initial_world as turn_based_world


def action(kind='WAIT', direction=None, ticks=None, jump_at=None):
    return dict(kind=kind, direction=direction, ticks=ticks, jump_at=jump_at)


WORKED_PROGRAM = [action('RUN', 1, 36, 0), action('WAIT', ticks=6), action('COLLECT')]
SETTINGS = Settings()


class RealtimeReplyTests(unittest.TestCase):
    def test_program_costs_and_half_open_endpoints(self):
        cases = [
            ([action('RUN', 1, 1, 0)], 3), ([action('RUN', -1, 15)], 1),
            ([action('RUN', 1, 16)], 2), ([action('RUN', 1, 90, 89)], 8),
            ([action('WAIT', ticks=120)], 0), (WORKED_PROGRAM, 7),
            ([action(k) for k in ('JUMP', 'VENT', 'REROUTE', 'COLLECT')], 8),
            ([action('RUN', 1, 90), action('WAIT', ticks=30)], 6),
        ]
        for program, cost in cases:
            with self.subTest(program=program):
                self.assertEqual(wire.validate_actions(program, SETTINGS), cost)
                payload = dict(request_id='slot', window=1, actions=program, notes='private')
                self.assertEqual(wire.parse(json.dumps(payload), 'commit', 1, 'slot', SETTINGS), payload)

    def test_whole_program_rejection_and_independent_limits(self):
        cases = [
            ([], 'commands'), ([action('WAIT', ticks=1)] * 5, 'commands'),
            ([action('RUN', 0, 1)], 'direction'), ([action('RUN', 1, 0)], 'ticks'),
            ([action('RUN', 1, 91)], 'ticks'), ([action('RUN', 1, 10, -1)], 'offset'),
            ([action('RUN', 1, 10, 10)], 'offset'), ([action('WAIT', ticks=121)], 'WAIT'),
            ([action('WAIT', -1, 15)], 'WAIT'), ([action('WAIT', ticks=15, jump_at=0)], 'WAIT'),
            ([action('JUMP', ticks=1)], 'null'), ([action('COLLECT', 1)], 'null'),
            ([action('VENT', jump_at=0)], 'null'), ([action('MOVE')], 'supported'),
            ([action('WAIT', ticks=120), action('VENT')], '121 ticks'),
            ([action('RUN', 1, 90, 0), action('REROUTE')], '10 points'),
        ]
        for program, reason in cases:
            with self.subTest(program=program):
                before = deepcopy(program)
                with self.assertRaises(wire.ActionPlanError) as rejected:
                    wire.validate_actions(program, SETTINGS)
                self.assertEqual(str(rejected.exception), 'invalid_action_plan')
                self.assertIn(reason, rejected.exception.detail)
                self.assertEqual(program, before)
        for settings in (Settings(window_ticks=42), Settings(action_points=6), Settings(max_commands=2)):
            with self.subTest(settings=settings), self.assertRaises(wire.ActionPlanError):
                wire.validate_actions(WORKED_PROGRAM, settings)
        self.assertEqual(wire.validate_actions(WORKED_PROGRAM, Settings(window_ticks=43, action_points=7,
                                                                       max_commands=3)), 7)

    def test_strict_bounded_json_and_host_identity(self):
        speech = dict(request_id='slot', window=1, message='hi')
        commit = dict(request_id='slot', window=1, actions=[action('WAIT', ticks=1)], notes='')
        bad = [
            ('broadcast', json.dumps({**speech, 'role': 'FLUX'}), 'invalid_json_schema'),
            ('negotiate', json.dumps({**speech, 'window': True}), 'invalid_json_schema'),
            ('broadcast', json.dumps({**speech, 'message': 'z' * (MAX_MESSAGE_CHARS + 1)}), 'invalid_json_schema'),
            ('broadcast', json.dumps({**speech, 'message': '\ud800'}), 'invalid_json_schema'),
            ('negotiate', json.dumps(commit), 'invalid_json_schema'), ('commit', json.dumps(speech), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'notes': 'z' * (MAX_NOTES_CHARS + 1)}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': {'kind': 'WAIT'}}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [dict(kind='JUMP', ticks=None)]}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [{**action('JUMP'), 'role': 'PYRA'}]}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [action('RUN', True, 9)]}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [action('RUN', 1, 1.0)]}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [action('RUN', 1, 9, '0')]}), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'actions': [action('WAIT', ticks=float('nan'))]}), 'invalid_json_schema'),
            ('commit', json.dumps(commit).replace('"kind":', '"kind":"JUMP","kind":'), 'invalid_json_schema'),
            ('broadcast', json.dumps(speech).replace('"window":', '"window":9,"window":'), 'invalid_json_schema'),
            ('commit', json.dumps({**commit, 'window': 2}), 'stale_window'),
            ('commit', json.dumps({**commit, 'request_id': 'previous-attempt'}), 'stale_request_id'),
            ('commit', json.dumps({**commit, 'actions': [action('RUN', 1, 5, 5)]}), 'invalid_action_plan'),
            ('broadcast', '[]', 'invalid_json_schema'), ('commit', '[' * 1400 + ']' * 1400, 'invalid_json_schema'),
            ('broadcast', 'x' * (MAX_REPLY_CHARS + 1), 'response_size'), ('broadcast', b'{}', 'response_size'),
        ]
        for phase, raw, code in bad:
            with self.subTest(phase=phase, code=code, prefix=repr(raw)[:100]):
                with self.assertRaises(ReplyValidationError) as rejected:
                    wire.parse(raw, phase, 1, 'slot', SETTINGS)
                self.assertEqual(str(rejected.exception), code)
        for phase in ('broadcast', 'negotiate'):
            exact = {**speech, 'message': 'ü' * MAX_MESSAGE_CHARS}
            self.assertEqual(wire.parse(json.dumps(exact), phase, 1, 'slot', SETTINGS), exact)
        exact = {**commit, 'notes': 'a' * MAX_NOTES_CHARS}
        self.assertEqual(wire.parse(json.dumps(exact), 'commit', 1, 'slot', SETTINGS), exact)

    def test_request_excludes_unpublished_speech_and_freezes_private_history(self):
        own = Observation('PYRA', 2, '{"role":"PYRA","window":2,"sample_tick":120}', b'current')
        message = dict(role='FLUX', window=2, phase='broadcast', text='Published.', readiness='sealed')
        prior = dict(window=1, observation={'role': 'PYRA', 'window': 1, 'sample_tick': 0, 'own': 'old'},
                     your_actions=[action('WAIT', ticks=12)], public_messages=[])
        request = wire.make_request(own, 'negotiate', [message], [prior], 'own note', 2, 'fresh', SETTINGS)
        original = request.prompt_text()
        message['text'] = 'changed'
        prior['observation']['own'] = 'changed'
        prior['your_actions'].clear()
        self.assertEqual(request.prompt_text(), original)
        public = json.loads(original)['public_messages']
        self.assertEqual(public, [dict(role='FLUX', window=2, phase='broadcast', text='Published.')])
        self.assertNotIn('readiness', original)
        for changed in ({'role': 'FLUX'}, {'window': 1}, {'window': True}, {'sample_tick': -1}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                stale = replace(own, hud_json=json.dumps({**own.hud, **changed}))
                wire.make_request(stale, 'broadcast', [], [], '', 2, 'fresh', SETTINGS)
        for phase, messages, history in [
                ('broadcast', [message], []),
                ('commit', [{**message, 'phase': 'commit'}], []),
                ('commit', [{**message, 'fallback': True}], []),
                ('commit', [], [{**prior, 'observation': {'role': 'FLUX', 'private': 'secret'}}]),
                ('commit', [], [{**prior, 'spectator': {'private': 'secret'}}]),
                ('commit', [], [{**prior, 'window': 2}])]:
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                wire.make_request(own, phase, messages, history, '', 2, 'fresh', SETTINGS)


def envelope(provider, answer):
    if provider == 'openai':
        return {'status': 'completed', 'output': [
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': answer}]}]}
    if provider == 'anthropic':
        return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': answer}]}
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': answer}]}}]}


def unpack_body(provider, body):
    if provider == 'openai':
        image, text = body['input'][0]['content']
        return (body['instructions'], body['text']['format']['schema'], body['max_output_tokens'],
                image['image_url'].split(',', 1)[1], text['text'])
    if provider == 'anthropic':
        image, text = body['messages'][0]['content']
        return (body['system'], body['output_config']['format']['schema'], body['max_tokens'],
                image['source']['data'], text['text'])
    image, text = body['contents'][0]['parts']
    return (body['systemInstruction']['parts'][0]['text'], body['generationConfig']['responseJsonSchema'],
            body['generationConfig']['maxOutputTokens'], image['inlineData']['data'], text['text'])


class RealtimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        world = physics.initial_world()
        cls.observations = {}
        for window in (1, 2):
            world.tick = (window - 1) * SETTINGS.window_ticks
            views = {}
            for role in ROLES:
                own = observe(world, role, window, SETTINGS)
                hud = {**own.hud, 'private_sentinel': f'private-HUD-{role}-{window}'}
                views[role] = replace(own, hud_json=json.dumps(hud))
            cls.observations[window] = views

    async def test_each_provider_round_trips_every_role_phase_and_retry(self):
        identity = wire.contract_identity()
        prices = {r: Rates(input_per_million=1, output_per_million=1) for r in ROLES}
        settings = Settings(max_attempts=2, max_calls=36, retry_delay_seconds=0,
                            max_estimated_cost_usd=None)
        for provider in ('openai', 'anthropic', 'gemini'):
            seen = {}
            quotes = {}
            ids = set()

            def handle(http_request):
                rules, schema, max_tokens, image, raw_prompt = unpack_body(provider, json.loads(http_request.content))
                prompt = json.loads(raw_prompt)
                role, window, phase = slot = (prompt['role'], prompt['window'], prompt['phase'])
                own = self.observations[window][role]
                self.assertEqual((max_tokens, base64.b64decode(image, validate=True)), (settings.max_output_tokens, own.image_png))
                self.assertEqual(prompt['observation'], own.hud)
                self.assertEqual(prompt['contract_version'], identity['version'])
                self.assertEqual(rules, wire.REALTIME_RULES)
                self.assertEqual(rules, identity['system_rules'])
                self.assertEqual(schema, identity['response_schemas'][phase])
                self.assertEqual(hashlib.sha256(rules.encode('utf-8')).hexdigest(), identity['system_rules_sha256'])
                self.assertEqual(canonical_hash(schema), identity['response_schema_sha256_by_phase'][phase])
                self.assertEqual(schema['additionalProperties'], False)
                self.assertIn('flat floor', rules)
                for other in set(ROLES) - {role}:
                    self.assertNotIn(f'private-HUD-{other}', raw_prompt)
                    self.assertNotIn(f'private-note-{other}', raw_prompt)
                self.assertNotIn('UNPARSED_REPLY_SENTINEL', raw_prompt)
                if window == 2:
                    previous = prompt['your_recent_history']
                    self.assertEqual(len(previous), 1)
                    self.assertEqual(previous[0]['observation'], self.observations[1][role].hud)
                    self.assertEqual(previous[0]['your_actions'], WORKED_PROGRAM)
                    self.assertEqual(prompt['your_private_notes'], f'private-note-{role}')
                prior_phases = wire.PHASES[:wire.PHASES.index(phase)]
                self.assertEqual([(m['phase'], m['role'], m['text']) for m in prompt['public_messages']],
                                 [(p, r, f'speech-{r}-{p}-{window}') for p in prior_phases for r in ROLES])
                if phase == 'commit':
                    self.assertEqual(set(schema['required']), {'request_id', 'window', 'actions', 'notes'})
                    item = schema['properties']['actions']['items']
                    self.assertEqual(item['required'], ['kind', 'direction', 'ticks', 'jump_at'])
                    self.assertFalse(item['additionalProperties'])
                    for name in ('direction', 'ticks', 'jump_at'):
                        self.assertEqual(item['properties'][name]['anyOf'], [{'type': 'integer'}, {'type': 'null'}])
                else:
                    self.assertEqual(set(schema['required']), {'request_id', 'window', 'message'})
                instance = prompt['request_id']
                self.assertNotIn(instance, ids)
                ids.add(instance)
                seen[slot] = seen.get(slot, 0) + 1
                if seen[slot] == 1:
                    text_bytes = len((rules + raw_prompt + json.dumps(schema)).encode('utf-8'))
                    units = text_bytes + settings.image_token_reserve + 2048 + max_tokens
                    quotes[slot] = Decimal(units) / Decimal(1000000)
                    self.assertEqual(prompt['format_repair'], '')
                    answer = 'UNPARSED_REPLY_SENTINEL'
                else:
                    self.assertTrue(prompt['format_repair'])
                    reply = dict(request_id=instance, window=window)
                    if phase == 'commit':
                        reply.update(actions=WORKED_PROGRAM, notes=f'private-note-{role}')
                    else:
                        reply['message'] = f'speech-{role}-{phase}-{window}'
                    answer = json.dumps(reply)
                return httpx.Response(200, json=envelope(provider, answer))

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                players = {r: HTTPAgent(provider, 'fixture-model', 'offline', client=client) for r in ROLES}
                coordinator = Coordinator(players, settings, prices, lambda *a, **kw: None)
                for window in (1, 2):
                    with self.subTest(provider=provider, window=window):
                        programs, _ = await coordinator.coordinate(self.observations[window], window, time.monotonic() + 20)
                        self.assertEqual(programs, dict.fromkeys(ROLES, WORKED_PROGRAM))
                self.assertTrue(await coordinator.close())
            self.assertEqual(list(seen.values()), [2] * 18)
            self.assertEqual(len(coordinator.attempts), 36)
            for attempt in coordinator.attempts:
                slot = (attempt['role'], attempt['window'], attempt['phase'])
                self.assertEqual(Decimal(attempt['reservation_quote_usd_decimal']), quotes[slot])
                self.assertEqual(attempt['settlement_basis'], 'retained_estimate')
            self.assertEqual(coordinator.budget.unknown_usage_calls, 36)
            self.assertEqual(coordinator.budget.reserved_calls, 0)

    async def test_turn_based_wire_bytes_and_provenance_match_prechange_values(self):
        # Captured with the original c18cd10 provider and protocol sources.
        expected = {
            'openai': {
                'broadcast': '328bc680b8370a5bf0d80dd5ed9ac18cc5c2a997e17a0051aae53fd1907507b3',
                'negotiate': '31ad35812a3fd29e218d5b6702352c4210454b05d731961dea96cee1c82e6cd7',
                'commit': '975c895f3c92e815c3e6833f4f647e279b5d0c833574c876858fcaa4e5bf4edf',
            },
            'anthropic': {
                'broadcast': 'dc8cfdff965a2e783146513a41ecfc8207ca3f75811315e0638897ae4b74269c',
                'negotiate': '8f9008d3b3113984b0ac4152e4a64e634e5b9665254580c28b8777af73e4b1ac',
                'commit': 'a691b11c6439cb7ff5dca9eb46ba50759fa2ea49c351443cd74733e6ea2603e6',
            },
            'gemini': {
                'broadcast': '21f008c390e22c077dfc1c584a3c19cd01779f4b7eb7aca3e500497de83a21d9',
                'negotiate': '7f784fa2be67aef1f7c3a079b9f9c077d33066bf115c28a1fdc068b3a34cd632',
                'commit': '5522acbcfcc3cf511cca52bd6255d4d8047df7ea147c0dad9349858ce3ec52ef',
            },
        }
        observation = Observation('SPECTRA', 0, '{}', b'\x89PNG\r\n\x1a\n')
        for provider, digests in expected.items():
            def handle(http_request):
                self.assertEqual(hashlib.sha256(http_request.content).hexdigest(), digest)
                return httpx.Response(200, json=envelope(provider, '{}'))

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                player = HTTPAgent(provider, 'fixture-model', 'offline', client=client)
                for phase, digest in digests.items():
                    with self.subTest(provider=provider, phase=phase):
                        reply = await player.respond(AgentRequest(observation, phase))
                        self.assertEqual((reply.status, reply.text), ('ok', '{}'))
        request = AgentRequest(observation, 'commit')
        self.assertEqual(canonical_hash(request.prompt_text()), 'b7da2d2727a88b529f8cc03aaf91379a716bff21e277b5705cc705a8bba95909')
        identity = input_identities(turn_based_world().snapshot())
        self.assertEqual(identity['prompt']['sha256'], 'b86f98934096b6841b520baa5948446ccc938310af27a0b46da2d43b61e008ee')
        self.assertEqual(identity['schemas']['sha256'], '3db198437651454610891d1d107c1b979bf44c8f72e83c6a175e79bd2667c65f')
