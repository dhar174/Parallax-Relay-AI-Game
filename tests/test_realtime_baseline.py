import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import MatchExecutionError, run_match
from parallax_relay.protocol import ModelReply, ROLES
from parallax_relay.realtime.baseline import run_baseline
from parallax_relay.realtime.session import Session
from parallax_relay.realtime.settings import Settings
from parallax_relay.state import initial_world, public_events


class Stream:
    def __init__(self):
        self.events = []
        self.feeds = {}

    def emit(self, kind, **fields):
        self.events.append(dict(kind=kind, **fields))

    def store_feed(self, role, window, png):
        key = (role, window)
        if key in self.feeds:
            raise AssertionError(f'Duplicate feed for {key}')
        self.feeds[key] = png


class BaselineStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_discrete_states_feeds_dialogue_and_actions_match_native_game(self):
        native_inputs = []
        streamed_inputs = []
        respond = ScriptedAgent.respond

        def capture(sink):
            async def respond_and_capture(agent, request):
                sink.append(request)
                return await respond(agent, request)
            return respond_and_capture

        with patch.object(ScriptedAgent, 'respond', capture(native_inputs)):
            native = await run_match({r: ScriptedAgent(r) for r in ROLES})
        stream = Stream()
        with patch.object(ScriptedAgent, 'respond', capture(streamed_inputs)):
            result = await run_baseline(stream, Settings.offline('baseline'), paced=False)

        self.assertEqual(result, ('victory', True))
        self.assertEqual(len(native_inputs), 63)
        self.assertEqual(streamed_inputs, native_inputs)
        self.assertEqual(stream.feeds, {(r.role, r.turn + 1): r.observation.image_png
                                        for r in native_inputs})
        announcements = [(e['role'], e['window'], e['tick']) for e in stream.events
                         if e['kind'] == 'observation']
        self.assertEqual(announcements, [(r, w, w - 1) for w in range(1, 8) for r in ROLES])
        states = [e for e in stream.events if e['kind'] == 'state']
        snapshots = [initial_world().snapshot(), *(row['state_after'] for row in native.records)]
        self.assertEqual([e['tick'] for e in states], list(range(8)))
        for event, original in zip(states, snapshots, strict=True):
            world = event['world']
            self.assertEqual(world['tick'], original['turn'])
            self.assertEqual(world['energy'], original['energy'])
            self.assertEqual(world['bridge_powered'], original['bridge_extended'])
            self.assertEqual(world['heat'], original['motor_heat'])
            for role, body in world['robots'].items():
                self.assertEqual((body['x'], body['y'], body['pose']),
                                 (256 * original['robots'][role]['x'], 0, 'idle'))
        self.assertTrue(states[-1]['world']['completed'])
        self.assertEqual(states[-1]['world']['energy'], 5)
        checkpoints = [e for e in stream.events if e['kind'] == 'checkpoint']
        self.assertEqual([e['tick'] for e in checkpoints], list(range(1, 8)))
        self.assertEqual([e['world'] for e in checkpoints], [e['world'] for e in states[1:]])
        expectations = [(p['turn'] + 1, p['phase'], m['role'], m['text'])
                        for p in native.phases for m in p.get('messages', []) if m['text']]
        self.assertEqual([(e['window'], e['phase'], e['role'], e['text']) for e in stream.events
                          if e['kind'] == 'dialogue'], expectations)
        self.assertEqual([e['text'] for e in stream.events if e['kind'] == 'consequence'],
                         [s for row in native.records for s in public_events(row['events'])])

        for row in native.records:
            turn = row['turn']
            releases = [e for e in stream.events if e['kind'] == 'window_started' and e['window'] == turn]
            self.assertEqual(len(releases), 1)
            self.assertEqual((releases[0]['tick'], releases[0]['start_tick']), (turn, turn))
            self.assertEqual(releases[0]['plans'], {r: [row['sealed_actions'][r]] for r in ROLES})
            self.assertEqual(releases[0]['starts'], dict.fromkeys(ROLES, turn))
            self.assertEqual(releases[0]['dispositions'], dict.fromkeys(ROLES, 'ok'))
            self.assertEqual(releases[0]['sources'], {r: {'source': 'scripted_fixture'} for r in ROLES})
        public_json = json.dumps(stream.events)
        self.assertNotIn('Next plan index', public_json)
        self.assertNotIn('your_private_goal', public_json)

    async def test_watch_first_ready_before_other_commits_and_tile_release(self):
        stream = Stream()
        first_ready = asyncio.Event()
        remaining_slots = asyncio.Event()
        emit = stream.emit
        respond = ScriptedAgent.respond

        def observe(kind, **fields):
            emit(kind, **fields)
            if kind == 'ready' and fields['window'] == 1 and fields['role'] == 'SPECTRA':
                first_ready.set()

        async def staggered(agent, request):
            if request.turn == 0 and request.phase == 'commit' and request.role != 'SPECTRA':
                await remaining_slots.wait()
            return await respond(agent, request)

        stream.emit = observe
        with patch.object(ScriptedAgent, 'respond', staggered):
            match = asyncio.create_task(run_baseline(stream, Settings.offline('baseline'), paced=False))
            try:
                await asyncio.wait_for(first_ready.wait(), timeout=5)
                ready = [e for e in stream.events if e['kind'] == 'ready']
                self.assertEqual(len(ready), 1)
                self.assertEqual((ready[0]['phase'], ready[0]['role'], ready[0]['disposition']),
                                 ('commit', 'SPECTRA', 'ready'))
                self.assertFalse({'actions', 'plans', 'notes', 'text'} & ready[0].keys())
                self.assertEqual([e['tick'] for e in stream.events if e['kind'] == 'state'], [0])
                self.assertFalse(any(e['kind'] == 'window_started' for e in stream.events))
                self.assertEqual([e['phase'] for e in stream.events if e['kind'] == 'phase_open'],
                                 ['broadcast', 'negotiate', 'commit'])
            finally:
                remaining_slots.set()
                await asyncio.wait_for(match, timeout=15)
        kinds = [e['kind'] for e in stream.events if e.get('window') == 1]
        self.assertEqual(kinds.count('ready'), 3)
        start = kinds.index('window_started')
        self.assertLess(max(i for i, kind in enumerate(kinds) if kind == 'ready'), start)
        self.assertTrue(all(i > start for i, kind in enumerate(kinds) if kind == 'consequence'))

    async def test_retries_emit_one_final_disposition_per_role_without_reply_contents(self):
        events = []
        attempts = []
        respond = ScriptedAgent.respond

        async def mixed(agent, request):
            if request.phase == 'commit':
                attempts.append(request.role)
                if request.role == 'PYRA':
                    return ModelReply('', status='refusal')
                if request.role == 'FLUX' and attempts.count('FLUX') == 1:
                    return ModelReply('private malformed bytes')
            return await respond(agent, request)

        with patch.object(ScriptedAgent, 'respond', mixed):
            result = await run_match({r: ScriptedAgent(r) for r in ROLES},
                                     MatchSettings(max_turns=1, retry_delay_seconds=0),
                                     phase_event=events.append)
        self.assertEqual(attempts.count('FLUX'), 2)
        self.assertEqual(result.records[0]['sealed_actions']['SPECTRA']['steps'], 2)
        self.assertEqual([(e['role'], e['disposition']) for e in events if e['kind'] == 'ready'],
                         [('SPECTRA', 'ready'), ('PYRA', 'fallback'), ('FLUX', 'ready')])
        self.assertNotIn('private malformed bytes', json.dumps(events))
        self.assertNotIn('Next plan index', json.dumps(events))
        self.assertTrue(all({'actions', 'plans', 'notes', 'text'}.isdisjoint(e) for e in events))

    async def test_unresolved_turn_never_announces_a_start_or_checkpoint(self):
        stream = Stream()
        with patch('parallax_relay.orchestrator.resolve_turn', side_effect=RuntimeError('private diagnostic')):
            result = await run_baseline(stream, Settings.offline('baseline'), paced=False)
        self.assertEqual(result, ('internal_error', False))
        self.assertEqual([e['tick'] for e in stream.events if e['kind'] == 'state'], [0])
        self.assertFalse(any(e['kind'] in {'window_started', 'checkpoint'} for e in stream.events))
        self.assertNotIn('private diagnostic', json.dumps(stream.events))

    async def test_session_journals_measured_attempts_privately_and_finishes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'run'
            session = Session(out, 'baseline', Settings.offline('baseline'), paced=False)
            try:
                self.assertTrue(session.start())
                result = await asyncio.wait_for(asyncio.to_thread(session.wait), timeout=20)
            finally:
                session.close()
            self.assertEqual(result, json.loads((out / 'result.json').read_text(encoding='utf-8')))
            self.assertEqual((result['stop_reason'], result['tick'], result['window']), ('victory', 7, 7))
            events = session.events(0)['events']
            self.assertEqual(sum(e['kind'] == 'result' for e in events), 1)
            self.assertFalse(any(e['kind'] == 'attempt' for e in events))
            self.assertEqual(sum(e['kind'] == 'phase_closed' for e in events), 21)
            lines = (out / 'private.jsonl').read_text(encoding='utf-8').splitlines()
            private = [json.loads(line) for line in lines]
            attempts = [row['data'] for row in private if row['kind'] == 'attempt']
            self.assertEqual(len(attempts), 63)
            self.assertEqual(len({(a['window'], a['phase'], a['role']) for a in attempts}), 63)
            self.assertTrue(all(a['status'] == 'ok' and a['latency_seconds'] >= 0 for a in attempts))
            self.assertTrue(all(a['usage']['input_tokens'] == a['usage']['output_tokens'] == 0
                                for a in attempts))

    async def test_refused_reservation_and_callback_failure_leave_world_at_last_turn(self):
        agents = {r: ScriptedAgent(r) for r in ROLES}
        events = []
        result = await run_match(agents, MatchSettings(max_calls=1), phase_event=events.append)
        self.assertEqual((result.stop_reason, result.budget['calls_started'], events), ('call_budget', 0, []))

        def failed(event):
            raise OSError('private local path')

        with self.assertRaises(MatchExecutionError) as raised:
            await run_match(agents, phase_event=failed)
        result = raised.exception.result
        self.assertEqual((result.stop_reason, result.budget['calls_started'], result.world.turn),
                         ('local_error', 0, 0))
        self.assertEqual(result.budget['reserved_calls'], 0)
        self.assertNotIn('private local path', str(raised.exception))
