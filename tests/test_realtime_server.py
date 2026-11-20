"""Real loopback requests against a temporary public/private journal."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.client import HTTPConnection
from io import BytesIO, StringIO
import json
from pathlib import Path
import socket
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from PIL import Image

from parallax_relay.realtime.journal import Journal
from parallax_relay.realtime import server as transport


def manual_plan(**changes):
    return {'window': 1, 'role': 'PYRA', 'request_id': 'open-slot',
            'actions': [{'kind': 'VENT', 'direction': None, 'ticks': None, 'jump_at': None}],
            **changes}


class SessionProbe:
    """The controller owns this worker; polling and repeat starts cannot replace it."""

    def __init__(self, journal):
        self.journal = journal
        self.events = journal.events
        self.feed = journal.feed
        self.mode = 'manual'
        self.state = 'idle'
        self.stop = Event()
        self.worker = None
        self.starts = 0
        self.closes = 0
        self.plans = []

    def status(self):
        return {'mode': self.mode, 'status': self.state, 'run_id': self.journal.run_id,
                'window_ticks': 120, 'action_points': 8, 'host_only': 'private-status-value'}

    def start(self):
        if self.worker:
            return False
        self.starts += 1
        self.state = 'running'
        self.worker = Thread(target=self.stop.wait)
        self.worker.start()
        return True

    def submit(self, data):
        self.plans.append(data)
        if data['request_id'] != 'open-slot':
            return {'ok': False, 'error': 'That request is closed.'}
        return {'ok': True, 'points': 2}

    def close(self):
        self.closes += 1
        self.stop.set()
        if self.worker:
            self.worker.join(2)
        self.state = 'ended'


class SpectatorTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.journal = Journal(self.root / 'run')
        self.session = SessionProbe(self.journal)
        self.server = transport.SpectatorServer(self.session)
        self.listener = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.listener.start()
        self.addCleanup(self.stop_server)
        self.host = [('Host', self.server.authority)]
        self.auth = [*self.host, ('X-Relay-Token', self.server.token)]

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.listener.join(2)
        self.assertFalse(self.listener.is_alive())
        self.assertEqual(self.session.closes, 1)

    def exchange(self, method, path, headers, body=b'', *, end_input=False):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(body)
            if end_input:
                connection.sock.shutdown(socket.SHUT_WR)
            with connection.getresponse() as response:
                return response.status, response.headers, response.read()
        finally:
            connection.close()

    def get(self, path):
        return self.exchange('GET', path, self.auth)

    def post(self, path, value):
        body = json.dumps(value).encode()
        return self.exchange('POST', path, [*self.auth, ('Content-Type', 'application/json'),
                                            ('Content-Length', str(len(body)))], body)

    def test_status_bootstraps_token_and_public_metadata_without_starting(self):
        code, headers, data = self.exchange('GET', '/api/status', self.host)
        self.assertEqual(code, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['Cross-Origin-Resource-Policy'], 'same-origin')
        self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
        self.assertEqual(json.loads(data), {
            'mode': 'manual', 'status': 'idle', 'run_id': self.journal.run_id,
            'window_ticks': 120, 'action_points': 8, 'token': self.server.token,
        })
        self.assertEqual(self.get('/api/events')[0], 200)
        self.assertEqual(self.session.starts, 0)

    def test_host_origin_and_fetch_metadata_guard_the_bootstrap(self):
        origin = ('Origin', self.server.url[:-1])
        self.assertEqual(self.exchange('GET', '/api/status', [*self.host, origin])[0], 200)
        for headers in ([], self.host * 2, [('Host', 'example.invalid')],
                        [*self.host, ('Origin', 'null')], [*self.host, origin, origin],
                        [*self.host, ('Sec-Fetch-Site', 'cross-site')],
                        [*self.host, ('Origin', 'http://127.0.0.1:1')]):
            with self.subTest(headers=headers):
                code, _, data = self.exchange('GET', '/api/status', headers)
                self.assertEqual(code, 403)
                self.assertNotIn('token', json.loads(data))

    def test_data_and_both_controls_require_one_matching_header_token(self):
        for method, path in [('GET', '/api/events?after=0'), ('GET', '/api/feed/FLUX/1'),
                             ('POST', '/api/start'), ('POST', '/api/plan')]:
            for token_values in ([], ['wrong'], [self.server.token] * 2):
                headers = [*self.host, *(('X-Relay-Token', token) for token in token_values)]
                with self.subTest(method=method, path=path, supplied=len(token_values)):
                    self.assertEqual(self.exchange(method, path, headers)[0], 403)
        self.assertEqual(self.exchange('GET', '/api/events?token=' + self.server.token, self.host)[0], 403)
        self.assertEqual(self.session.starts, 0)
        self.assertEqual(self.session.plans, [])

    def test_poll_reconnect_and_feed_use_only_persisted_public_data(self):
        first = self.journal.emit('dialogue', text='Open the bridge.', role='PYRA')
        private = 'role-local-note'
        self.journal.private('sealed', note=private)
        second = self.journal.emit('ready', role='FLUX')
        expected = {'run_id': self.journal.run_id, 'cursor': 2, 'watermark': 2,
                    'events': [first, second], 'reset': False, 'has_more': False}
        code, _, raw = self.get('/api/events?after=0')
        self.assertEqual(code, 200)
        self.assertNotIn(private.encode(), raw)
        self.assertEqual(json.loads(raw), expected)
        self.assertEqual(json.loads(self.get('/api/events?after=1')[2]), {**expected, 'events': [second]})
        self.assertEqual(json.loads(self.get('/api/events?after=2')[2]), {**expected, 'events': []})
        self.assertEqual(json.loads(self.get('/api/events?after=99')[2]), {**expected, 'reset': True})
        with patch.object(self.session, 'events', side_effect=lambda after: self.journal.events(after, limit=1)):
            page = json.loads(self.get('/api/events?after=0')[2])
            self.assertEqual(page, {**expected, 'cursor': 1, 'events': [first], 'has_more': True})
            self.assertEqual(json.loads(self.get(f'/api/events?after={page["cursor"]}')[2]),
                             {**expected, 'events': [second]})
        for query in ('after=', 'after=-1', 'after=1.5', 'after=2&after=2', 'unknown=0', 'after=' + '9'*17):
            with self.subTest(query=query):
                self.assertEqual(self.get('/api/events?' + query)[0], 400)
        image = BytesIO()
        Image.new('RGB', (4, 3), 'red').save(image, format='PNG')
        self.journal.store_feed('PYRA', 1, image.getvalue())
        code, headers, payload = self.get('/api/feed/PYRA/1')
        self.assertEqual((code, headers['Content-Type'], payload), (200, 'image/png', image.getvalue()))
        for path in ('/api/feed/PYRA/2', '/api/feed/SPECTRA/1', '/api/feed/ECHO/1',
                     '/api/feed/PYRA/-1', '/api/private', '/run/private.jsonl'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)
        self.assertEqual(self.session.starts, 0)

    def test_static_allowlist_returns_only_runtime_files(self):
        assets = self.root / 'assets'
        (assets / 'web').mkdir(parents=True)
        (assets / 'art').mkdir()
        (assets / 'web' / 'index.html').write_bytes(b'<title>Room</title>')
        (assets / 'web' / 'app.js').write_bytes(b'export {};')
        (assets / 'art' / 'bridge.png').write_bytes(b'bridge')
        (assets / 'art' / 'private.jsonl').write_bytes(b'private')
        with patch.object(transport, 'ASSET_ROOT', assets):
            code, headers, body = self.exchange('GET', '/', self.host)
            self.assertEqual((code, body), (200, b'<title>Room</title>'))
            self.assertEqual(headers['X-Frame-Options'], 'DENY')
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertIn("img-src 'self' blob:", headers['Content-Security-Policy'])
            self.assertEqual(self.get('/app.js')[1]['Content-Type'], 'text/javascript')
            self.assertEqual(self.get('/art/bridge.png')[2], b'bridge')
            for name in ('/art', '/web', '/art/private.jsonl', '/art/../run/private.jsonl',
                         '/art/%2e%2e/run/private.jsonl', '/art/animations/sheets/echo-jump.png'):
                with self.subTest(name=name):
                    self.assertEqual(self.get(name)[0], 404)

    def test_simultaneous_starts_launch_one_worker_and_close_joins_it(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.post('/api/start', {})[0], range(2)))
        self.assertCountEqual(replies, [200, 409])
        self.assertEqual(self.session.starts, 1)
        self.assertTrue(self.session.worker.is_alive())
        self.assertEqual(json.loads(self.get('/api/status')[2])['status'], 'running')
        self.server.shutdown()
        self.server.server_close()
        self.assertFalse(self.session.worker.is_alive())
        self.assertEqual(self.server.control('/api/start', {})[0], 409)

    def test_start_and_manual_controls_are_gated_by_the_host_mode(self):
        self.assertEqual(self.post('/api/start', {'mode': 'live'})[0], 400)
        for mode in ('live', 'unknown'):
            self.session.mode = mode
            self.assertEqual(self.post('/api/start', {})[0], 403)
            self.assertEqual(self.post('/api/plan', manual_plan())[0], 403)
        for mode in ('reactive', 'baseline', 'test'):
            self.session.mode = mode
            self.assertEqual(self.post('/api/plan', manual_plan())[0], 403)
        self.assertEqual(self.session.starts, 0)
        self.assertEqual(self.session.plans, [])

    def test_plan_shape_and_controller_admission_result(self):
        for invalid in ({}, [], manual_plan(extra='field'), manual_plan(role='ECHO'),
                        manual_plan(window=True), manual_plan(request_id=None), manual_plan(actions={})):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.post('/api/plan', invalid)[0], 400)
        self.assertEqual(self.session.plans, [])
        code, _, accepted = self.post('/api/plan', manual_plan())
        self.assertEqual((code, json.loads(accepted)), (200, {'ok': True, 'points': 2}))
        stale = manual_plan(request_id='obsolete')
        code, _, rejected = self.post('/api/plan', stale)
        self.assertEqual((code, json.loads(rejected)), (409, {'ok': False, 'error': 'That request is closed.'}))
        self.assertEqual(self.session.plans, [manual_plan(), stale])

    def test_headers_size_encoding_and_strict_json_checked_before_dispatch(self):
        length = ('Content-Length', '2')
        media = ('Content-Type', 'application/json')
        for extra in ([], [media], [length], [length, length, media], [length, media, media],
                      [length, media, ('Transfer-Encoding', 'chunked')], [length, ('Content-Type', 'text/plain')],
                      [media, ('Content-Length', '16385')], [media, ('Content-Length', '0')],
                      [media, ('Content-Length', '-2')]):
            with self.subTest(extra=extra):
                self.assertEqual(self.exchange('POST', '/api/start', [*self.auth, *extra], b'{}')[0], 400)
        for raw in (b'[]', b'invalid', b'{"mode":1,"mode":2}', b'{"x":NaN}', b'{"x":"\xff"}'):
            headers = [*self.auth, media, ('Content-Length', str(len(raw)))]
            self.assertEqual(self.exchange('POST', '/api/plan', headers, raw)[0], 400)
        headers = [*self.auth, media, ('Content-Length', '12')]
        self.assertEqual(self.exchange('POST', '/api/start', headers, b'{}', end_input=True)[0], 400)
        self.assertEqual(self.session.starts, 0)
        self.assertEqual(self.session.plans, [])

    def test_idle_connection_does_not_block_status(self):
        with socket.create_connection(self.server.server_address, timeout=3):
            self.assertEqual(self.exchange('GET', '/api/status', self.host)[0], 200)
        self.assertEqual(self.session.starts, 0)

    def test_bound_url_printed_before_callback_and_session_closed_on_interrupt(self):
        session = SessionProbe(self.journal)
        output = StringIO()
        observed = []

        def ready(url):
            self.assertIn('Open ' + url + ' in your browser.', output.getvalue())
            parsed = urlsplit(url)
            self.assertEqual((parsed.hostname, parsed.path), ('127.0.0.1', '/'))
            self.assertGreater(parsed.port, 0)
            with socket.create_connection((parsed.hostname, parsed.port), timeout=3):
                observed.append(url)
            self.assertEqual(session.starts, 0)

        with redirect_stdout(output), patch.object(transport.SpectatorServer, 'serve_forever',
                                                  side_effect=KeyboardInterrupt):
            transport.serve(session, ready=ready)
        self.assertEqual(len(observed), 1)
        self.assertEqual(session.closes, 1)
        with self.assertRaises(ValueError):
            transport.SpectatorServer(session, host='0.0.0.0')


if __name__ == '__main__':
    unittest.main()
