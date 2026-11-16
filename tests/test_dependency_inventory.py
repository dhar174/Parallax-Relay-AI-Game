"""Behavior checks for the offline dependency/license inventory collector."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/dependency_inventory.py"


class DependencyInventoryTests(unittest.TestCase):
    def load_collector(self):
        spec = importlib.util.spec_from_file_location("dependency_inventory", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_record_paths_cannot_disclose_private_metadata_or_escape_license_area(self):
        module = self.load_collector()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "demo-1.0.dist-info"
            (dist / "licenses").mkdir(parents=True)
            (dist / "METADATA").write_text("Name: demo\nVersion: 1.0\n", encoding="utf-8")
            (dist / "direct_url.json").write_text("FAKE-PRIVATE-INSTALL-URL", encoding="utf-8")
            (root / "outside.txt").write_text("FAKE-OUTSIDE-CONTENT", encoding="utf-8")
            (dist / "licenses/LICENSE").write_text("Legitimate notice\n", encoding="utf-8")
            try:
                (dist / "licenses/LICENSE-alias").symlink_to(dist / "direct_url.json")
                (dist / "licenses/LICENSE-escape").symlink_to(root / "outside.txt")
                (dist / "licenses/LICENSE-hardlink").hardlink_to(dist / "direct_url.json")
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"filesystem link creation unavailable: {type(error).__name__}")
            entries = ["demo-1.0.dist-info/licenses/LICENSE",
                       "demo-1.0.dist-info/licenses/../direct_url.json",
                       "demo-1.0.dist-info/licenses/direct_url.json",
                       "demo-1.0.dist-info/licenses/LICENSE-alias",
                       "demo-1.0.dist-info/licenses/LICENSE-escape",
                       "demo-1.0.dist-info/licenses/LICENSE-hardlink",
                       str(dist / "direct_url.json")]
            (dist / "licenses/direct_url.json").write_text("FAKE-PRIVATE-COPY", encoding="utf-8")
            (dist / "RECORD").write_text("".join(path + ",,\n" for path in entries), encoding="utf-8")
            result = module.collect_inventory([tmp])
        serialized = json.dumps(result)
        for sentinel in ["FAKE-PRIVATE-INSTALL-URL", "FAKE-OUTSIDE-CONTENT", "FAKE-PRIVATE-COPY"]:
            self.assertNotIn(sentinel, serialized)
        licenses = result["packages"][0]["license_files"]
        self.assertEqual([f["text"] for f in licenses if f["text"] is not None], ["Legitimate notice\n"])

    def test_unavailable_license_files_do_not_abort_other_packages(self):
        module = self.load_collector()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "broken-1.0.dist-info"
            (broken / "licenses/LICENSE-directory").mkdir(parents=True)
            (broken / "METADATA").write_text(
                "Metadata-Version: 2.4\nName: broken\nVersion: 1.0\n"
                "License-File: LICENSE-missing\n", encoding="utf-8")
            denied = broken / "licenses/LICENSE-denied"
            denied.write_text("Unreadable notice", encoding="utf-8")
            denied.chmod(0)
            (broken / "RECORD").write_text(
                "broken-1.0.dist-info/licenses/LICENSE-denied,,\n"
                "broken-1.0.dist-info/licenses/LICENSE-directory,,\n", encoding="utf-8")
            good = root / "good-1.0.dist-info"
            good.mkdir()
            (good / "METADATA").write_text("Name: good\nVersion: 1.0\n", encoding="utf-8")
            (good / "LICENSE").write_text("Keep this notice", encoding="utf-8")
            (good / "RECORD").write_text("good-1.0.dist-info/LICENSE,,\n", encoding="utf-8")
            original = Path.read_bytes
            # Root can read chmod(000) files; reproduce that OS error at the I/O boundary.
            def read_bytes(path):
                if path == denied:
                    raise PermissionError("FAKE-PRIVATE-PERMISSION-DETAIL")
                return original(path)
            with patch.object(Path, "read_bytes", read_bytes):
                result = module.collect_inventory([tmp])
            denied.chmod(0o600)
        self.assertEqual([p["name"] for p in result["packages"]], ["broken", "good"])
        broken_files = {Path(f["path"]).name: f for f in result["packages"][0]["license_files"]}
        self.assertEqual(set(broken_files), {"LICENSE-denied", "LICENSE-directory", "LICENSE-missing"})
        for name, error in [("LICENSE-denied", "PermissionError"),
                            ("LICENSE-directory", "IsADirectoryError"),
                            ("LICENSE-missing", "FileNotFoundError")]:
            self.assertIsNone(broken_files[name]["text"])
            self.assertIsNone(broken_files[name]["sha256"])
            self.assertEqual(broken_files[name]["text_error"], error)
        self.assertEqual(result["packages"][1]["license_files"][0]["text"], "Keep this notice")
        self.assertNotIn("FAKE-PRIVATE-PERMISSION-DETAIL", json.dumps(result))

    def test_declared_license_absent_from_missing_record_is_explicit(self):
        module = self.load_collector()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "declared-1.0.dist-info"
            dist.mkdir()
            (dist / "METADATA").write_text(
                "Metadata-Version: 2.4\nName: declared\nVersion: 1.0\nLicense-File: COPYING\n", encoding="utf-8")
            result = module.collect_inventory([tmp])
        files = result["packages"][0]["license_files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "declared-1.0.dist-info/licenses/COPYING")
        self.assertEqual(files[0]["text_error"], "FileNotFoundError")

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
