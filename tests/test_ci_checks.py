"""The CI smoke checker must fail closed on CLI and artifact failures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class MockCheckTests(unittest.TestCase):
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
        self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
        self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
        self.assertNotIn('GEMINI_API_KEY', kwargs['env'])
        out = Path(command[command.index('--out') + 1])
        self.assertFalse(out.exists(), 'CLI requires a fresh destination')
        out.mkdir()
        self.outputs.append(out)
        calls = 42 if '--fast' in command else 63
        (out / 'result.json').write_text(json.dumps(self.result(calls)), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, 'scripted output', '')

    def run_check(self, effect):
        with patch.object(self.checker.subprocess, 'run', side_effect=effect), \
             contextlib.redirect_stdout(self.diagnostics), \
             contextlib.redirect_stderr(self.diagnostics):
            code = self.checker.main()
        self.assertTrue(all(not path.exists() for path in self.outputs))
        return code

    def test_both_modes_use_current_interpreter_fresh_paths_and_no_keys(self):
        credentials = {provider + '_API_KEY': 'never-forward-this'
                       for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI')}
        with patch.dict(os.environ, credentials):
            self.assertEqual(self.run_check(self.fake_run), 0)
        self.assertEqual(len(self.outputs), 2)
        self.assertNotEqual(self.outputs[0], self.outputs[1])
        self.assertIn('normal', self.diagnostics.getvalue())
        self.assertIn('fast', self.diagnostics.getvalue())

    def test_subprocess_failures_return_nonzero(self):
        failures = [subprocess.CompletedProcess([], 7, 'child stdout', 'child stderr'),
                    subprocess.TimeoutExpired('mock', 120), OSError('cannot launch')]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                def fail(command, **kwargs):
                    self.fake_run(command, **kwargs)
                    if isinstance(failure, Exception):
                        raise failure
                    return failure
                self.assertEqual(self.run_check(fail), 1)
        self.assertIn('normal', self.diagnostics.getvalue())
        self.assertIn('child stderr', self.diagnostics.getvalue())

    def test_missing_malformed_and_incorrect_results_return_nonzero(self):
        cases = [None, '{broken', '[]', json.dumps(self.result(42)),
                 json.dumps({**self.result(), 'completed': False}),
                 json.dumps({**self.result(), 'scores': {'SPECTRA': 100}})]
        for content in cases:
            with self.subTest(content=content):
                def bad_result(command, **kwargs):
                    proc = self.fake_run(command, **kwargs)
                    result = self.outputs[-1] / 'result.json'
                    if content is None:
                        result.unlink()
                    else:
                        result.write_text(content, encoding='utf-8')
                    return proc
                self.assertEqual(self.run_check(bad_result), 1)
