"""Offline acceptance tests: synthetic records never establish live support."""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import GameConfig, load_config
from parallax_relay.orchestrator import run_match
from parallax_relay.protocol import ROLES
from parallax_relay.provenance import PlayerIdentity, ProvenanceContext
from parallax_relay.recording import Recorder

ROOT = Path(__file__).resolve().parent.parent


class LiveSmokeTests(unittest.TestCase):
    def smoke(self):
        path = ROOT / 'scripts/live_smoke.py'
        self.assertTrue(path.is_file(), 'The bounded smoke launcher is missing')
        spec = importlib.util.spec_from_file_location('live_smoke_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_profile_export_and_environment_pin_models_without_mutation(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        before = copy.deepcopy(profile)
        env = {'OPENAI_API_KEY': 'OPENAI_SENTINEL', 'GEMINI_API_KEY': 'GEMINI_SENTINEL',
               'OPENAI_MODEL': 'wrong', 'PYRA_MODEL': 'wrong', 'GEMINI_MODEL': 'wrong'}
        child = smoke.prepare_environment(profile, env)
        self.assertEqual(child['OPENAI_MODEL'], 'gpt-6-luna')
        self.assertEqual(child['PYRA_MODEL'], 'gpt-6-luna')
        self.assertEqual(child['GEMINI_MODEL'], 'gemini-3.5-flash-lite')
        self.assertEqual(child['OPENAI_API_KEY'], 'OPENAI_SENTINEL')
        self.assertEqual(env['OPENAI_MODEL'], 'wrong')
        self.assertEqual(profile, before)
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'export.toml'
            file.write_text(smoke.configuration_toml(GameConfig.model_validate(profile['config'])))
            config = load_config(file)
        self.assertEqual(config.match.max_turns, 1)
        self.assertEqual(config.match.max_calls, 18)
        self.assertEqual(config.match.max_output_tokens, 4096)
        self.assertEqual(config.match.max_estimated_cost_usd, 1)
        self.assertEqual(config.players['PYRA'].provider, 'openai')
        self.assertEqual(config.model_dump(), profile['config'])

    def test_real_check_never_constructs_provider_clients_or_creates_run(self):
        smoke = self.smoke()
        from parallax_relay import play
        profile = smoke.load_profile()
        env = {'OPENAI_API_KEY': 'FAKE_OPENAI', 'GEMINI_API_KEY': 'FAKE_GEMINI'}
        invocations = []
        def run_cli(command, **kwargs):
            invocations.append(command)
            with patch.dict(os.environ, kwargs['env'], clear=True), \
                 patch.object(play, 'HTTPAgent', side_effect=AssertionError('Provider access forbidden')):
                status = play.main(command[3:])
            return subprocess.CompletedProcess(command, status, '', '')
        with tempfile.TemporaryDirectory() as temp, patch.object(smoke.subprocess, 'run', run_cli):
            result = smoke.launch(profile, live=False, environ=env)
            self.assertEqual(result['cli_returncode'], 0)
            self.assertIsNone(result['out'])
            self.assertEqual(len(invocations), 1)
            self.assertIn('--check', invocations[0])

    def test_missing_credentials_and_altered_exports_fail_before_launch(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        with self.assertRaises(ValueError):
            smoke.prepare_environment(profile, {})
        with tempfile.TemporaryDirectory() as temp:
            config = GameConfig.model_validate(profile['config'])
            changed = config.model_copy(update={'match': config.match.model_copy(update={'max_calls': 19})})
            path = Path(temp) / 'changed.toml'
            path.write_text(smoke.configuration_toml(changed))
            with patch.object(smoke.subprocess, 'run', side_effect=AssertionError('Unexpected CLI launch')):
                with self.assertRaises(ValueError):
                    smoke.launch(profile, live=True, config_path=path,
                                 environ={'OPENAI_API_KEY': 'FAKE', 'GEMINI_API_KEY': 'FAKE'})

    def synthetic_run(self, smoke, directory):
        profile = smoke.load_profile()
        cfg = GameConfig.model_validate(profile['config'])
        identities = {r: PlayerIdentity(provider=cfg.players[r].provider, model=profile['models'][r])
                      for r in ROLES}
        recorder = Recorder(directory, {'room': 'The Split Span'}, context=ProvenanceContext(
            mode='live', players=identities, requested_settings=cfg.match))
        asyncio.run(run_match({r: ScriptedAgent(r) for r in ROLES}, cfg.match,
            rates={r: cfg.players[r].pricing for r in ROLES}, recorder=recorder))
        receipt = {'schema_version': 1, 'profile_sha256': smoke.profile_digest(profile),
                   'cli_returncode': 0}
        (directory / 'smoke_launch.json').write_text(json.dumps(receipt))
        return profile

    def test_verifier_accepts_coherent_synthetic_run_and_rejects_cli_failure(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            report = smoke.verify_run(out, profile)
            self.assertTrue(report['accepted'], report)
            self.assertTrue(all(p['accepted'] for p in report['providers'].values()))
            receipt = json.loads((out / 'smoke_launch.json').read_text())
            receipt['cli_returncode'] = 3
            (out / 'smoke_launch.json').write_text(json.dumps(receipt))
            self.assertFalse(smoke.verify_run(out, profile)['accepted'])

    def test_verifier_rejects_incomplete_mismatched_or_malformed_evidence(self):
        smoke = self.smoke()
        mutations = (
            ('result.json', lambda x: x.update(completed=True)),
            ('result.json', lambda x: x.update(turns=True)),
            ('result.json', lambda x: x['budget'].update(calls_started=0)),
            ('result.json', lambda x: x['budget'].update(reported_output_tokens=999)),
            ('result.json', lambda x: x['budget'].update(unknown_usage_calls=9)),
            ('result.json', lambda x: x['budget'].update(estimated_cost_usd=-1)),
            ('manifest.json', lambda x: x['settings'].update(max_calls=19)),
            ('manifest.json', lambda x: x['players']['PYRA'].update(model='other-model')),
            ('smoke_launch.json', lambda x: x.update(profile_sha256='bad')),
        )
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            for name, mutate in mutations:
                with self.subTest(name=name):
                    path = out / name
                    original = path.read_text()
                    data = json.loads(original)
                    mutate(data)
                    path.write_text(json.dumps(data))
                    self.assertFalse(smoke.verify_run(out, profile)['accepted'])
                    path.write_text(original)
            path = out / 'phases.jsonl'
            original = path.read_text()
            data = [json.loads(line) for line in original.splitlines()]
            data[0]['statuses']['PYRA'] = 'refusal'
            path.write_text('\n'.join(map(json.dumps, data)))
            self.assertFalse(smoke.verify_run(out, profile)['providers']['PYRA']['accepted'])
            path.write_text(original)
            (out / 'calls.jsonl').write_text('[malformed SECRET_SENTINEL')
            report = smoke.verify_run(out, profile)
            self.assertFalse(report['accepted'])
            self.assertNotIn('SECRET_SENTINEL', json.dumps(report))

    def test_report_projects_allowlisted_source_and_usage_only(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            path = out / 'manifest.json'
            data = json.loads(path.read_text())
            data['provenance']['source']['additional_note'] = 'SECRET_SENTINEL'
            path.write_text(json.dumps(data))
            report = smoke.verify_run(out, profile)
            self.assertTrue(report['accepted'], report)
            self.assertNotIn('SECRET_SENTINEL', json.dumps(report))

    def test_live_failure_is_not_retried_or_hidden(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        calls = []
        def failed_cli(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 3, 'SECRET_SENTINEL', 'SECRET_SENTINEL')
        with tempfile.TemporaryDirectory() as temp, patch.object(smoke.subprocess, 'run', failed_cli):
            result = smoke.launch(profile, live=True, out=Path(temp) / 'run',
                environ={'OPENAI_API_KEY': 'FAKE', 'GEMINI_API_KEY': 'FAKE'})
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['cli_returncode'], 3)
            self.assertFalse(result['verification']['accepted'])
            self.assertNotIn('SECRET_SENTINEL', json.dumps(result))
