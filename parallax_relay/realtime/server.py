"""Local HTTP transport for the spectator, its event journal and manual controls."""
from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Protocol

from ..protocol import MAX_REPLY_CHARS, ROLES, _unique_object


ASSET_ROOT = Path(__file__).resolve().parents[2] / 'tools' / 'realtime_spectator'
WEB_FILES = {'index.html', 'app.js', 'manual.js', 'presentation.js', 'scene.js', 'style.css'}
ART_FILES = {
    'room-background.png', 'floor.png', 'bridge.png', 'motor-console.png',
    'memory-shard.png', 'energy-cell.png', 'exit-open.png', 'exit-closed.png',
    'animations/manifest.json',
    *(f'{role.lower()}-idle.png' for role in ROLES),
    *(f'animations/sheets/{role.lower()}-{pose}.png'
      for role in ROLES for pose in ('idle', 'walk', 'jump')),
}
MEDIA_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript',
               '.css': 'text/css', '.png': 'image/png', '.json': 'application/json'}
PUBLIC_STATUS_FIELDS = ('mode', 'status', 'run_id', 'window_ticks', 'action_points')
OFFLINE_MODES = {'reactive', 'manual', 'baseline', 'test'}


class SpectatorSession(Protocol):
    def status(self) -> dict: ...
    def events(self, after: int) -> dict: ...
    def feed(self, role: str, window: int) -> bytes | None: ...
    def start(self) -> bool: ...
    def submit(self, data: dict) -> dict: ...
    def close(self) -> None: ...


class SpectatorServer(ThreadingHTTPServer):
    """Serve one active session at a time; the simulation owns its clock."""

    daemon_threads = True
    request_queue_size = 32

    def __init__(self, session: SpectatorSession, host: str = '127.0.0.1', port: int = 0,
                 *, new_session: Callable[[], SpectatorSession] | None = None):
        if host not in ('127.0.0.1', 'localhost'):
            raise ValueError('The spectator requires the IPv4 loopback address.')
        self.session = session
        self.new_session = new_session
        self.token = secrets.token_urlsafe(32)
        self._controls = Lock()
        self._closed = False
        # Always bind and advertise the numeric address, including for "localhost".
        super().__init__(('127.0.0.1', port), SpectatorHandler)
        self.authority = '127.0.0.1' if self.server_port == 80 else f'127.0.0.1:{self.server_port}'
        self.url = f'http://{self.authority}/'

    def public_status(self) -> dict:
        status = self.session.status()
        public = {key: status[key] for key in PUBLIC_STATUS_FIELDS if key in status}
        if self.new_session is not None and status['mode'] in OFFLINE_MODES:
            public['restart_available'] = True
        return {**public, 'token': self.token}

    def control(self, route: str, data: dict) -> tuple[int, dict]:
        with self._controls:
            if self._closed:
                return 409, {'error': 'The session is closed.'}
            session = self.session
            status = session.status()
            mode = status['mode']
            if route in ('/api/start', '/api/restart'):
                if 'run_id' not in data:
                    if route == '/api/restart' or self.new_session is not None:
                        return 400, {'error': 'Expected the current match ID.'}
                elif data['run_id'] != status['run_id']:
                    return 409, {'error': 'The match has changed. Try again on the current match.'}
            if route == '/api/start':
                if mode not in OFFLINE_MODES:
                    return 403, {'error': 'The browser can start only an offline session.'}
                if session.start():
                    return 200, {'started': True}
                return 409, {'error': 'This session has already started.'}
            if route == '/api/restart':
                if self.new_session is None or mode not in OFFLINE_MODES:
                    return 403, {'error': 'Restart is available only in the offline viewer.'}
                if status['status'] == 'idle':
                    return 409, {'error': 'The match is already ready to start.'}
                if status['status'] == 'running':
                    session.close()
                    if session.status()['status'] != 'ended':
                        return 409, {'error': 'The previous match is still stopping. Try again shortly.'}
                replacement = self.new_session()
                self.session = replacement
                return 200, {'run_id': replacement.status()['run_id']}
            if mode != 'manual':
                return 403, {'error': 'Plans can be submitted only in manual mode.'}
        # Admission may wait for the match loop. Other requests and shutdown
        # must remain able to run while this role awaits its individual receipt.
        verdict = session.submit(data)
        return (200 if verdict['ok'] else 409), verdict

    def server_close(self) -> None:
        super().server_close()
        with self._controls:
            if not self._closed:
                self._closed = True
                self.session.close()


def _reject_constant(_: str) -> None:
    raise ValueError('Nonfinite number.')


class SpectatorHandler(BaseHTTPRequestHandler):
    server: SpectatorServer
    timeout = 10

    def log_message(self, *args) -> None:
        pass  # Cursor polling is frequent. The session records its own events.

    def _send(self, code: int, body: bytes, media_type: str, *, description: str = '') -> None:
        try:
            self.send_response(code)
            self.send_header('Content-Type', media_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('Referrer-Policy', 'no-referrer')
            if description and description.isascii() and '\r' not in description and '\n' not in description:
                self.send_header('X-Relay-Sensor-Description', description)
            if media_type.startswith('text/html'):
                self.send_header('X-Frame-Options', 'DENY')
                self.send_header('Content-Security-Policy',
                                 "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                 "img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; "
                                 "base-uri 'none'; form-action 'none'")
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            pass  # Closing a tab cannot interrupt the session.

    def _json(self, code: int, value: dict) -> None:
        self._send(code, json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8'),
                   'application/json')

    def _error(self, code: int, message: str) -> None:
        self._json(code, {'error': message})

    def _allowed(self, *, token: bool) -> bool:
        hosts = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if hosts != [self.server.authority] or origins not in ([], [self.server.url[:-1]]):
            return False
        if self.path.startswith('/api/') and self.headers.get_all('Sec-Fetch-Site', []) not in (
                [], ['same-origin'], ['none']):
            return False
        if token:
            values = self.headers.get_all('X-Relay-Token', [])
            return len(values) == 1 and values[0].isascii() and secrets.compare_digest(
                values[0], self.server.token)
        return True

    def do_GET(self) -> None:
        api = self.path.startswith('/api/')
        if not self._allowed(token=api and self.path != '/api/status'):
            self._error(403, 'Session rejected.')
            return
        if not api:
            self._static()
            return
        try:
            if self.path == '/api/status':
                self._json(200, self.server.public_status())
                return
            path, separator, query = self.path.partition('?')
            if path == '/api/events':
                after = 0
                if separator:
                    match = re.fullmatch(r'after=([0-9]{1,16})', query)
                    if not match:
                        self._error(400, 'Expected a nonnegative event cursor.')
                        return
                    after = int(match[1])
                self._json(200, self.server.session.events(after))
                return
            match = re.fullmatch(r'/api/feed/([A-Z]+)/([0-9]{1,16})', self.path)
            if match and match[1] in ROLES:
                session = self.server.session
                run_ids = self.headers.get_all('X-Relay-Run-ID', [])
                if len(run_ids) != 1 or not run_ids[0]:
                    if run_ids or self.server.new_session is not None:
                        self._error(400, 'Expected the current match ID.')
                        return
                elif run_ids[0] != session.status()['run_id']:
                    self._error(409, 'The match has changed. Try again on the current match.')
                    return
                png = session.feed(match[1], int(match[2]))
                if png is not None:
                    describe = getattr(session, 'feed_description', None)
                    caption = describe(match[1], int(match[2])) if describe else ''
                    self._send(200, png, 'image/png', description=caption)
                    return
            self._error(404, 'Not found.')
        except (OSError, RuntimeError, ValueError):
            self._error(503, 'The session is unavailable.')

    def _static(self) -> None:
        if self.path == '/favicon.ico':
            self._send(204, b'', 'image/x-icon')
            return
        route = self.path[1:] if self.path.startswith('/') else ''
        if self.path == '/':
            relative = 'web/index.html'
        elif route in WEB_FILES:
            relative = 'web/' + route
        elif route.startswith('art/') and route[4:] in ART_FILES:
            relative = route
        else:
            self._error(404, 'Not found.')
            return
        try:
            target = (ASSET_ROOT / relative).resolve(strict=True)
            if not target.is_relative_to(ASSET_ROOT.resolve()) or not target.is_file():
                raise FileNotFoundError
            body = target.read_bytes()
        except (OSError, ValueError, RuntimeError):
            self._error(404, 'Not found.')
            return
        self._send(200, body, MEDIA_TYPES[target.suffix])

    def _read_object(self) -> dict:
        lengths = self.headers.get_all('Content-Length', [])
        types = self.headers.get_all('Content-Type', [])
        if (self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Content-Encoding')
                or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,5}', lengths[0])
                or len(types) != 1 or types[0].split(';', 1)[0].strip().lower() != 'application/json'):
            raise ValueError('Invalid JSON request headers.')
        length = int(lengths[0])
        if not 0 < length <= MAX_REPLY_CHARS:
            raise ValueError('Invalid request size.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('Incomplete request body.')
        body = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
        if not isinstance(body, dict):
            raise ValueError('Expected an object.')
        return body

    def do_POST(self) -> None:
        if not self._allowed(token=True):
            self._error(403, 'Session rejected.')
            return
        if self.path not in ('/api/start', '/api/restart', '/api/plan'):
            self._error(404, 'Not found.')
            return
        try:
            body = self._read_object()
        except (OSError, ValueError, RecursionError):
            self._error(400, 'Expected a bounded UTF-8 JSON object with a valid length.')
            return
        if self.path in ('/api/start', '/api/restart'):
            valid_id = body.keys() == {'run_id'} and isinstance(body['run_id'], str) and bool(body['run_id'])
            if not (valid_id or self.path == '/api/start' and not body):
                self._error(400, 'Expected the current match ID.')
                return
        if self.path == '/api/plan' and (
                body.keys() != {'window', 'role', 'request_id', 'actions'}
                or type(body['window']) is not int or body['window'] < 0
                or body['role'] not in ROLES or not isinstance(body['request_id'], str)
                or not body['request_id'] or not isinstance(body['actions'], list)):
            self._error(400, 'A plan requires its window, role, request ID and actions.')
            return
        try:
            code, result = self.server.control(self.path, body)
            self._json(code, result)
        except (OSError, RuntimeError, ValueError):
            self._error(503, 'The session is unavailable.')


def serve(session: SpectatorSession, host: str = '127.0.0.1', port: int = 0,
          ready: Callable[[str], None] | None = None, *,
          new_session: Callable[[], SpectatorSession] | None = None) -> None:
    """Publish the bound URL before accepting controls; keep serving after the run ends."""
    with SpectatorServer(session, host, port, new_session=new_session) as server:
        print(f'Open {server.url} in your browser.', flush=True)
        try:
            if ready is not None:
                ready(server.url)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
