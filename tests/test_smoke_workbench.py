"""The named browser preset and CLI must use the same public run sheet."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'site'))
from build_workbench import build
from runtime_contract import runtime_fingerprint


class SmokeWorkbenchTests(unittest.TestCase):
    def test_build_exposes_public_profile_without_changing_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            output = build(Path(temp) / 'dist')
            contract = json.loads((output / 'contract.json').read_text(encoding='utf-8'))
            self.assertIn('live_smoke', contract, 'The browser preset is missing')
            profile = json.loads((ROOT / 'configs/live_smoke.json').read_text(encoding='utf-8'))
            self.assertEqual(contract['live_smoke'], profile)
            self.assertEqual(contract['defaults']['match']['max_turns'], 12)
            self.assertEqual(contract['defaults']['players']['PYRA']['provider'], 'anthropic')

    def test_stale_companion_rejects_changed_profile_or_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('configs', 'parallax_relay', 'scripts'):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            # Exercise an already-CRLF checkout even on Linux/macOS.
            for name in ('configs/live_smoke.json', 'scripts/live_smoke.py'):
                path = root / name
                path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            original = runtime_fingerprint(root)
            for name in ('configs/live_smoke.json', 'scripts/live_smoke.py'):
                with self.subTest(name=name):
                    path = root / name
                    content = path.read_bytes()
                    path.write_bytes(content + b'\n')
                    self.assertNotEqual(runtime_fingerprint(root), original,
                                        'Changed smoke inputs must invalidate a stale companion')
                    path.write_bytes(content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
                    self.assertEqual(runtime_fingerprint(root), original)
                    path.write_bytes(content)
