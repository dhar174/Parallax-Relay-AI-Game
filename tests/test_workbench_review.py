"""Offline regressions for the independent workbench review."""
from contextlib import contextmanager, redirect_stderr
import http.client
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
try:
    import build_workbench
    import runtime_contract
    from run_records import read_run
finally:
    sys.path.remove(str(ROOT / "site"))


class WorkbenchReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.work.cleanup)
        output = build_workbench.build(Path(cls.work.name) / "dist")
        with zipfile.ZipFile(output / "relay-workbench.zip") as archive:
            archive.extractall(Path(cls.work.name) / "unpacked")
        companion = Path(cls.work.name) / "unpacked" / "relay-workbench"
        spec = importlib.util.spec_from_file_location("review_companion", companion / "relay_workbench.py")
        cls.companion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.companion)

    @contextmanager
    def server(self, timeout=2):
        handler = type("TestHandler", (self.companion.Handler,), {"timeout": timeout})
        with self.companion.WorkbenchServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                yield server
            finally:
                server.shutdown()
                thread.join(3)
                self.assertFalse(thread.is_alive())

    def request(self, server, method="GET", path="/api/status", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=1)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_stalled_body_does_not_block_status_and_times_out_safely(self):
        errors = io.StringIO()
        with redirect_stderr(errors), self.server() as server:
            with socket.create_connection(server.server_address, timeout=3) as stalled:
                request = (f"POST /api/mock HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                           f"X-Relay-Token: {self.companion.TOKEN}\r\nContent-Length: 100\r\n\r\n{{")
                stalled.sendall(request.encode("ascii"))
                self.assertEqual(self.request(server)[0], 200)
                response = http.client.HTTPResponse(stalled)
                response.begin()
                self.assertEqual(response.status, 400)
                self.assertIn("error", json.loads(response.read()))
        self.assertNotIn("Traceback", errors.getvalue())

    def test_nested_json_gets_a_sanitized_response(self):
        errors = io.StringIO()
        with redirect_stderr(errors), self.server() as server:
            payload = '{"a":' * 2000 + '0' + '}' * 2000
            status, _, body = self.request(server, "POST", "/api/mock", payload,
                                           {"X-Relay-Token": self.companion.TOKEN})
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(body))
        self.assertNotIn("Traceback", errors.getvalue())

    def test_strict_headers_html_protection_and_path_boundaries(self):
        with self.server() as server:
            status, headers, _ = self.request(server, path="/")
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("X-Frame-Options"), "DENY")
            self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))
            for path in ("/../AGENTS.md", "/%2e%2e/AGENTS.md", "/api/live"):
                self.assertEqual(self.request(server, path=path)[0], 404)
            for name, value in (("Host", "evil.invalid"), ("Origin", "null")):
                self.assertEqual(self.request(server, headers={name: value})[0], 403)
            self.assertEqual(self.request(server, "POST", "/api/mock", "{}")[0], 403)
            origin = f"http://127.0.0.1:{server.server_port}"
            for extra, expected in (("Content-Length: +2", 400), ("Content-Length: 1_0", 400),
                          ("Content-Length: 2\r\nContent-Length: 2", 400),
                          ("Content-Length: 2\r\nHost: duplicate", 403),
                          (f"Content-Length: 2\r\nOrigin: {origin}\r\nOrigin: {origin}", 403),
                          (f"Content-Length: 2\r\nX-Relay-Token: {self.companion.TOKEN}", 403),
                          ("Content-Length: 2\r\nTransfer-Encoding: chunked", 400)):
                with socket.create_connection(server.server_address, timeout=2) as connection:
                    raw = (f"POST /api/mock HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                           f"X-Relay-Token: {self.companion.TOKEN}\r\n{extra}\r\n\r\n{{}}")
                    connection.sendall(raw.encode("ascii"))
                    response = http.client.HTTPResponse(connection)
                    response.begin()
                    self.assertEqual(response.status, expected)
                    response.read()

    def test_concurrent_mock_is_rejected_without_duplicate_execution(self):
        started, release = threading.Event(), threading.Event()
        result = read_run(ROOT / "example_run")
        def execute(_):
            started.set()
            self.assertTrue(release.wait(3))
            return result
        first = []
        with self.server() as server, patch.object(self.companion, "execute", side_effect=execute) as mocked:
            headers = {"X-Relay-Token": self.companion.TOKEN}
            worker = threading.Thread(target=lambda: first.append(self.request(server, "POST", "/api/mock", "{}", headers)))
            worker.start()
            try:
                self.assertTrue(started.wait(1))
                self.assertEqual(self.request(server, "POST", "/api/mock", "{}", headers)[0], 409)
            finally:
                release.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(first[0][0], 200)
            self.assertEqual(mocked.call_count, 1)

    def test_native_reader_rejects_wrong_record_types_and_filters_images(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "run"
            shutil.copytree(ROOT / "example_run", directory)
            (directory / "unrelated.png").write_bytes(b"not a run image")
            self.assertFalse("unrelated.png" in read_run(directory)["images"])
            for name, text in (("result.json", "[]"), ("calls.jsonl", "null\n")):
                path = directory / name
                original = path.read_bytes()
                path.write_text(text, encoding="utf-8")
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                with self.assertRaises(ValueError):
                    read_run(directory)
                path.write_bytes(original)
                self.assertEqual(path.read_bytes(), original)
            image = directory / "final_spectator.png"
            image.write_bytes(b"invalid PNG")
            self.assertEqual(image.read_bytes(), b"invalid PNG")
            with self.assertRaises(ValueError):
                read_run(directory)

    def test_gitless_and_unrelated_parent_identity_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            subprocess.run(["git", "init", "-q", str(parent)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(parent), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "test", "--allow-empty"], check=True, capture_output=True)
            root = parent / "archive"
            root.mkdir()
            self.assertEqual(runtime_contract.checkout_revision(root), "unavailable")
            with patch.dict(os.environ, {"GIT_DIR": str(parent / ".git"), "GIT_WORK_TREE": str(parent)}):
                self.assertEqual(runtime_contract.checkout_revision(root), "unavailable")

    def test_dirty_source_and_probe_failures_are_explicit(self):
        source = runtime_contract.checkout_source(ROOT)
        self.assertEqual(source["revision"], subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
        self.assertIn(source["status"], ("clean", "dirty"))
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("git", 1)):
            with patch.object(runtime_contract.subprocess, "run", side_effect=error):
                self.assertEqual(runtime_contract.checkout_source(ROOT)["status"], "unavailable")

    def test_gitless_archive_build_and_actual_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            root.mkdir()
            for name in ("parallax_relay", "configs", "example_run", "site", "docs"):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copyfile(ROOT / "LICENSE", root / "LICENSE")
            completed = subprocess.run([sys.executable, "site/build_workbench.py"], cwd=root,
                                       capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            contract = json.loads((root / "build/workbench/dist/contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["commit"], "unavailable")
            self.assertEqual(contract["source_status"], "unavailable")
            code = """
import sys,json
sys.path.insert(0,'site')
from relay_workbench import CONTRACT,execute
config=CONTRACT['defaults'];config['match'].update(max_turns=1,max_calls=18)
data=execute(config)
print(json.dumps({'calls':data['result']['budget']['calls_started'],'source':data['source_commit'],'status':data['source_status']}))
"""
            completed = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                                       text=True, encoding="utf-8", timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            self.assertEqual(json.loads(completed.stdout), {"calls": 9, "source": "unavailable", "status": "unavailable"})

    def test_zip_is_independent_of_input_mtimes_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "site"
            shutil.copytree(ROOT / "site", source, ignore=shutil.ignore_patterns("__pycache__"))
            outputs = []
            with patch.object(build_workbench, "SITE", source):
                for index, mode in enumerate((0o600, 0o644)):
                    for path in source.rglob("*"):
                        if path.is_file():
                            os.chmod(path, mode)
                            os.utime(path, (1600000000 + index * 100, 1600000000 + index * 100))
                    output = build_workbench.build(root / str(index))
                    outputs.append((output / "relay-workbench.zip").read_bytes())
            self.assertEqual(hashlib.sha256(outputs[0]).hexdigest(), hashlib.sha256(outputs[1]).hexdigest())
            with zipfile.ZipFile(io.BytesIO(outputs[0])) as archive:
                self.assertEqual(archive.read("relay-workbench/LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))
                self.assertTrue(all((info.external_attr >> 16) & 0o777 == 0o644 for info in archive.infolist()))
