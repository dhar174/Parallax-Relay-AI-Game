"""Review regressions at the real recorder and CLI boundaries; no provider calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import ConfigError, MatchSettings
from parallax_relay.orchestrator import MatchExecutionError, run_match
from parallax_relay.play import load_env_file, main
from parallax_relay.protocol import ROLES
from parallax_relay.provenance import PlayerIdentity, ProvenanceContext, read_provenance
from parallax_relay.recording import Recorder


class EnvironmentReviewTests(unittest.TestCase):
    def test_env_file_rejects_transport_overrides_without_partial_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.env'
            for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                        'SSL_CERT_FILE', 'SSL_CERT_DIR'):
                for existing in (False, True):
                    with self.subTest(key=key, existing=existing):
                        path.write_text(f'CUSTOM_KEY=SECRET_SENTINEL\n{key}=SECRET_TRANSPORT\n', encoding='utf-8')
                        env = {key: 'process-setting'} if existing else {}
                        before = env.copy()
                        with self.assertRaises(ConfigError) as error:
                            load_env_file(path, env)
                        self.assertEqual(env, before)
                        self.assertNotIn('SECRET_', str(error.exception))

    def test_process_transport_settings_and_custom_keys_remain_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.env'
            path.write_text('CUSTOM_KEY=new\nCUSTOM_MODEL=test-model\n', encoding='utf-8')
            env = {'HTTPS_PROXY': 'process-proxy', 'SSL_CERT_FILE': 'process-certificate',
                   'CUSTOM_KEY': 'existing'}
            load_env_file(path, env)
            self.assertEqual(env, {'HTTPS_PROXY': 'process-proxy', 'SSL_CERT_FILE': 'process-certificate',
                                   'CUSTOM_KEY': 'existing', 'CUSTOM_MODEL': 'test-model'})

    def test_rejected_env_is_safe_cli_error_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, out = Path(tmp) / 'settings.env', Path(tmp) / 'not-created'
            path.write_text('HTTPS_PROXY=SECRET_SENTINEL\n', encoding='utf-8')
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(['--live', '--env-file', str(path), '--out', str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())
            self.assertNotIn('SECRET_SENTINEL', stdout.getvalue() + stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())

    def test_intercepted_live_launcher_retains_requested_dollar_cap(self):
        class SyntheticHTTP(ScriptedAgent):
            def __init__(self, provider, model, key, **kwargs):
                super().__init__(dict(zip(('openai', 'anthropic', 'gemini'), ROLES))[provider])
        with tempfile.TemporaryDirectory() as tmp:
            config, env_file, out = (Path(tmp) / name for name in ('priced.toml', 'keys.env', 'run'))
            text = Path('configs/three_models.toml').read_text(encoding='utf-8')
            text = text.replace('[match]\n', '[match]\nmax_estimated_cost_usd=1.0\n')
            for role in ROLES:
                text += f'\n[players.{role}.pricing]\ninput_per_million=1\noutput_per_million=2\n'
            config.write_text(text, encoding='utf-8')
            env_file.write_text('\n'.join(
                f'{provider}_{suffix}={"test-model" if suffix == "MODEL" else "SECRET_SENTINEL"}'
                for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI') for suffix in ('MODEL', 'API_KEY')), encoding='utf-8')
            with patch('parallax_relay.play.HTTPAgent', SyntheticHTTP), patch.dict(os.environ, {}, clear=True), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(['--live', '--quiet', '--max-turns', '1', '--config', str(config),
                             '--env-file', str(env_file), '--out', str(out)])
            self.assertEqual(code, 0)
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            data = read_provenance(manifest)
            self.assertEqual(manifest['settings']['max_estimated_cost_usd'], 1.0)
            self.assertEqual(data['requested_settings']['max_estimated_cost_usd'], 1.0)
            self.assertEqual(data['execution']['value']['settings']['max_estimated_cost_usd'], 1.0)


class RecordingReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def agents(self):
        return {role: ScriptedAgent(role) for role in ROLES}

    def saved(self, recorder):
        return json.loads((recorder.out / 'manifest.json').read_text(encoding='utf-8'))

    def embedded(self, recorder):
        html = (recorder.out / 'index.html').read_text(encoding='utf-8')
        return json.loads(html.split('const DATA=', 1)[1].split(';\nconst $=', 1)[0])

    async def test_failed_binding_never_becomes_external_or_partially_bound(self):
        for failure_point in ('begin_hook', 'input_identities'):
            with self.subTest(failure_point=failure_point):
                recorder = Recorder(self.root / failure_point, {})
                original = ValueError('SECRET_SENTINEL')
                failure = (patch.object(recorder, 'begin_match', side_effect=original)
                           if failure_point == 'begin_hook' else
                           patch('parallax_relay.provenance.input_identities', side_effect=original))
                with failure, self.assertRaises(MatchExecutionError) as error:
                    await run_match(self.agents(), recorder=recorder)
                self.assertIs(error.exception.original_error, original)
                self.assertEqual(error.exception.operation, 'begin_match')
                self.assertEqual(error.exception.result.stop_reason, 'local_error')
                self.assertEqual(error.exception.result.budget['calls_started'], 0)
                data = read_provenance(self.saved(recorder))
                self.assertEqual(data['lifecycle']['stage'], 'initialized')
                self.assertIsNone(data['execution'])
                self.assertIsNone(data['inputs'])
                for field in ('started_at', 'ended_at', 'elapsed_seconds', 'execution_stop_reason', 'stop_reason'):
                    self.assertIsNone(data['lifecycle'][field])
                self.assertEqual(self.embedded(recorder)['result']['stop_reason'], 'local_error')
                saved = {path.name: path.read_bytes() for path in recorder.out.iterdir()}
                with self.assertRaises(ValueError):
                    await run_match(self.agents(), recorder=recorder)
                self.assertEqual({path.name: path.read_bytes() for path in recorder.out.iterdir()}, saved)

    async def test_end_hook_primary_failure_keeps_unknown_end_and_valid_metadata(self):
        recorder = Recorder(self.root / 'end-hook', {})
        original = OSError('SECRET_SENTINEL')
        with patch.object(recorder, 'end_match', side_effect=original), self.assertRaises(MatchExecutionError) as error:
            await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        self.assertIs(error.exception.original_error, original)
        self.assertEqual(error.exception.operation, 'end_match')
        self.assertEqual(error.exception.original_stop_reason, 'turn_limit')
        self.assertEqual(error.exception.result.stop_reason, 'local_error')
        life = read_provenance(self.saved(recorder))['lifecycle']
        self.assertEqual(life['stage'], 'running')
        self.assertEqual(life['stop_reason'], 'local_error')
        self.assertIsNone(life['execution_stop_reason'])
        self.assertIsNone(life['ended_at'])

    async def test_external_finish_claims_recorder_without_inventing_execution(self):
        result = await run_match(self.agents(), MatchSettings(max_turns=1))
        recorder = Recorder(self.root / 'external', {})
        recorder.finish(result)
        self.assertEqual(read_provenance(self.saved(recorder))['lifecycle']['stage'], 'external_result')
        saved = {path.name: path.read_bytes() for path in recorder.out.iterdir()}
        with self.assertRaises(ValueError):
            await run_match(self.agents(), recorder=recorder)
        self.assertEqual({path.name: path.read_bytes() for path in recorder.out.iterdir()}, saved)

    async def test_second_pass_manifest_failure_preserves_primary_and_first_snapshot(self):
        recorder = Recorder(self.root / 'second-pass', {})
        real_write, manifest_attempts = recorder._bytes, []
        original, secondary = OSError('SECRET_PRIMARY'), OSError('SECRET_SECONDARY')
        def write(name, data):
            if name == 'manifest.json' and json.loads(data)['provenance']['lifecycle']['stage'] == 'ended':
                manifest_attempts.append(json.loads(data))
                if len(manifest_attempts) == 2:
                    raise secondary
            if name == 'result.json' and len(manifest_attempts) == 1:
                raise original
            real_write(name, data)
        with patch.object(recorder, '_bytes', side_effect=write), self.assertRaises(MatchExecutionError) as error:
            await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        self.assertIs(error.exception.original_error, original)
        self.assertEqual(error.exception.operation, 'finish:result.json')
        self.assertIn(('finish:manifest.json', secondary), error.exception.secondary_errors)
        self.assertEqual(len(manifest_attempts), 2)
        disk, embedded = self.saved(recorder), self.embedded(recorder)
        self.assertEqual(read_provenance(disk)['lifecycle']['stop_reason'], 'turn_limit')
        self.assertEqual(read_provenance(embedded['manifest'])['lifecycle']['stop_reason'], 'local_error')
        self.assertEqual(disk['provenance']['lifecycle']['ended_at'],
                         embedded['manifest']['provenance']['lifecycle']['ended_at'])
        self.assertEqual(embedded['result']['stop_reason'], 'local_error')
        self.assertTrue(recorder.viewer_ready)

    async def test_context_populates_display_fields_and_overrides_stale_labels(self):
        for mode in ('mock', 'live', 'programmatic'):
            with self.subTest(mode=mode):
                context = ProvenanceContext(mode=mode, players={
                    r: PlayerIdentity(provider='mock', model='scripted-fixture') for r in ROLES})
                recorder = Recorder(self.root / mode, {'mode': 'stale', 'players': {}}, context=context)
                await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
                manifest = self.saved(recorder)
                self.assertEqual(manifest['mode'], mode)
                self.assertEqual(manifest['players'], {
                    r: {'provider': 'mock', 'model': 'scripted-fixture'} for r in ROLES})
                self.assertEqual(self.embedded(recorder)['manifest'], manifest)

    async def test_missing_display_labels_use_programmatic_unknown_identities(self):
        recorder = Recorder(self.root / 'unknown', {})
        await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        manifest = self.saved(recorder)
        self.assertEqual(manifest['mode'], 'programmatic')
        self.assertEqual(manifest['players'], {r: {'provider': 'unknown', 'model': None} for r in ROLES})

    async def test_legacy_display_labels_do_not_claim_provenance_identity(self):
        players = {r: {'provider': 'mock', 'model': 'legacy-label'} for r in ROLES}
        recorder = Recorder(self.root / 'legacy', {'mode': 'mock', 'players': players})
        await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        manifest = self.saved(recorder)
        self.assertEqual(manifest['mode'], 'mock')
        self.assertEqual(manifest['players'], players)
        self.assertTrue(all(player['provider'] == 'unknown' for player in read_provenance(manifest)['players'].values()))

    def test_tuple_metadata_redacts_nested_credentials_before_json_serialization(self):
        recorder = Recorder(self.root / 'redacted', {'nested': ({'API_KEY': 'SECRET_SENTINEL'},)})
        manifest = self.saved(recorder)
        self.assertEqual(manifest['nested'], [{'API_KEY': '[REDACTED]'}])
        self.assertNotIn('SECRET_SENTINEL', json.dumps(manifest))
