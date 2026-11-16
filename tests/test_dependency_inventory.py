"""Behavior checks for the offline dependency/license inventory collector."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/dependency_inventory.py"


class DependencyInventoryTests(unittest.TestCase):
    def test_installed_metadata_keeps_license_text_and_explicit_unknowns(self):
        self.assertTrue(SCRIPT.exists(), "inventory collector is not implemented")
        spec = importlib.util.spec_from_file_location("dependency_inventory", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            licensed = root / "licensed_demo-1.2.dist-info"
            (licensed / "licenses").mkdir(parents=True)
            (licensed / "METADATA").write_text(
                "Metadata-Version: 2.4\nName: licensed-demo\nVersion: 1.2\n"
                "License-Expression: BSD-3-Clause\nLicense-File: LICENSE\n"
                "Author-email: private@example.invalid\n", encoding="utf-8")
            (licensed / "licenses/LICENSE").write_text("Retain this notice.\n", encoding="utf-8")
            (licensed / "licenses/NOTICE").write_bytes(b"\xa9 legacy notice")
            (licensed / "RECORD").write_text(
                "licensed_demo-1.2.dist-info/licenses/LICENSE,,\n"
                "licensed_demo-1.2.dist-info/licenses/NOTICE,,\n", encoding="utf-8")
            unknown = root / "unknown_demo-2.0.dist-info"
            unknown.mkdir()
            (unknown / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: unknown-demo\nVersion: 2.0\n", encoding="utf-8")
            result = module.collect_inventory([tmp])
        packages = result["packages"]
        self.assertEqual([p["name"] for p in packages], ["licensed-demo", "unknown-demo"])
        self.assertEqual(packages[0]["license_expression"], "BSD-3-Clause")
        self.assertEqual(packages[0]["license_files"][0]["text"], "Retain this notice.\n")
        self.assertEqual(packages[0]["license_files"][0]["sha256"],
                         "969ef3a4d8eb29f1e88cded83946011142bcc2a3c72b96a7f41ad9c24b846bc7")
        self.assertIsNone(packages[0]["license_files"][1]["text"])
        self.assertEqual(packages[0]["license_files"][1]["text_error"], "not UTF-8")
        self.assertIsNone(packages[1]["license_expression"])
        self.assertEqual(packages[1]["license_files"], [])
        self.assertNotIn("private@example.invalid", json.dumps(result))

    def test_cli_emits_json_without_environment_secrets(self):
        self.assertTrue(SCRIPT.exists(), "inventory collector is not implemented")
        import os
        env = dict(os.environ, INVENTORY_SECRET_SENTINEL="do-not-collect-this-value")
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                text=True, env=env, check=True)
        inventory = json.loads(result.stdout)
        self.assertIn("python", inventory)
        self.assertIn("platform", inventory)
        self.assertIn("packages", inventory)
        self.assertNotIn("do-not-collect-this-value", result.stdout)


if __name__ == "__main__":
    unittest.main()
