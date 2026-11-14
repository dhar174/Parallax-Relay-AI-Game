"""The CI smoke checker must fail closed on CLI and artifact failures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class MockCheckTests(unittest.TestCase):
    def test_real_helper_handles_unicode_paths_with_ascii_parent_stdio(self):
        with tempfile.TemporaryDirectory(prefix='relay-鏡-') as tmp:
            env = {**os.environ, 'TMPDIR': tmp, 'TEMP': tmp, 'TMP': tmp,
                   'PYTHONIOENCODING': 'ascii'}
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_mock_runs.py')],
                                    cwd=tmp, env=env, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('normal: victory', result.stdout)
            self.assertIn('fast: victory', result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_json_boolean_and_integer_types_are_strict(self):
        for field, wrong in [('win', 1), ('turns', 7.0),
                             ('scores', dict.fromkeys(('SPECTRA', 'PYRA', 'FLUX'), 100.0))]:
            with self.subTest(field=field):
                def wrong_type(command, **kwargs):
                    proc = self.fake_run(command, **kwargs)
                    result = self.result(42 if '--fast' in command else 63)
                    result[field] = wrong
                    (self.outputs[-1] / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                    return proc
                self.assertEqual(self.run_check(wrong_type), 1)
                self.assertIn(field, self.diagnostics.getvalue())

    def setUp(self):
        script = ROOT / 'scripts' / 'check_mock_runs.py'
        self.assertTrue(script.is_file(), 'The reusable mock checker is missing')
        spec = importlib.util.spec_from_file_location('check_mock_runs', script)
        self.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.checker)
        self.outputs = []
        self.diagnostics = io.StringIO()

    def result(self, calls=63):
        return {'win': True, 'loss': False, 'completed': True,
                'stop_reason': 'victory', 'turns': 7, 'energy': 5,
                'scores': dict.fromkeys(('SPECTRA', 'PYRA', 'FLUX'), 100),
                'budget': {'calls_started': calls}}

    def fake_run(self, command, **kwargs):
        self.assertEqual(command[:4], [sys.executable, '-m', 'parallax_relay.play', '--mock'])
        self.assertEqual(kwargs['cwd'], ROOT)
        self.assertEqual(kwargs['timeout'], 120)
        self.assertEqual(kwargs['encoding'], 'utf-8')
        self.assertEqual(kwargs['errors'], 'replace')
        self.assertEqual(kwargs['env']['PYTHONIOENCODING'], 'utf-8')
        self.assertIn('--quiet', command)
        self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
        self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
        self.assertNotIn('GEMINI_API_KEY', kwargs['env'])
        out = Path(command[command.index('--out') + 1])
        self.assertEqual('--fast' in command, out.name == 'fast')
        self.assertFalse(out.exists(), 'CLI requires a fresh destination')
        out.mkdir()
        self.outputs.append(out)
        calls = 42 if '--fast' in command else 63
        (out / 'result.json').write_text(json.dumps(self.result(calls)), encoding='utf-8')
        for name in ('index.html', 'manifest.json', 'calls.jsonl'):
            (out / name).write_text('mock fixture', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, 'scripted output', '')

    def run_check(self, effect):
        self.diagnostics = io.StringIO()
        self.outputs = []
        with patch.object(self.checker.subprocess, 'run', side_effect=effect), \
             contextlib.redirect_stdout(self.diagnostics), \
             contextlib.redirect_stderr(self.diagnostics):
            code = self.checker.main()
        self.assertTrue(all(not path.exists() for path in self.outputs))
        return code

    def test_both_modes_use_current_interpreter_fresh_paths_and_no_keys(self):
        credentials = {provider + '_' + suffix: 'never-forward-this'
                       for provider in ('OPENAI', 'Anthropic', 'gemini')
                       for suffix in ('API_KEY', 'MODEL')}
        credentials.update({key: 'never-forward-this' for key in
                            ('https_proxy', 'ALL_PROXY', 'OPENAI_BASE_URL', 'PYTHONPATH',
                             'PYTHONSTARTUP', 'PYTHONHOME', 'PYTHONINSPECT')})
        def check_environment(command, **kwargs):
            self.assertFalse({key.upper() for key in kwargs['env']} &
                             {key.upper() for key in credentials})
            return self.fake_run(command, **kwargs)
        with patch.dict(os.environ, credentials):
            self.assertEqual(self.run_check(check_environment), 0)
        self.assertEqual(len(self.outputs), 2)
        self.assertNotEqual(self.outputs[0], self.outputs[1])
        self.assertIn('normal', self.diagnostics.getvalue())
        self.assertIn('fast', self.diagnostics.getvalue())

    def test_subprocess_failures_return_nonzero(self):
        failures = [(subprocess.CompletedProcess([], 7, 'child stdout', 'child stderr'), 'exit 7', 'child stderr'),
                    (subprocess.TimeoutExpired('mock', 120, output=b'partial\xff', stderr=b'timeout stderr'),
                     'timed out', 'timeout stderr'), (OSError('cannot launch'), 'cannot launch', '')]
        for mode in ('normal', 'fast'):
            for failure, message, stderr in failures:
                with self.subTest(mode=mode, failure=type(failure).__name__):
                    def fail(command, **kwargs):
                        proc = self.fake_run(command, **kwargs)
                        if self.outputs[-1].name != mode:
                            return proc
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    self.assertEqual(self.run_check(fail), 1)
                    self.assertIn(mode + ' mock check failed', self.diagnostics.getvalue())
                    self.assertIn(message, self.diagnostics.getvalue())
                    if stderr:
                        self.assertIn(stderr, self.diagnostics.getvalue())
                    if isinstance(failure, subprocess.TimeoutExpired):
                        self.assertIn('partial\ufffd', self.diagnostics.getvalue())

    def test_missing_malformed_and_incorrect_results_return_nonzero(self):
        cases = [('file', None), ('file', b'{broken'), ('file', b'\xff'), ('root', []),
                 ('budget', []), ('win', False), ('loss', True), ('stop_reason', 'turn_limit'),
                 ('turns', 8), ('energy', 0), ('completed', False), ('calls', 0), ('calls', 63.0),
                 ('scores', {'SPECTRA': 100}), ('scores', dict.fromkeys(('SPECTRA', 'PYRA', 'FLUX'), 99)),
                 ('scores', {**self.result()['scores'], 'ECHO': 100})]
        for mode in ('normal', 'fast'):
            for field, value in cases:
                with self.subTest(mode=mode, field=field, value=value):
                    def bad_result(command, **kwargs):
                        proc = self.fake_run(command, **kwargs)
                        if self.outputs[-1].name != mode:
                            return proc
                        path = self.outputs[-1] / 'result.json'
                        data = self.result(42 if mode == 'fast' else 63)
                        if field == 'file':
                            if value is None:
                                path.unlink()
                            else:
                                path.write_bytes(value)
                        else:
                            if field == 'root': data = value
                            elif field == 'calls': data['budget']['calls_started'] = value
                            else: data[field] = value
                            path.write_text(json.dumps(data), encoding='utf-8')
                        return subprocess.CompletedProcess(command, 0, proc.stdout, 'validation stderr')
                    self.assertEqual(self.run_check(bad_result), 1)
                    self.assertIn(mode + ' mock check failed', self.diagnostics.getvalue())
                    self.assertIn('validation stderr', self.diagnostics.getvalue())

    def test_missing_artifacts_and_quiet_progress_fail(self):
        for name in ('index.html', 'manifest.json', 'calls.jsonl', 'progress'):
            with self.subTest(name=name):
                def fail(command, **kwargs):
                    proc = self.fake_run(command, **kwargs)
                    if self.outputs[-1].name == 'fast':
                        if name == 'progress':
                            return subprocess.CompletedProcess(command, 0, 'Round 01 | broadcast', '')
                        (self.outputs[-1] / name).unlink()
                    return proc
                self.assertEqual(self.run_check(fail), 1)
                self.assertIn('fast mock check failed', self.diagnostics.getvalue())

    def test_cleanup_failure_has_its_own_stage(self):
        real_temporary = tempfile.TemporaryDirectory
        class CleanupFailure:
            def __init__(self, **kwargs): self.inner = real_temporary(**kwargs)
            def __enter__(self): return self.inner.__enter__()
            def __exit__(self, *args):
                self.inner.__exit__(*args)
                raise OSError('cleanup trouble')
        with patch.object(self.checker.tempfile, 'TemporaryDirectory', CleanupFailure):
            self.assertEqual(self.run_check(self.fake_run), 1)
        self.assertIn('cleanup mock check failed: cleanup trouble', self.diagnostics.getvalue())
