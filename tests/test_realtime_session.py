import asyncio
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from parallax_relay.protocol import ROLES
from parallax_relay.realtime import session as driver
from parallax_relay.realtime.coordination import CoordinationStop
from parallax_relay.realtime.journal import replay
from parallax_relay.realtime.observations import observe
from parallax_relay.realtime.physics import DRIVE
from parallax_relay.realtime.settings import Settings, load_profile


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


class RealtimeSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name) / 'match'

    def session(self, **settings):
        config = Settings.offline().model_copy(update=settings)
        return driver.Session(self.out, 'reactive', config, paced=False)

    def test_live_session_requires_matching_named_limits_before_opening_its_run(self):
        profile = load_profile('dev-bridge-live-v1')
        changed = profile.settings.model_copy(update={'max_calls': profile.settings.max_calls + 1})
        with patch.object(driver, 'make_live_agents') as make_clients:
            with self.assertRaisesRegex(ValueError, 'profile'):
                driver.Session(self.out, 'live', changed, profile=profile)
            self.assertFalse(self.out.exists())
            equivalent = Settings.model_validate(profile.settings.model_dump())
            session = driver.Session(self.out, 'live', equivalent, profile=profile)
            self.assertEqual(session.status()['status'], 'idle')
            make_clients.assert_not_called()

    async def test_offline_transport_records_the_selected_adapter_for_each_role(self):
        settings = Settings.offline('test').model_copy(update={'max_windows': 1, 'window_ticks': 1})
        supplied_id = str(uuid4())
        session = await asyncio.to_thread(driver.Session, self.out, 'test', settings, paced=False, run_id=supplied_id)
        await session._run()
        self.assertEqual(session.result['stop_reason'], 'window_limit')
        self.assertEqual(session.result['run_id'], supplied_id)
        config = next(e['data'] for e in records(self.out / 'private.jsonl') if e['kind'] == 'configuration')
        expected = {r: {'source': 'offline_test_transport',
                        'provider': 'gemini' if r == 'FLUX' else 'openai',
                        'model': 'gemini-3.5-flash-lite' if r == 'FLUX' else 'gpt-6-luna'} for r in ROLES}
        self.assertEqual(config['players'], expected)
        public = records(self.out / 'events.jsonl')
        self.assertEqual({event['run_id'] for event in public}, {supplied_id})
        for kind in ('match', 'window_started'):
            self.assertEqual(next(e['sources'] for e in public if e['kind'] == kind), expected)
        private_kinds = [e['kind'] for e in records(self.out / 'private.jsonl')]
        self.assertEqual((private_kinds.count('attempt_started'), private_kinds.count('attempt')), (9, 9))
        self.assertFalse(any(e['kind'] in ('attempt_started', 'attempt') for e in public))

    async def test_frozen_run_seals_every_start_replays_hashes_and_returns_own_feedback(self):
        session = await asyncio.to_thread(self.session)
        original_emit = session.emit
        published = []
        path = self.out / 'result.json'

        def observe_publication(kind, **data):
            if kind == 'result':
                published.append(json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None)
            return original_emit(kind, **data)

        with patch.object(session, 'emit', side_effect=observe_publication):
            self.assertTrue(session.start())
            try:
                self.assertTrue(await asyncio.to_thread(session._done.wait, 30))
                result = session.wait()
            finally:
                session.close()
        self.assertEqual(published, [result])
        self.assertEqual(result['run_id'], json.loads((self.out / 'manifest.json').read_text(encoding='utf-8'))['run_id'])
        self.assertEqual(result['stop_reason'], 'checkpoint')
        self.assertTrue(result['completed'])
        self.assertTrue(2 <= result['window'] <= 4)

        public = records(self.out / 'events.jsonl')
        self.assertEqual([e['run_id'] for e in public if e['kind'] == 'result'], [result['run_id']])
        starts = [row for row in public if row['kind'] == 'window_started']
        self.assertEqual([s['window'] for s in starts], list(range(1, result['window'] + 1)))
        for start in starts:
            window, sample = start['window'], start['sample_tick']
            self.assertEqual(start['tick'], sample + 1)
            self.assertEqual(start['starts'], dict.fromkeys(ROLES, sample + 1))
            self.assertEqual(start['observation_age_ticks'], 0)
            before = [e for e in public if e['window'] == window and e['seq'] < start['seq']]
            self.assertEqual({e['role'] for e in before if e['kind'] == 'observation'}, set(ROLES))
            ready = [e for e in before if e['kind'] == 'ready' and e['phase'] == 'commit']
            self.assertCountEqual([e['role'] for e in ready], ROLES)
            self.assertTrue(all(e['disposition'] == 'ready' and 'plans' not in e for e in ready))
            self.assertEqual({e['tick'] for e in before}, {sample})
        active = None
        by_tick = {s['tick']: s for s in starts}
        for record in records(self.out / 'simulation.jsonl'):
            if record['type'] == 'tick':
                active = record.get('programs', active)
                if record['tick'] in by_tick:
                    self.assertEqual(record['offset'], 0)
                    self.assertEqual(active, by_tick[record['tick']]['plans'])
        verified = replay(self.out)
        self.assertEqual(verified['run_id'], result['run_id'])
        self.assertEqual((verified['reason'], verified['ticks'], verified['state']),
                         ('checkpoint', result['tick'], session.world.snapshot()))

        views = {(entry['data']['sample_window'], entry['data']['role']): entry['data']['hud']
                 for entry in records(self.out / 'private.jsonl') if entry['kind'] == 'role_observation'}
        for role, interaction in (('PYRA', 'vented'), ('FLUX', 'rerouted')):
            self.assertEqual(views[1, role]['your_feedback']['recent_consequences'], [])
            feedback = views[2, role]['your_feedback']['recent_consequences']
            self.assertIn((1, interaction), [(e['tick'], e['kind']) for e in feedback])
            for teammate in set(ROLES) - {role}:
                other = views[2, teammate]['your_feedback']['recent_consequences']
                self.assertNotIn(interaction, [e['kind'] for e in other])

    async def test_expired_run_opens_no_new_observation_or_attempt(self):
        session = await asyncio.to_thread(self.session)
        with patch.object(driver, 'observe', wraps=observe) as sampled:
            with self.assertRaises(CoordinationStop) as stop:
                await session._play_physics(time.monotonic() - 1)
        self.assertEqual(stop.exception.reason, 'time_limit')
        sampled.assert_not_called()
        self.assertEqual((session.window, session.world.tick, session._budget.calls_started), (0, 0, 0))
        self.assertEqual(list((self.out / 'feeds').iterdir()), [])
        self.assertFalse(any(e['kind'] in ('observation', 'phase_open', 'window_started')
                             for e in session.events(0)['events']))

    async def test_continue_clock_recovers_multiple_due_ticks_after_one_delayed_wake(self):
        session = await asyncio.to_thread(self.session, clock_mode='continue')
        window = session.window = 1
        samples = {r: observe(session.world, r, window, session.settings) for r in ROLES}
        start_x = session.world.robots['SPECTRA'].x
        programs = {r: [] for r in ROLES}
        programs['SPECTRA'] = [{'kind': 'RUN', 'direction': 1, 'ticks': 1, 'jump_at': 0}]
        gate = asyncio.Event()
        period = 1 / session.settings.tick_rate
        clock = SimpleNamespace(now=10.0)
        waits, yields = [], []

        async def coordinate(observations, _window, _deadline):
            self.assertEqual(observations, samples)
            await gate.wait()
            return programs, []

        async def delayed_wake(tasks, *, timeout):
            waits.append(timeout)
            clock.now += 12.5 * period
            gate.set()
            return await asyncio.wait(tasks)

        async def yield_to_other_tasks(delay):
            self.assertEqual(delay, 0)
            yields.append(session.world.tick)
            # Draining the existing backlog costs time after the intake has already closed.
            clock.now += 2 * period
            await asyncio.sleep(0)

        scheduler = SimpleNamespace(create_task=asyncio.create_task, wait=delayed_wake,
                                    sleep=yield_to_other_tasks, CancelledError=asyncio.CancelledError)
        with (patch.object(driver, 'asyncio', scheduler),
              patch.object(driver, 'time', SimpleNamespace(monotonic=lambda: clock.now))):
            sealed, _ = await session._coordinate(SimpleNamespace(coordinate=coordinate), samples, window, 30)
        self.assertEqual(len(waits), 1)
        self.assertAlmostEqual(waits[0], period)
        self.assertTrue(any(0 < tick < 12 for tick in yields), 'The host must yield during catch-up')
        self.assertEqual(session.world.tick, 12)
        self.assertEqual(session.world.robots['SPECTRA'].x, start_x)
        self.assertEqual(samples['SPECTRA'].hud['sample_tick'], 0)
        before = [e for e in records(self.out / 'simulation.jsonl') if e['type'] == 'tick']
        self.assertEqual([e['tick'] for e in before], list(range(1, 13)))
        self.assertEqual(before[0]['programs'], dict.fromkeys(ROLES, []))
        self.assertEqual(len({e['programs_hash'] for e in before}), 1)
        pacing = [e['data'] for e in records(self.out / 'private.jsonl') if e['kind'] == 'pacing']
        self.assertEqual([(p['period'], p['ticks']) for p in pacing], [('discussion', 12)])
        self.assertGreater(pacing[0]['max_lag_seconds'], 11 * period)
        self.assertFalse(any(e['kind'] == 'window_started' for e in session.events(0)['events']))
        session._step(sealed, 0, release=dict.fromkeys(ROLES, 'ok'), sample_tick=0)
        start = next(e for e in session.events(0)['events'] if e['kind'] == 'window_started')
        self.assertEqual((start['tick'], start['observation_age_ticks']), (13, 12))
        self.assertEqual(start['starts'], dict.fromkeys(ROLES, 13))
        self.assertEqual(session.world.robots['SPECTRA'].x, start_x + DRIVE)

    async def test_failed_result_replacement_reports_local_error_without_public_terminal_result(self):
        session = await asyncio.to_thread(self.session, max_windows=1, window_ticks=1)
        # A directory at the final pathname produces a real replace failure on every supported OS.
        (self.out / 'result.json').mkdir()
        await session._run()
        self.assertEqual(session.result['stop_reason'], 'local_error')
        self.assertEqual(session.result['simulation_stop'], 'window_limit')
        self.assertFalse(session.result['completed'])
        self.assertTrue((self.out / 'result.json').is_dir())
        self.assertFalse(any(e['kind'] == 'result' for e in session.events(0)['events']))
        self.assertFalse(any(e['kind'] == 'result' for e in records(self.out / 'events.jsonl')))
        finish = records(self.out / 'simulation.jsonl')[-1]
        self.assertEqual((finish['type'], finish['tick'], finish['reason']), ('finish', 1, 'window_limit'))

    async def test_result_event_write_failure_retains_the_durable_win_and_rewrites_run_outcome(self):
        session = await asyncio.to_thread(self.session)
        emit = session.journal.emit
        path = self.out / 'result.json'
        first = []

        def fail_terminal_event(kind, **data):
            if kind == 'result':
                first.append(json.loads(path.read_text(encoding='utf-8')))
                raise OSError('terminal event write failed')
            return emit(kind, **data)

        with patch.object(session.journal, 'emit', side_effect=fail_terminal_event):
            await session._run()
        self.assertEqual([r['stop_reason'] for r in first], ['checkpoint'])
        self.assertTrue(first[0]['completed'])
        self.assertTrue(session.result['completed'])
        self.assertTrue(session.result['recording_error'])
        self.assertEqual((session.result['stop_reason'], session.result['simulation_stop']), ('local_error', 'checkpoint'))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), session.result)
        self.assertFalse(any(e['kind'] == 'result' for e in records(self.out / 'events.jsonl')))
        verified = replay(self.out)
        self.assertTrue(verified['state']['completed'])
        self.assertEqual((verified['reason'], verified['ticks'], verified['run_id']),
                         ('checkpoint', session.result['tick'], session.result['run_id']))

    async def test_gameplay_completion_tracks_whether_the_winning_tick_was_durable(self):
        for stored in (False, True):
            with self.subTest(winning_tick_stored=stored):
                out = self.out.parent / ('after-winning-tick' if stored else 'before-winning-tick')
                session = await asyncio.to_thread(driver.Session, out, 'reactive', Settings.offline(), paced=False)
                failures = []
                if stored:
                    emit = session.emit

                    def fail_checkpoint(kind, **data):
                        if kind == 'checkpoint' and data['world']['completed']:
                            failures.append(session.world.tick)
                            raise OSError('failed after persisting the winning tick')
                        return emit(kind, **data)

                    fault = patch.object(session, 'emit', side_effect=fail_checkpoint)
                else:
                    record_tick = session.journal.record_tick

                    def fail_tick(world, programs, offset):
                        if world.completed:
                            failures.append(world.tick)
                            raise OSError('failed before persisting the winning tick')
                        return record_tick(world, programs, offset)

                    fault = patch.object(session.journal, 'record_tick', side_effect=fail_tick)
                with fault:
                    await session._run()
                self.assertEqual(failures, [session.world.tick])
                self.assertTrue(session.world.completed)
                self.assertEqual(session.result['stop_reason'], 'local_error')
                self.assertEqual(session.result['completed'], stored)
                verified = replay(out)
                self.assertEqual(verified['state']['completed'], stored)
                self.assertEqual(verified['ticks'], session.world.tick if stored else session.world.tick - 1)
                self.assertEqual(verified['ticks'], session.result['tick'])
