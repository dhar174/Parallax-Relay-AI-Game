"""CLI-only mock cost policy; all provider access is intercepted or forbidden."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import load_config
from parallax_relay.orchestrator import run_match
from parallax_relay.play import main
from parallax_relay.protocol import ROLES


class NoResponseAgent:
    def __init__(self, *args, **kwargs):
        pass

    async def respond(self, request):
        raise AssertionError('The cost guard must stop before responding')

    async def close(self):
        pass


class MockBudgetCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def config(self, cap=0.001, priced_roles=ROLES):
        text = Path('configs/three_models.toml').read_text(encoding='utf-8')
        if cap is not None:
            text = text.replace('[match]\n', f'[match]\nmax_estimated_cost_usd = {cap}\n')
        for role in priced_roles:
            text += f'\n[players.{role}.pricing]\ninput_per_million = 1\noutput_per_million = 2\n'
        path = self.root / 'config.toml'
        path.write_text(text, encoding='utf-8')
        return path

    def command(self, config, out, *args):
        env = os.environ.copy()
        for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI'):
            for suffix in ('MODEL', 'API_KEY'):
                env.pop(provider + '_' + suffix, None)
        return subprocess.run(
            [sys.executable, '-m', 'parallax_relay.play', '--mock', '--quiet',
             '--config', str(config), '--out', str(out), *args],
            capture_output=True, text=True, env=env, timeout=30)

    def artifacts(self, out):
        return (json.loads((out / 'result.json').read_text()),
                json.loads((out / 'manifest.json').read_text()))

    def test_priced_tiny_cap_mock_wins_in_normal_and_fast_modes(self):
        config = self.config()
        for args, calls, rounds in [((), 63, 2), (('--fast',), 42, 1)]:
            with self.subTest(args=args):
                out = self.root / f'mock-{rounds}'
                proc = self.command(config, out, *args)
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                result, manifest = self.artifacts(out)
                self.assertEqual((result['stop_reason'], result['turns'], result['energy']),
                                 ('victory', 7, 5))
                self.assertTrue(result['win'])
                self.assertEqual(result['scores'], dict.fromkeys(ROLES, 100))
                self.assertEqual(result['budget']['calls_started'], calls)
                for field in ('reported_input_tokens', 'reported_output_tokens',
                              'unknown_usage_calls', 'estimated_cost_usd'):
                    self.assertEqual(result['budget'][field], 0)
                requested = manifest['requested_settings']
                effective = manifest['settings']
                self.assertEqual(requested['max_estimated_cost_usd'], 0.001)
                self.assertIsNone(effective['max_estimated_cost_usd'])
                self.assertEqual(requested['communication_rounds'], rounds)
                self.assertEqual(effective, {**requested, 'max_estimated_cost_usd': None})
                self.assertEqual(manifest['mode'], 'mock')
                self.assertTrue(all(p == {'provider': 'mock', 'model': 'scripted-fixture'}
                                    for p in manifest['players'].values()))

    def test_mock_preserves_config_and_never_constructs_providers_or_reads_env(self):
        config = self.config()
        cfg = load_config(config)
        original = cfg.model_dump()
        out = self.root / 'guarded-mock'
        with patch('parallax_relay.play.load_config', return_value=cfg), \
             patch('parallax_relay.play.HTTPAgent', side_effect=AssertionError('No providers')), \
             patch('parallax_relay.play.load_env_file', side_effect=AssertionError('No env file')), \
             contextlib.redirect_stdout(io.StringIO()):
            code = main(['--mock', '--quiet', '--config', str(config), '--out', str(out),
                         '--env-file', str(self.root / 'missing.env')])
        self.assertEqual(code, 0)
        self.assertEqual(cfg.model_dump(), original)
        self.assertTrue(self.artifacts(out)[0]['win'])

    def test_mock_still_obeys_cli_turn_and_call_limits(self):
        config = self.config()
        cases = [('--max-turns', '1', 0, 'turn_limit', 1, 9),
                 ('--max-calls', '5', 4, 'call_budget', 0, 0)]
        for flag, value, code, reason, turns, calls in cases:
            with self.subTest(flag=flag):
                out = self.root / flag.removeprefix('--')
                proc = self.command(config, out, flag, value)
                self.assertEqual(proc.returncode, code, proc.stderr + proc.stdout)
                result, manifest = self.artifacts(out)
                self.assertEqual((result['stop_reason'], result['turns']), (reason, turns))
                self.assertEqual(result['budget']['calls_started'], calls)
                self.assertFalse(result['completed'])
                self.assertIsNone(result['scores'])
                key = flag.removeprefix('--').replace('-', '_')
                self.assertEqual(manifest['requested_settings'][key], int(value))
                self.assertEqual(manifest['settings'][key], int(value))
                self.assertEqual(manifest['settings'], {
                    **manifest['requested_settings'], 'max_estimated_cost_usd': None})

    def test_unpriced_and_partially_priced_mock_cost_remains_null(self):
        for roles in ((), ('SPECTRA',)):
            with self.subTest(priced_roles=roles):
                out = self.root / f'unpriced-{len(roles)}'
                proc = self.command(self.config(cap=None, priced_roles=roles), out)
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                result, manifest = self.artifacts(out)
                self.assertTrue(result['win'])
                self.assertIsNone(result['budget']['estimated_cost_usd'])
                self.assertEqual(manifest['requested_settings'], manifest['settings'])

    def test_mock_does_not_bypass_requested_config_validation(self):
        valid = self.config().read_text()
        cases = [self.config(priced_roles=ROLES[:-1]).read_text(),
                 valid.replace('input_per_million = 1', 'input_per_million = 0', 1),
                 valid.replace('input_per_million = 1', 'input_per_million = "SECRET_SENTINEL"', 1),
                 valid.replace('max_calls = 216', 'max_calls = 0')]
        config = self.root / 'invalid.toml'
        for index, text in enumerate(cases):
            with self.subTest(index=index):
                config.write_text(text, encoding='utf-8')
                out = self.root / f'invalid-{index}'
                proc = self.command(config, out)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertFalse(out.exists())
                self.assertNotIn('SECRET_SENTINEL', proc.stdout + proc.stderr)

    def test_synthetic_live_launcher_keeps_the_spending_guard(self):
        config = self.config()
        out = self.root / 'synthetic-live'
        values = {f'{provider}_{suffix}': 'test-model' if suffix == 'MODEL' else 'KEY_SENTINEL'
                  for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI')
                  for suffix in ('MODEL', 'API_KEY')}
        env_file = self.root / 'fake.env'
        env_file.write_text('\n'.join(f'{k}={v}' for k, v in values.items()), encoding='utf-8')
        with patch.dict(os.environ, values), \
             patch('parallax_relay.play.HTTPAgent', NoResponseAgent), \
             contextlib.redirect_stdout(io.StringIO()):
            code = main(['--live', '--quiet', '--config', str(config), '--out', str(out),
                         '--env-file', str(env_file)])
        self.assertEqual(code, 4)
        result, manifest = self.artifacts(out)
        self.assertEqual(result['stop_reason'], 'spend_budget')
        self.assertEqual(result['budget']['calls_started'], 0)
        self.assertEqual(manifest['settings']['max_estimated_cost_usd'], 0.001)
        self.assertNotIn('requested_settings', manifest)
        self.assertNotIn('KEY_SENTINEL', (out / 'manifest.json').read_text())

    def test_programmatic_agents_including_scripted_keep_the_spending_guard(self):
        cfg = load_config(self.config())
        for agent_type in (ScriptedAgent, NoResponseAgent):
            with self.subTest(agent_type=agent_type.__name__):
                result = asyncio.run(run_match(
                    {r: agent_type(r) for r in ROLES}, cfg.match,
                    rates={r: cfg.players[r].pricing for r in ROLES}))
                self.assertEqual(result.stop_reason, 'spend_budget')
                self.assertEqual(result.budget['calls_started'], 0)
