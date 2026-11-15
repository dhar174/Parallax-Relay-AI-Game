"""Real CLI metadata and intercepted live launches without remote requests."""
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
from uuid import uuid4

from parallax_relay.agents import ScriptedAgent
from parallax_relay.play import main
from parallax_relay.protocol import ROLES


class ProvenanceCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def command(self, *args):
        return subprocess.run([sys.executable, '-m', 'parallax_relay.play', *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=30)

    def test_priced_mock_custom_destination_uuid_and_effective_context(self):
        text = Path('configs/three_models.toml').read_text(encoding='utf-8')
        text = text.replace('[match]\n', '[match]\nmax_estimated_cost_usd=0.001\n')
        for role in ROLES:
            text += f'\n[players.{role}.pricing]\ninput_per_million=1\noutput_per_million=2\n'
        config = self.root / 'priced.toml'; config.write_text(text, encoding='utf-8')
        for fast, calls in [(False, 63), (True, 42)]:
            out = self.root / ('custom-fast' if fast else 'custom-normal')
            experiment, trial = str(uuid4()), str(uuid4())
            args = ['--mock', '--quiet', '--config', config, '--out', out,
                    '--experiment-id', experiment, '--trial-id', trial]
            if fast: args.append('--fast')
            proc = self.command(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            data = manifest['provenance']
            self.assertEqual(data['experiment_id'], experiment)
            self.assertEqual(data['trial_id'], trial)
            self.assertEqual(data['execution']['value']['mode'], 'mock')
            self.assertIsNone(data['execution']['value']['settings']['max_estimated_cost_usd'])
            self.assertEqual(data['requested_settings']['max_estimated_cost_usd'], 0.001)
            self.assertTrue(all(p['provider'] == 'mock' for p in data['players'].values()))
            self.assertEqual(data['lifecycle']['stop_reason'], 'victory')
            result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual((result['turns'], result['energy'], result['budget']['calls_started']), (7, 5, calls))

    def test_invalid_identifiers_do_not_echo_input_or_create_output(self):
        for flag in ('--experiment-id', '--trial-id'):
            out = self.root / flag[2:]
            proc = self.command('--mock', '--out', out, flag, 'SECRET_SENTINEL')
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn('SECRET_SENTINEL', proc.stdout + proc.stderr)
            self.assertFalse(out.exists())

    def test_keys_comments_and_environment_variable_names_are_not_fingerprinted(self):
        original = Path('configs/three_models.toml').read_text(encoding='utf-8')
        class SyntheticHTTP(ScriptedAgent):
            def __init__(self, provider, model, key, **kwargs):
                super().__init__(dict(zip(('openai', 'anthropic', 'gemini'), ROLES))[provider])
        hashes = []
        for number in (1, 2):
            config = self.root / f'config-{number}.toml'
            text = original + f'\n# SECRET_COMMENT_{number}\n'
            env = []
            for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI'):
                text = text.replace(provider + '_API_KEY', provider + f'_KEY_{number}')
                env += [f'{provider}_KEY_{number}=SECRET_KEY_{number}', f'{provider}_MODEL=test-model']
            config.write_text(text, encoding='utf-8')
            env_file = self.root / f'SECRET_PATH_{number}.env'
            env_file.write_text('\n'.join(env), encoding='utf-8')
            out = self.root / f'output-{number}'
            with patch('parallax_relay.play.HTTPAgent', SyntheticHTTP), \
                 patch.dict(os.environ, {}, clear=True), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(['--live', '--quiet', '--max-turns', '1', '--config', str(config),
                             '--env-file', str(env_file), '--out', str(out)])
            self.assertEqual(code, 0)
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertIn('provenance', manifest)
            data = manifest['provenance']
            hashes.append(data['execution']['sha256'])
            self.assertEqual(data['players']['PYRA']['api_contract']['version_header'], '2026-10-21')
            for path in out.iterdir():
                if path.suffix in ('.json', '.jsonl', '.html'):
                    text = path.read_text(encoding='utf-8')
                    for sentinel in ('SECRET_KEY_', 'SECRET_COMMENT_', 'SECRET_PATH_', '_KEY_1', '_KEY_2'):
                        self.assertNotIn(sentinel, text)
        self.assertEqual(hashes[0], hashes[1])
