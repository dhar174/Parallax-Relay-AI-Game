"""Counter-origin evidence must not change accounting or copy provider text."""
from dataclasses import asdict
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.orchestrator import run_match
from parallax_relay.providers import _decode
from parallax_relay.protocol import ModelReply, ROLES, Usage
from parallax_relay.recording import Recorder


class UsageEvidenceTests(unittest.TestCase):
    def test_anthropic_cache_origin_preserves_null_versus_omitted(self):
        for state, extra, total in (
            ('omitted', {}, 80),
            ('null', {'cache_read_input_tokens': None}, None),
            ('count', {'cache_read_input_tokens': 0}, 80),
            ('count', {'cache_read_input_tokens': 12}, 92),
            ('invalid', {'cache_read_input_tokens': 'SECRET_SENTINEL'}, None),
        ):
            with self.subTest(state=state, total=total):
                reply = _decode('anthropic', {
                    'stop_reason': 'end_turn', 'content': [],
                    'usage': {'input_tokens': 80, 'output_tokens': 20, **extra,
                              'unrecognized': 'SECRET_SENTINEL'},
                })
                self.assertEqual(reply.usage.input_tokens, total)
                self.assertEqual(reply.usage.output_tokens, 20)
                evidence = getattr(reply.usage, 'source_usage', None)
                self.assertIsNotNone(evidence, 'Counter origin is currently lost')
                self.assertEqual(evidence['usage.cache_read_input_tokens'], {
                    'state': state,
                    'value': extra['cache_read_input_tokens'] if state == 'count' else None,
                })
                self.assertNotIn('SECRET_SENTINEL', json.dumps(asdict(reply.usage)))

    def test_openai_and_gemini_allowlisted_breakdowns(self):
        for provider, data, key, output in (
            ('openai', {'usage': {'input_tokens': 100, 'output_tokens': 20,
                'output_tokens_details': {'reasoning_tokens': 5}}},
                'usage.output_tokens_details.reasoning_tokens', 20),
            ('gemini', {'usageMetadata': {'promptTokenCount': 100,
                'candidatesTokenCount': 15, 'thoughtsTokenCount': 5}},
                'usageMetadata.thoughtsTokenCount', 20),
        ):
            with self.subTest(provider=provider):
                reply = _decode(provider, data)
                self.assertEqual(reply.usage.output_tokens, output)
                evidence = getattr(reply.usage, 'source_usage', None)
                self.assertIsNotNone(evidence, 'Counter origin is currently lost')
                self.assertEqual(evidence[key], {'state': 'count', 'value': 5})

    def test_existing_positional_usage_remains_valid(self):
        usage = Usage(1, 2, 3, 4)
        self.assertEqual((usage.input_tokens, usage.output_tokens,
                          usage.cached_input_tokens, usage.reasoning_output_tokens), (1, 2, 3, 4))
        self.assertIsNone(getattr(usage, 'source_usage', None))

    def test_counter_evidence_is_immutable_hashable_and_json_serializable(self):
        original = {'usage.input_tokens': {'state': 'count', 'value': 3}}
        usage = Usage(3, 4, source_usage=original)
        original['usage.input_tokens']['value'] = 999
        self.assertEqual(usage.source_usage['usage.input_tokens']['value'], 3)
        with self.assertRaises(TypeError):
            usage.source_usage['usage.input_tokens']['value'] = 999
        with self.assertRaises(TypeError):
            usage.source_usage.update(other={})
        self.assertEqual(hash(usage), hash(Usage(3, 4, source_usage={
            'usage.input_tokens': {'value': 3, 'state': 'count'}})))
        self.assertEqual(json.loads(json.dumps(asdict(usage)))['source_usage'], {
            'usage.input_tokens': {'state': 'count', 'value': 3}})

    def test_parent_counter_states_and_nonstring_invalid_values(self):
        for data, state in (({}, 'omitted'), ({'usage': None}, 'null'),
                            ({'usage': {'input_tokens_details': None}}, 'null')):
            with self.subTest(state=state, data=data):
                usage = _decode('openai', data).usage
                self.assertEqual(usage.source_usage['usage.input_tokens_details.cached_tokens']['state'], state)
        for invalid in (True, False, -1, 1.5, [], {}):
            with self.subTest(invalid=invalid):
                usage = _decode('anthropic', {'usage': {'cache_read_input_tokens': invalid}}).usage
                self.assertEqual(usage.source_usage['usage.cache_read_input_tokens'],
                                 {'state': 'invalid', 'value': None})

    def test_recorded_null_counters_retain_estimates_without_provider_text(self):
        class InterceptedUsageAgent(ScriptedAgent):
            async def respond(self, request):
                scripted = await super().respond(request)
                usage = _decode('anthropic', {
                    'usage': {'input_tokens': 80, 'output_tokens': 20,
                              'cache_read_input_tokens': None,
                              'cache_creation_input_tokens': 'SECRET_SENTINEL'},
                }).usage
                return ModelReply(scripted.text, usage)

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            result = asyncio.run(run_match(
                {r: InterceptedUsageAgent(r) for r in ROLES},
                MatchSettings(max_turns=1, max_estimated_cost_usd=1),
                rates={r: Rates(input_per_million=0.1, output_per_million=0.5) for r in ROLES},
                recorder=Recorder(out, {})))
            self.assertEqual(result.stop_reason, 'turn_limit')
            self.assertEqual(result.budget['unknown_usage_calls'], 9)
            self.assertEqual(result.budget['reported_input_tokens'], 0)
            self.assertEqual(result.budget['reported_output_tokens'], 180)
            self.assertGreater(result.budget['estimated_cost_usd'], 0)
            calls = [json.loads(line) for line in (out / 'calls.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(calls), 9)
            for call in calls:
                self.assertEqual(call['usage']['source_usage']['usage.cache_read_input_tokens'],
                                 {'state': 'null', 'value': None})
            for path in out.iterdir():
                if path.suffix in {'.json', '.jsonl', '.html'}:
                    self.assertNotIn('SECRET_SENTINEL', path.read_text(encoding='utf-8'))
