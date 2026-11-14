"""CI must reject whitespace defects that are already committed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check_committed_diff.py'


class CommittedDiffTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'Committed-diff checker is missing')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Offline test')
        self.git('config', 'user.email', 'offline@example.invalid')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, capture_output=True,
                              text=True, encoding='utf-8', errors='replace', check=True).stdout.strip()

    def commit(self, text):
        (self.repo / 'tracked.txt').write_text(text, encoding='utf-8')
        self.git('add', 'tracked.txt')
        self.git('commit', '-qm', 'Fixture commit')
        return self.git('rev-parse', 'HEAD')

    def check(self, event, payload):
        path = self.root / 'event.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo,
                              env={**os.environ, 'GITHUB_EVENT_NAME': event,
                                   'GITHUB_EVENT_PATH': str(path)},
                              capture_output=True, text=True, encoding='utf-8', errors='replace')

    def test_clean_checkout_rejects_committed_whitespace_for_each_event(self):
        base = self.commit('clean\n')
        self.commit('trailing space \n<<<<<<< conflict\n')
        self.assertEqual(self.git('diff', '--check'), '')  # Original CI passes.
        for event, payload in [('pull_request', {'pull_request': {'base': {'sha': base}}}),
                               ('push', {'before': base}), ('workflow_dispatch', {})]:
            with self.subTest(event=event):
                result = self.check(event, payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('tracked.txt', result.stdout + result.stderr)

    def test_initial_push_and_manual_root_commit_are_checked(self):
        self.commit('trailing space \n')
        for event, payload in [('push', {'before': '0' * 40}), ('workflow_dispatch', {})]:
            with self.subTest(event=event):
                self.assertNotEqual(self.check(event, payload).returncode, 0)

    def test_clean_commits_pass_and_invalid_base_fails_closed(self):
        base = self.commit('clean\n')
        self.commit('still clean\n')
        self.assertEqual(self.check('pull_request', {'pull_request': {'base': {'sha': base}}}).returncode, 0)
        self.assertEqual(self.check('push', {'before': base}).returncode, 0)
        invalid = self.check('pull_request', {'pull_request': {'base': {'sha': '--invalid'}}})
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn('Invalid comparison commit', invalid.stderr)
