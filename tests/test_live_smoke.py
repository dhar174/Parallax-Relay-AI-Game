"""Offline acceptance tests: synthetic records never establish live support."""
import asyncio
import copy
import importlib.util
from contextlib import redirect_stdout, redirect_stderr
import io
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
from parallax_relay.protocol import ModelReply, ROLES
from parallax_relay.provenance import PlayerIdentity, ProvenanceContext
from parallax_relay.recording import Recorder
from parallax_relay.providers import ProviderError, _decode

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

    def synthetic_run(self, smoke, directory, agents=None):
        profile = smoke.load_profile()
        cfg = GameConfig.model_validate(profile['config'])
        identities = {r: PlayerIdentity(provider=cfg.players[r].provider, model=profile['models'][r])
                      for r in ROLES}
        recorder = Recorder(directory, {'room': 'The Split Span'}, context=ProvenanceContext(
            mode='live', players=identities, requested_settings=cfg.match))
        asyncio.run(run_match(agents or {r: ScriptedAgent(r) for r in ROLES}, cfg.match,
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
            receipt = json.loads((out / 'smoke_launch.json').read_text(encoding='utf-8'))
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
                    original = path.read_text(encoding='utf-8')
                    data = json.loads(original)
                    mutate(data)
                    path.write_text(json.dumps(data))
                    self.assertFalse(smoke.verify_run(out, profile)['accepted'])
                    path.write_text(original)
            path = out / 'phases.jsonl'
            original = path.read_text(encoding='utf-8')
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
            data = json.loads(path.read_text(encoding='utf-8'))
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

    def test_credential_file_cannot_configure_python_startup(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'keys.env'
            for setting in ('PYTHONWARNINGS=ignore::this.Warning', 'PYTHONUSERBASE=/untrusted'):
                path.write_text('OPENAI_API_KEY=FAKE\nGEMINI_API_KEY=FAKE\n' + setting + '\n', encoding='utf-8')
                with self.subTest(setting=setting), self.assertRaises(ValueError):
                    smoke.prepare_environment(profile, {}, path)
            path.write_text('OPENAI_API_KEY=FILE_FAKE\nGEMINI_API_KEY=FILE_FAKE\n', encoding='utf-8')
            child = smoke.prepare_environment(profile, {'OPENAI_API_KEY': 'PROCESS_FAKE',
                'HTTPS_PROXY': 'http://127.0.0.1:9', 'PYTHONWARNINGS': 'ignore::this.Warning'}, path)
            self.assertEqual(child['OPENAI_API_KEY'], 'PROCESS_FAKE')
            self.assertEqual(child['GEMINI_API_KEY'], 'FILE_FAKE')
            self.assertEqual(child['HTTPS_PROXY'], 'http://127.0.0.1:9')
            self.assertNotIn('PYTHONWARNINGS', child)

    def test_verifier_rejects_missing_replay_phase_and_world_structure(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            paths = ['replay.jsonl', 'phases.jsonl', 'final_state.json', 'result.json']
            originals = {name: (out / name).read_text(encoding='utf-8') for name in paths}
            for mutation in ('missing_replay', 'missing_phase', 'missing_world', 'missing_fallbacks',
                             'inconsistent_messages', 'inconsistent_actions', 'wrong_hud_role'):
                with self.subTest(mutation=mutation):
                    turn = json.loads(originals['replay.jsonl'])
                    phases = [json.loads(line) for line in originals['phases.jsonl'].splitlines()]
                    state = json.loads(originals['final_state.json'])
                    result = json.loads(originals['result.json'])
                    if mutation == 'missing_replay': turn = {'turn': 1, 'state_after': state}
                    if mutation == 'missing_phase':
                        for phase in phases:
                            phase.pop('messages', None); phase.pop('sealed_actions', None)
                    if mutation == 'missing_world':
                        state = {'turn': 1, 'win': False, 'loss': False}
                        turn['state_after'] = state
                        result.pop('energy')
                    if mutation == 'missing_fallbacks': turn.pop('fallbacks')
                    if mutation == 'inconsistent_messages': turn['communications'][0]['text'] = 'different'
                    if mutation == 'inconsistent_actions': turn['sealed_actions']['PYRA']['kind'] = 'WAIT'
                    if mutation == 'wrong_hud_role': turn['observations']['PYRA']['hud']['your_role'] = 'SPECTRA'
                    for name, text in {'replay.jsonl': json.dumps(turn),
                        'phases.jsonl': '\n'.join(map(json.dumps, phases)),
                        'final_state.json': json.dumps(state), 'result.json': json.dumps(result)}.items():
                        (out / name).write_text(text, encoding='utf-8')
                    self.assertFalse(smoke.verify_run(out, profile)['accepted'])
                    for name, text in originals.items(): (out / name).write_text(text, encoding='utf-8')

    def test_verifier_safely_rejects_huge_numeric_cost(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            path = out / 'result.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['budget']['estimated_cost_usd'] = 10 ** 1000
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertFalse(smoke.verify_run(out, profile)['accepted'])

    def test_verifier_rejects_broken_images_and_empty_viewer(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            for name in ('turn_00_pyra.png', 'turn_00_spectator.png', 'final_spectator.png', 'index.html'):
                with self.subTest(name=name):
                    path = out / name
                    original = path.read_bytes()
                    path.write_bytes(b'' if name.endswith('.html') else b'\x89PNG\r\n\x1a\n')
                    self.assertFalse(smoke.verify_run(out, profile)['accepted'])
                    path.write_bytes(original)

    def test_aborted_run_retains_attempt_counts_without_claiming_acceptance(self):
        smoke = self.smoke()
        class FatalAgent(ScriptedAgent):
            async def respond(self, request):
                raise ProviderError('http_error', False, 401)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            agents = {r: FatalAgent(r) if r == 'SPECTRA' else ScriptedAgent(r) for r in ROLES}
            profile = self.synthetic_run(smoke, out, agents)
            report = smoke.verify_run(out, profile)
            self.assertFalse(report['accepted'])
            self.assertEqual({r: p['attempts'] for r, p in report['providers'].items()},
                             {'SPECTRA': 1, 'PYRA': 1, 'FLUX': 1})
            self.assertFalse(any(p['accepted'] for p in report['providers'].values()))

    def test_unknown_attempt_status_is_not_copied_to_public_report(self):
        smoke = self.smoke()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out)
            path = out / 'calls.jsonl'
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            rows[0]['status'] = 'secret_sentinel'
            path.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
            report = smoke.verify_run(out, profile)
            self.assertNotIn('secret_sentinel', json.dumps(report))

    def test_malformed_profile_container_raises_safe_configuration_error(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        profile['sources']['PYRA'] = ['model_url', 'pricing_url', 'notes']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profile.json'
            path.write_text(json.dumps(profile), encoding='utf-8')
            with self.assertRaises(ValueError):
                smoke.load_profile(path)

    def test_timeout_reports_partial_path_and_atomic_receipt_without_relaunch(self):
        smoke = self.smoke()
        profile = smoke.load_profile()
        invocations = []
        def timeout(command, **kwargs):
            invocations.append(command)
            Path(command[command.index('--out') + 1]).mkdir()
            raise subprocess.TimeoutExpired(command, 600, output='SECRET_SENTINEL', stderr='SECRET_SENTINEL')
        with tempfile.TemporaryDirectory() as temp, patch.object(smoke.subprocess, 'run', timeout):
            out = Path(temp) / 'run'
            result = smoke.launch(profile, live=True, out=out,
                environ={'OPENAI_API_KEY': 'FAKE', 'GEMINI_API_KEY': 'FAKE'})
            self.assertEqual(len(invocations), 1)
            self.assertEqual(result['out'], str(out))
            self.assertTrue(result['timed_out'])
            self.assertIsNone(result['cli_returncode'])
            self.assertFalse(result['verification']['accepted'])
            receipt = json.loads((out / 'smoke_launch.json').read_text(encoding='utf-8'))
            self.assertTrue(receipt['timed_out'])
            self.assertIsNone(receipt['cli_returncode'])
            self.assertFalse((out / 'smoke_launch.json.tmp').exists())
            self.assertNotIn('SECRET_SENTINEL', json.dumps(result) + json.dumps(receipt))
            with patch.object(smoke, 'launch', return_value=result), redirect_stdout(io.StringIO()):
                self.assertEqual(smoke.main(['--live']), 2)

    def test_verify_rejects_ignored_execution_flags(self):
        smoke = self.smoke()
        with redirect_stderr(io.StringIO()):
            for option in ('--config', '--env-file'):
                with self.subTest(option=option):
                    with self.assertRaises(SystemExit) as error:
                        smoke.main(['--verify', 'run', option, 'unused'])
                    self.assertEqual(error.exception.code, 2)

    def test_valid_retry_and_unknown_usage_keep_evidence_and_estimates(self):
        smoke = self.smoke()
        class MetadataAgent(ScriptedAgent):
            def __init__(self, role):
                super().__init__(role)
                self.first = True

            async def respond(self, request):
                scripted = await super().respond(request)
                usage = _decode('openai', {'usage': {'input_tokens': 9, 'output_tokens': None,
                    'input_tokens_details': {'cached_tokens': 'SECRET_SENTINEL'}}}).usage
                if self.role == 'SPECTRA' and self.first:
                    self.first = False
                    return ModelReply('not JSON', usage)
                return ModelReply(scripted.text, usage)

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            profile = self.synthetic_run(smoke, out, {r: MetadataAgent(r) for r in ROLES})
            report = smoke.verify_run(out, profile)
            self.assertTrue(report['accepted'], report)
            self.assertEqual(report['providers']['SPECTRA']['attempts'], 4)
            self.assertEqual(report['budget']['unknown_usage_calls'], 10)
            self.assertGreater(report['budget']['estimated_cost_usd'], 0)
            self.assertEqual(report['providers']['PYRA']['source_usage'][0]['usage.input_tokens'],
                             {'state': 'count', 'value': 9})
            self.assertEqual(report['providers']['PYRA']['source_usage'][0]['usage.input_tokens_details.cached_tokens'],
                             {'state': 'invalid', 'value': None})
            self.assertNotIn('SECRET_SENTINEL', json.dumps(report))
