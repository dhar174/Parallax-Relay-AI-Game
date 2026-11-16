"""Behavior checks for protocol-v1 treatments and offline policies."""
import asyncio
from dataclasses import asdict
import hashlib
import json
import random
import unittest
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID

from parallax_relay.config import MatchSettings
from parallax_relay.protocol import ModelReply, Usage, ROLES, parse_reply
from parallax_relay.orchestrator import run_match
from parallax_relay.config import Rates
from parallax_relay.budget import Budget
from parallax_relay.protocol import AgentRequest, Observation


class ControlsTests(unittest.IsolatedAsyncioTestCase):
    async def test_conditions_reach_every_phase_and_later_turn_without_chat_leaks(self):
        from parallax_relay.conditions import CONDITIONS
        for name, condition in CONDITIONS.items():
            seen = {role: [] for role in ROLES}
            class Probe:
                async def respond(self, request):
                    seen[request.role].append(request)
                    payload = {'turn': request.turn}
                    if request.phase == 'commit':
                        payload.update(action={'kind': 'WAIT', 'direction': 0, 'steps': 0}, notes='own-note')
                    else:
                        payload['message'] = 'WITHHELD_SENTINEL'
                    return ModelReply(json.dumps(payload), Usage(0, 0))
            result = await run_match({r: Probe() for r in ROLES}, MatchSettings(condition=name, max_turns=2))
            self.assertEqual(result.budget['calls_started'], 6 * len(condition.phases))
            self.assertEqual(len(result.records), 2)
            for requests in seen.values():
                self.assertEqual([r.phase for r in requests], list(condition.phases) * 2)
                for request in requests:
                    self.assertEqual(request.include_image, condition.include_image)
                    self.assertTrue(request.observation.image_png.startswith(b'\x89PNG'))
                    if not condition.deliver_messages:
                        self.assertEqual(request.messages, ())
                        self.assertNotIn('WITHHELD_SENTINEL', request.prompt_text())
                        self.assertNotIn('fallback', request.prompt_text())
            if name == 'withheld':
                self.assertIn('WITHHELD_SENTINEL', json.dumps(result.phases))

    async def test_uniform_seed_matches_registered_derivation_and_retry_is_stable(self):
        from parallax_relay.policies import UniformAgent, canonical_actions
        from parallax_relay.protocol import AgentRequest, Observation
        trial = UUID('b81b3e0a-61cc-45fd-83c6-f871291c98af')
        for role in ROLES:
            agent = UniformAgent(role, trial)
            for turn in (0, 4, 1, 4):
                request = AgentRequest(Observation(role, turn, '{}', b''), 'commit')
                key = json.dumps(['uniform-v1', str(trial), role, turn], sort_keys=True,
                                 separators=(',', ':'), ensure_ascii=True).encode()
                seed = int.from_bytes(hashlib.sha256(key).digest()[:8], 'big')
                expected = canonical_actions(role)[random.Random(seed).randrange(len(canonical_actions(role)))]
                first, second = await agent.respond(request), await agent.respond(request)
                self.assertEqual(first, second)
                self.assertEqual(asdict(parse_reply(first.text, 'commit', turn).action.to_engine()), asdict(expected))

    async def test_wait_policy_uses_normal_engine_deadline(self):
        from parallax_relay.policies import WaitAgent
        result = await run_match({r: WaitAgent(r) for r in ROLES}, MatchSettings(condition='disabled'))
        self.assertEqual(result.stop_reason, 'defeat')
        self.assertEqual(result.budget['calls_started'], 36)
        self.assertTrue(all(not n for t in result.records for n in t['private_notes'].values()))

    async def test_adapters_omit_only_images_and_quotes_drop_image_reserve(self):
        from parallax_relay.providers import HTTPAgent
        request = AgentRequest(Observation('SPECTRA', 0, '{"own":"HUD_SENTINEL"}', b'PNG_SENTINEL'), 'commit')
        from dataclasses import replace
        without = replace(request, include_image=False, condition='no_images')
        for provider in ('openai', 'anthropic', 'gemini'):
            agent = HTTPAgent(provider, 'test-model', 'fake-key')
            try:
                _, _, body = agent._wire_request(without)
                encoded = json.dumps(body)
                self.assertIn('HUD_SENTINEL', encoded)
                for forbidden in ('input_image', 'inlineData', 'base64', 'image/png'):
                    self.assertNotIn(forbidden, encoded)
            finally:
                await agent.close()
        rates = {r: Rates(input_per_million=1, output_per_million=1) for r in ROLES}
        settings = MatchSettings()
        a, b = Budget(settings, rates), Budget(settings, rates)
        with_tickets = a.reserve_phase({r: request for r in ROLES})
        without_tickets = b.reserve_phase({r: without for r in ROLES})
        # Notices differ slightly; compare the quote with the reserve explicitly zeroed.
        reserve = settings.image_token_reserve
        from decimal import Decimal
        expected=reserve+len(request.prompt_text().encode('utf-8'))-len(without.prompt_text().encode('utf-8'))
        self.assertEqual(with_tickets['SPECTRA'].quote-without_tickets['SPECTRA'].quote,Decimal(expected)/Decimal(1000000))

    async def test_withheld_retry_and_failure_metadata_never_reaches_later_requests(self):
        seen = []
        class Probe:
            async def respond(self, request):
                seen.append(request)
                if not request.repair:
                    return ModelReply('WITHHELD_SENTINEL invalid JSON', Usage(1, 1))
                payload = {'turn': request.turn}
                payload.update({'action': {'kind': 'WAIT', 'direction': 0, 'steps': 0}, 'notes': ''}
                               if request.phase == 'commit' else {'message': 'WITHHELD_SENTINEL'})
                return ModelReply(json.dumps(payload), Usage(1, 1))
        result = await run_match({r: Probe() for r in ROLES}, MatchSettings(condition='withheld', max_turns=2, retry_delay_seconds=0))
        self.assertEqual(result.budget['calls_started'], 36)
        for request in seen:
            self.assertEqual(request.messages, ())
            self.assertNotIn('WITHHELD_SENTINEL', request.prompt_text())
            self.assertNotIn('fallback', request.prompt_text())


class CompatibilityTests(unittest.TestCase):
    def test_legacy_reader_does_not_require_new_settings_or_rewrite_hashes(self):
        from parallax_relay.provenance import RunProvenance, read_provenance, canonical_hash
        from parallax_relay.state import initial_world
        data = json.loads(Path('tests/fixtures/legacy_provenance_v2.json').read_text())['provenance']
        data['schema_version'] = 1
        execution = data['execution']['value']
        execution['settings'].pop('condition')
        execution.pop('policy')
        execution['conditions'] = {'communication': 'full', 'observations': 'role_png_and_hud'}
        data['execution']['sha256'] = canonical_hash(execution)
        original = copy.deepcopy(data)
        self.assertEqual(read_provenance({'provenance': data}), original)
        self.assertEqual(data, original)

    def test_conditions_reject_conflicting_and_malformed_selectors(self):
        from pydantic import ValidationError
        for bad in ([], {}, True, 'unknown'):
            with self.assertRaises(ValidationError):
                MatchSettings(condition=bad)
        with self.assertRaises(ValidationError):
            MatchSettings(condition='disabled', communication_rounds=2)

    def test_cli_uniform_provenance_and_argument_rejection(self):
        from parallax_relay.provenance import read_provenance
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            command = [sys.executable, '-m', 'parallax_relay.play', '--mock', '--quiet',
                       '--policy', 'uniform', '--condition', 'no_images', '--max-turns', '1',
                       '--trial-id', 'b81b3e0a-61cc-45fd-83c6-f871291c98af', '--out', str(out)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(completed.returncode, 0, completed.stderr)
            provenance = read_provenance(json.loads((out / 'manifest.json').read_text(encoding='utf-8')))
            self.assertEqual(provenance['execution']['value']['policy']['name'], 'uniform')
            self.assertEqual(provenance['execution']['value']['conditions']['arm'], 'no_images')
            self.assertEqual(len(provenance['execution']['value']['policy']['commitment_seeds']['PYRA']), 1)
            for argv in (['--mock', '--policy', 'uniform'], ['--check', '--policy', 'wait'],
                         ['--mock', '--condition', 'withheld', '--fast']):
                completed = subprocess.run([sys.executable, '-m', 'parallax_relay.play', *argv],
                                           capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(completed.returncode, 2)
                self.assertNotIn('Traceback', completed.stderr)
