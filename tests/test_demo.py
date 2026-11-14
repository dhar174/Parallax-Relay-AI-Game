import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from parallax_relay.demo import main, run


ROOT = Path(__file__).resolve().parent.parent


class DemoTests(unittest.TestCase):
    def command(self, cwd, *args):
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONPATH'] = str(ROOT)
        return subprocess.run(
            [sys.executable, '-m', 'parallax_relay.demo', *map(str, args)],
            cwd=cwd, env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30)

    def test_cli_rejects_dangling_and_file_symlinks_without_following(self):
        for kind in ('dangling', 'file'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'target'
                if kind == 'file': target.write_bytes(b'SENTINEL')
                link = Path(tmp) / 'out'
                try:
                    link.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest('Symlink creation is unavailable')
                proc = self.command(tmp, '--out', link)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn('Output path already exists', proc.stderr)
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.readlink(), target)
                if kind == 'file': self.assertEqual(target.read_bytes(), b'SENTINEL')
                else: self.assertFalse(target.exists())

    def test_file_exists_during_rendering_is_a_local_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            with patch('parallax_relay.demo.render_png', side_effect=FileExistsError('SECRET_SENTINEL')), \
                 contextlib.redirect_stderr(stderr):
                code = main(['--out', str(Path(tmp) / 'new')])
            self.assertEqual(code, 2)
            self.assertIn('Local file operation failed', stderr.getvalue())
            self.assertNotIn('SECRET_SENTINEL', stderr.getvalue())

    def assert_replay(self, out):
        result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
        self.assertEqual(result, {'win': True, 'turns': 7,
                                 'scores': {'SPECTRA': 100, 'PYRA': 100, 'FLUX': 100},
                                 'energy': 5})
        records = [json.loads(line) for line in (out / 'replay.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 7)
        images = []
        for record in records:
            images.extend(out / obs['image'] for obs in record['observations'].values())
            images.append(out / f"turn_{record['turn']-1:02d}_spectator.png")
        self.assertEqual(len(images), 28)
        for path in images:
            with Image.open(path) as image:
                image.verify()
        self.assertTrue((out / 'index.html').is_file())

    def test_run_rejects_existing_empty_directory_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'existing'; out.mkdir()
            with self.assertRaises(FileExistsError):
                with contextlib.redirect_stdout(io.StringIO()):
                    run(out)
            self.assertEqual(list(out.iterdir()), [])

    def test_run_rejects_existing_files_and_preserves_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('file', 'directory'):
                with self.subTest(kind=kind):
                    out = Path(tmp) / kind
                    if kind == 'directory':
                        out.mkdir(); sentinel = out / 'result.json'
                    else:
                        sentinel = out
                    sentinel.write_bytes(b'SENTINEL')
                    with self.assertRaises(FileExistsError):
                        with contextlib.redirect_stdout(io.StringIO()):
                            run(out)
                    self.assertEqual(sentinel.read_bytes(), b'SENTINEL')
                    if kind == 'directory':
                        self.assertEqual(list(out.iterdir()), [sentinel])

    def test_run_rejects_symlink_to_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'; target.mkdir()
            sentinel = target / 'result.json'; sentinel.write_bytes(b'SENTINEL')
            link = Path(tmp) / 'link'
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('Symlink creation is unavailable')
            with self.assertRaises(FileExistsError):
                with contextlib.redirect_stdout(io.StringIO()):
                    run(link)
            self.assertTrue(link.is_symlink())
            self.assertEqual(sentinel.read_bytes(), b'SENTINEL')
            self.assertEqual(list(target.iterdir()), [sentinel])

    def test_cli_existing_destinations_exit_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('empty', 'populated', 'file'):
                with self.subTest(kind=kind):
                    out = Path(tmp) / kind
                    if kind == 'file':
                        out.write_bytes(b'SENTINEL')
                    else:
                        out.mkdir()
                        if kind == 'populated':
                            (out / 'result.json').write_bytes(b'SENTINEL')
                    proc = self.command(tmp, '--out', out)
                    self.assertEqual(proc.returncode, 2, proc.stderr)
                    self.assertIn('Output path already exists', proc.stderr)
                    self.assertNotIn('Traceback', proc.stderr)
                    if kind == 'file':
                        self.assertEqual(out.read_bytes(), b'SENTINEL')
                    elif kind == 'empty':
                        self.assertEqual(list(out.iterdir()), [])
                    else:
                        self.assertEqual((out / 'result.json').read_bytes(), b'SENTINEL')
                        self.assertEqual(len(list(out.iterdir())), 1)

    def test_run_new_destination_preserves_scripted_result_and_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'nested' / 'new-run'
            with contextlib.redirect_stdout(io.StringIO()):
                result = run(out)
            self.assertTrue(result['win'])
            self.assert_replay(out)

    def test_cli_new_destination_prints_replay_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'new-run'
            proc = self.command(tmp, '--out', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f'Replay: {out / "index.html"}', proc.stdout)
            self.assert_replay(out)

    def test_no_argument_cli_creates_distinct_runs_and_leaves_old_demo_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'demo_output'; original.mkdir()
            (original / 'result.json').write_bytes(b'SENTINEL')
            paths = []
            for _ in range(2):
                proc = self.command(tmp)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                match = re.search(r'^Replay: (.+)$', proc.stdout, re.MULTILINE)
                self.assertIsNotNone(match, proc.stdout)
                replay = Path(match.group(1))
                self.assertEqual(replay.parent.parent, Path('runs'))
                self.assertRegex(replay.parent.name, r'^demo_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{6}$')
                self.assert_replay(Path(tmp) / replay.parent)
                paths.append(replay)
            self.assertNotEqual(paths[0], paths[1])
            self.assertEqual((original / 'result.json').read_bytes(), b'SENTINEL')
            self.assertEqual(len(list(original.iterdir())), 1)

    def test_cli_io_errors_are_sanitized(self):
        stderr = io.StringIO()
        # Inject a filesystem failure: actual permission bits depend on the test user/OS.
        with patch('parallax_relay.demo.Path.mkdir', side_effect=PermissionError('SECRET_SENTINEL')):
            with contextlib.redirect_stderr(stderr):
                code = main(['--out', 'unused'])
        self.assertEqual(code, 2)
        self.assertIn('Local file operation failed', stderr.getvalue())
        self.assertNotIn('SECRET_SENTINEL', stderr.getvalue())
        self.assertNotIn('Traceback', stderr.getvalue())

    def test_cli_filesystem_error_exits_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / 'file-not-directory'
            parent.write_bytes(b'SECRET_SENTINEL')
            proc = self.command(tmp, '--out', parent / 'run')
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn('Local file operation failed', proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)
            self.assertNotIn('SECRET_SENTINEL', proc.stdout + proc.stderr)
            self.assertEqual(parent.read_bytes(), b'SECRET_SENTINEL')

    def test_parent_file_windows_error_is_reported_as_local_failure(self):
        # Windows can report EEXIST for a nonexistent destination below a file.
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / 'file-not-directory'
            parent.write_bytes(b'SECRET_SENTINEL')
            out = parent / 'run'
            stderr = io.StringIO()
            with patch('parallax_relay.demo.Path.mkdir', side_effect=FileExistsError('SECRET_SENTINEL')), \
                 contextlib.redirect_stderr(stderr):
                code = main(['--out', str(out)])
            self.assertEqual(code, 2)
            self.assertIn('Local file operation failed', stderr.getvalue())
            self.assertNotIn('SECRET_SENTINEL', stderr.getvalue())
            self.assertEqual(parent.read_bytes(), b'SECRET_SENTINEL')
