"""Run from the Parallax Relay checkout using its activated Python environment."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import re
import subprocess
import sys
import tempfile
from threading import Lock
from urllib.parse import urlparse

from run_records import read_run
from runtime_contract import checkout_source, runtime_fingerprint

ROOT = Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "site"
if not (ASSETS / "contract.json").is_file():
    ASSETS = HERE.parent / "build" / "workbench" / "dist"
if not (ASSETS / "contract.json").is_file():
    raise SystemExit("Build the workbench first with python site/build_workbench.py.")
CONTRACT = json.loads((ASSETS / "contract.json").read_text(encoding="utf-8"))

# Resolve the engine from the active checkout.
sys.path.insert(0, str(ROOT))
from parallax_relay.config import GameConfig

TOKEN = secrets.token_urlsafe(32)
MIME_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".zip": "application/zip",
}


def config_toml(config: GameConfig) -> str:
    # JSON strings and numbers are valid TOML scalars for this schema.
    lines = ["[match]"]
    lines.extend(
        f"{name} = {json.dumps(value)}"
        for name, value in config.match.model_dump().items()
        if value is not None
    )
    for role, player in config.players.items():
        lines.append(f"\n[players.{role}]")
        lines.extend(
            f"{name} = {json.dumps(value)}"
            for name, value in player.model_dump(exclude={"pricing"}).items()
        )
        if player.pricing:
            lines.append(f"\n[players.{role}.pricing]")
            lines.extend(f"{name} = {value}" for name, value in player.pricing.model_dump().items())
    return "\n".join(lines) + "\n"


def execute(config: dict) -> dict:
    if runtime_fingerprint(ROOT) != CONTRACT["runtime_fingerprint"]:
        raise ValueError("The runtime has changed since this build.")
    validated = GameConfig.model_validate(config)
    with tempfile.TemporaryDirectory(prefix="parallax-workbench-") as temp:
        path = Path(temp)
        settings = path / "config.toml"
        output = path / "run"
        settings.write_text(config_toml(validated), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "parallax_relay.play", "--mock", "--quiet",
             "--config", str(settings), "--out", str(output)],
            cwd=ROOT, capture_output=True, timeout=180, check=False,
        )
        # The CLI can exit nonzero with useful partial or budget-stop records.
        data = read_run(output)
        source = checkout_source(ROOT)
        data["source_commit"] = source["revision"] or "unavailable"
        data["source_status"] = source["status"]
        return data


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        self.run_lock = Lock()
        super().__init__(*args, **kwargs)


class Handler(BaseHTTPRequestHandler):
    timeout = 10

    def log_message(self, *args):
        pass

    def send_bytes(self, code: int, payload: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if content_type == "text/html":
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # A closed browser must not produce an unhandled write traceback.

    def send_json(self, code: int, body: dict) -> None:
        self.send_bytes(code, json.dumps(body).encode("utf-8"), "application/json")

    def allowed(self) -> bool:
        host = f"127.0.0.1:{self.server.server_port}"
        origin = f"http://{host}"
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        return hosts == [host] and (not origins or origins == [origin])

    def do_GET(self):
        if not self.allowed():
            self.send_json(403, {"error": "Origin rejected"})
            return
        if self.path == "/api/status":
            self.send_json(200, {"token": TOKEN, "commit": CONTRACT["commit"]})
            return
        try:
            relative = urlparse(self.path).path.lstrip("/") or "index.html"
            file = (ASSETS / relative).resolve()
            if not file.is_relative_to(ASSETS.resolve()) or not file.is_file():
                raise ValueError("Not a workbench file")
            payload = file.read_bytes()
        except (OSError, ValueError):
            self.send_json(404, {"error": "Not found"})
            return
        self.send_bytes(200, payload, MIME_TYPES.get(file.suffix, "application/octet-stream"))

    def do_POST(self):
        tokens = self.headers.get_all("X-Relay-Token", [])
        valid_token = len(tokens) == 1 and tokens[0].isascii() and secrets.compare_digest(tokens[0], TOKEN)
        if not self.allowed() or not valid_token:
            self.send_json(403, {"error": "Session rejected"})
            return
        if self.path != "/api/mock":
            self.send_json(404, {"error": "Only offline execution is available"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]) or self.headers.get_all("Transfer-Encoding"):
                raise ValueError("Invalid body length")
            length = int(lengths[0])
            if not 0 < length < 65536:
                raise ValueError("Invalid body length")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete body")
            config = json.loads(body)
            if not self.server.run_lock.acquire(blocking=False):
                self.send_json(409, {"error": "An offline run is already in progress."})
                return
            try:
                data = execute(config)
            finally:
                self.server.run_lock.release()
        except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
            self.send_json(400, {"error": "Run failed. Check the checkout, build and match settings."})
            return
        self.send_json(200, data)


if __name__ == "__main__":
    if runtime_fingerprint(ROOT) != CONTRACT["runtime_fingerprint"]:
        raise SystemExit("Checkout runtime differs from this build. Rebuild or use the matching checkout.")
    with WorkbenchServer(("127.0.0.1", 0), Handler) as server:
        print(f"Open http://127.0.0.1:{server.server_port} in your browser.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
