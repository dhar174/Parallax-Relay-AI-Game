"""Offline smoke check for published workbench inputs and real CLI artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
sys.path.insert(0, str(SITE))
try:
    from build_workbench import build
finally:
    sys.path.remove(str(SITE))

from parallax_relay.config import GameConfig
from parallax_relay.protocol import ROLES


class WorkbenchTests(unittest.TestCase):
    def test_build_and_run_bundled_companion(self):
        with tempfile.TemporaryDirectory() as work:
            output = build(Path(work) / "dist")
            contract = json.loads((output / "contract.json").read_text(encoding="utf-8"))
            fixture = json.loads((output / "fixture.json").read_text(encoding="utf-8"))
            defaults = GameConfig.model_validate(contract["defaults"])
            self.assertEqual(set(defaults.players), set(ROLES))
            self.assertEqual(contract["schema"], GameConfig.model_json_schema())
            self.assertEqual(fixture["manifest"]["mode"], "mock")
            self.assertTrue(fixture["images"])

            target = Path(work) / "unpacked"
            with zipfile.ZipFile(output / "relay-workbench.zip") as archive:
                archive.extractall(target)
            companion = target / "relay-workbench"
            check = """
import json
from relay_workbench import CONTRACT, execute
config = CONTRACT["defaults"]
config["match"].update(max_turns=1, max_calls=18)
print(json.dumps(execute(config)))
"""
            # Python resolves the game from cwd and the companion from PYTHONPATH.
            env = {**os.environ, "PYTHONPATH": str(companion)}
            completed = subprocess.run(
                [sys.executable, "-c", check], cwd=ROOT, env=env,
                capture_output=True, text=True, check=True, timeout=45,
            )
            run = json.loads(completed.stdout)
            self.assertEqual(run["result"]["stop_reason"], "turn_limit")
            self.assertEqual(run["result"]["budget"]["calls_started"], 9)
            self.assertIsNone(run["result"]["scores"])
            self.assertEqual(len(run["replay"]), 1)
            for role in ROLES:
                image = run["replay"][0]["observations"][role]["image"]
                self.assertIn(image, run["images"])
