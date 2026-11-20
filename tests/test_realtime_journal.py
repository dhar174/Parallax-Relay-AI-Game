import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from parallax_relay.realtime.journal import Journal, POSE_CAPACITY, replay


class ToyWorld:
    def __init__(self):
        self.tick = 0
        self.height = 0
        self.velocity = 0

    def snapshot(self):
        return {'tick': self.tick, 'height': self.height, 'velocity': self.velocity}

    def replay_state(self):
        return self.snapshot()


def toy_step(world, programs, offset):
    if programs['SPECTRA'] and offset == 0:
        world.velocity = 4
    world.velocity -= 1
    world.height += world.velocity
    world.tick += 1


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'run'
        self.journal = Journal(self.out)

    def test_explicit_canonical_run_id_and_invalid_id_does_not_create_path(self):
        run_id = 'aabbccdd-0000-4000-8000-000000000001'
        out = Path(self.tmp.name) / 'explicit'
        j = Journal(out, run_id=run_id)
        self.assertEqual(j.run_id, run_id)
        self.assertEqual(json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['run_id'], run_id)
        for bad in ('bad', run_id.upper(), 17):
            invalid = Path(self.tmp.name) / ('invalid-' + str(bad))
            with self.assertRaises(ValueError):
                Journal(invalid, run_id=bad)
            self.assertFalse(invalid.exists())

    def test_public_cursor_private_and_feed_isolation(self):
        j = self.journal
        j.private('sealed', secret='not-public')
        original = {'speaker': 'SPECTRA', 'text': 'hello'}
        j.emit('dialogue', dialogue=original, tick=3, window=1)
        original['text'] = 'changed'
        j.emit('pose', x=8)
        all_events = j.events(0)
        self.assertEqual(all_events['cursor'], 2)
        self.assertEqual(all_events['events'][0]['dialogue']['text'], 'hello')
        self.assertNotIn('not-public', json.dumps(all_events))
        self.assertEqual([e['seq'] for e in j.events(1)['events']], [2])
        self.assertEqual(j.events(99)['events'], all_events['events'])
        self.assertTrue(j.events(99)['reset'])
        self.assertEqual(j.events(2)['events'], [])
        png = b'\x89PNG\r\n\x1a\nexample'
        j.store_feed('SPECTRA', 1, png)
        self.assertEqual(j.feed('SPECTRA', 1), png)
        self.assertIsNone(j.feed('PYRA', 1))
        with self.assertRaises(ValueError):
            j.feed('../secret', 1)
        with self.assertRaises(FileExistsError):
            Journal(self.out)

    def test_write_failure_never_publishes_and_poisons_journal(self):
        j = self.journal
        with patch('parallax_relay.realtime.journal.os.fsync', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                j.emit('pose', x=1)
        self.assertEqual(j.events()['events'], [])
        with self.assertRaises(RuntimeError):
            j.emit('pose', x=2)

    def test_record_replay_neutral_and_midair_stop_and_tampering(self):
        fake = types.SimpleNamespace(initial_world=ToyWorld, step=toy_step)
        world = ToyWorld()
        j = self.journal
        j.record_initial(world)
        jump = {'SPECTRA': [{'kind': 'JUMP'}], 'PYRA': [], 'FLUX': []}
        neutral = {'SPECTRA': [], 'PYRA': [], 'FLUX': []}
        toy_step(world, jump, 0)
        j.record_tick(world, jump, 0)
        toy_step(world, neutral, 1)
        j.record_tick(world, neutral, 1)
        self.assertGreater(world.height, 0)
        j.finish('stopped')
        with patch.dict('sys.modules', {'parallax_relay.realtime.physics': fake}):
            result = replay(self.out)
            self.assertEqual(result['state'], world.snapshot())
            self.assertEqual(result['reason'], 'stopped')
            path = self.out / 'simulation.jsonl'
            lines = path.read_text(encoding='utf-8').splitlines()
            item = json.loads(lines[2])
            item['state_hash'] = '0' * 64
            lines[2] = json.dumps(item)
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                replay(self.out)

    def test_partial_recording_rejected(self):
        world = ToyWorld()
        self.journal.record_initial(world)
        fake = types.SimpleNamespace(initial_world=ToyWorld, step=toy_step)
        with patch.dict('sys.modules', {'parallax_relay.realtime.physics': fake}):
            with self.assertRaisesRegex(ValueError, 'finish marker'):
                replay(self.out)

    def test_foreign_simulation_cannot_claim_another_manifest(self):
        world = ToyWorld()
        self.journal.record_initial(world)
        self.journal.finish('stopped')
        other = Path(self.tmp.name) / 'other'
        Journal(other)
        (other / 'simulation.jsonl').write_bytes((self.out / 'simulation.jsonl').read_bytes())
        self.assertEqual((other / 'simulation.jsonl').read_bytes(), (self.out / 'simulation.jsonl').read_bytes())
        fake = types.SimpleNamespace(initial_world=ToyWorld, step=toy_step)
        with patch.dict('sys.modules', {'parallax_relay.realtime.physics': fake}):
            with self.assertRaisesRegex(ValueError, 'identity'):
                replay(other)

    def test_bound_private_and_result_and_legacy_identity(self):
        world = ToyWorld()
        j = self.journal
        j.private('configuration', settings={'clock_mode': 'freeze'})
        j.record_initial(world)
        j.finish('checkpoint')
        result_path = self.out / 'result.json'
        result_path.write_text(json.dumps({'run_id': j.run_id, 'stop_reason': 'local_error',
                                           'completed': True}), encoding='utf-8')
        self.assertEqual(json.loads(result_path.read_text(encoding='utf-8'))['run_id'], j.run_id)
        fake = types.SimpleNamespace(initial_world=ToyWorld, step=toy_step)
        with patch.dict('sys.modules', {'parallax_relay.realtime.physics': fake}):
            result = replay(self.out)
            self.assertEqual(result['identity_status'], 'bound')
            self.assertEqual(result['run_id'], j.run_id)
            self.assertEqual(result['record_version'], 2)
            self.assertEqual(result['reason'], 'checkpoint')
            result_path.write_text(json.dumps({'run_id': 'foreign'}), encoding='utf-8')
            self.assertEqual(json.loads(result_path.read_text(encoding='utf-8'))['run_id'], 'foreign')
            with self.assertRaisesRegex(ValueError, 'result identity'):
                replay(self.out)
            result_path.unlink()
            self.assertFalse(result_path.exists())
            private_path = self.out / 'private.jsonl'
            private_row = json.loads(private_path.read_text(encoding='utf-8'))
            private_row['run_id'] = 'foreign'
            private_path.write_text(json.dumps(private_row) + '\n', encoding='utf-8')
            self.assertEqual(json.loads(private_path.read_text(encoding='utf-8'))['run_id'], 'foreign')
            with self.assertRaisesRegex(ValueError, 'private journal identity'):
                replay(self.out)
            # Old records did not bind a run, so their displayed identity is unknown.
            manifest_path = self.out / 'manifest.json'
            manifest_path.write_text(json.dumps({'version': 1, 'run_id': j.run_id}), encoding='utf-8')
            self.assertEqual(json.loads(manifest_path.read_text(encoding='utf-8'))['version'], 1)
            simulation_path = self.out / 'simulation.jsonl'
            rows = [json.loads(line) for line in simulation_path.read_text(encoding='utf-8').splitlines()]
            for row in rows:
                row.pop('version')
                row.pop('run_id')
            simulation_path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
            self.assertNotIn('run_id', json.loads(simulation_path.read_text(encoding='utf-8').splitlines()[0]))
            legacy = replay(self.out)
            self.assertEqual(legacy['identity_status'], 'unknown')
            self.assertIsNone(legacy['run_id'])
            self.assertEqual(legacy['declared_run_id'], j.run_id)

    def test_real_physics_replay_with_neutral_inference_and_midair_stop(self):
        from parallax_relay.realtime.physics import initial_world, step

        world = initial_world()
        self.journal.record_initial(world)
        jump = {'SPECTRA': [{'kind': 'RUN', 'direction': 1, 'ticks': 10, 'jump_at': 0}],
                'PYRA': [], 'FLUX': []}
        neutral = {'SPECTRA': [], 'PYRA': [], 'FLUX': []}
        for offset in range(4):
            step(world, jump, offset)
            self.journal.record_tick(world, jump, offset)
        for offset in range(4, 7):
            step(world, neutral, offset)
            self.journal.record_tick(world, neutral, offset)
        self.assertFalse(world.robots['SPECTRA'].grounded)
        self.journal.finish('midair_stop')
        result = replay(self.out)
        self.assertEqual(result['ticks'], 7)
        self.assertEqual(result['state'], world.snapshot())

    def test_paged_recovery_retains_transcript_contacts_and_latest_pose(self):
        j = self.journal
        j.private('sealed', secret='PRIVATE-SENTINEL')
        with patch('parallax_relay.realtime.journal.os.fsync'):
            j.emit('match', mode='test')
            for n in range(1100):
                j.emit('state', tick=n, world={'x': n})
                if n % 3 == 0:
                    j.emit('dialogue', role='PYRA', text=f'message-{n}')
                if n in (10, 450):
                    j.emit('consequence', event_kind='landed', tick=n)
                if n == 1090:
                    j.emit('observation', role='SPECTRA', window=4)
                    j.emit('ready', role='PYRA', phase='commit', window=4)
            j.emit('result', completed=True, window=4)
        self.assertLessEqual(len(j._poses), POSE_CAPACITY)
        cursor = 0
        rows = []
        page_count = 0
        while True:
            page = j.events(cursor, limit=37)
            page_count += 1
            self.assertLessEqual(len(page['events']), 37)
            self.assertTrue(page['reset'] or cursor >= j._dropped_pose_through)
            rows.extend(page['events'])
            if not page['has_more']:
                break
            self.assertGreater(page['cursor'], cursor)
            cursor = page['cursor']
        self.assertGreater(page_count, 1)
        seqs = [row['seq'] for row in rows]
        self.assertEqual(seqs, sorted(set(seqs)))
        self.assertEqual(len([row for row in rows if row['kind'] == 'dialogue']), 367)
        self.assertEqual([row['world']['x'] for row in rows if row['kind'] == 'state'][-1], 1099)
        self.assertTrue({10, 450} <= {row['world']['x'] for row in rows if row['kind'] == 'state'})
        self.assertEqual(len([row for row in rows if row['kind'] == 'consequence']), 2)
        self.assertEqual(next(row for row in rows if row['kind'] == 'observation')['window'], 4)
        self.assertEqual(rows[-1]['kind'], 'result')
        self.assertNotIn('PRIVATE-SENTINEL', json.dumps(rows))
        self.assertEqual(j.events(page['cursor'])['events'], [])
        stale = j.events(1, limit=37)
        self.assertTrue(stale['reset'])
        self.assertTrue(stale['has_more'])
        self.assertLess(stale['cursor'], stale['watermark'])

    def test_slow_page_serialization_does_not_hold_writer_lock(self):
        j = self.journal
        j.emit('state', world={'x': 1})
        started, release, written = threading.Event(), threading.Event(), threading.Event()
        from parallax_relay.realtime import journal as module
        real_detach = module._detach

        def slow_detach(value):
            if isinstance(value, list):
                started.set()
                if not release.wait(5):
                    raise RuntimeError('test timed out')
            return real_detach(value)

        result = []
        with patch.object(module, '_detach', side_effect=slow_detach):
            reader = threading.Thread(target=lambda: result.append(j.events(0)))
            reader.start()
            self.assertTrue(started.wait(2))
            writer = threading.Thread(target=lambda: (j.emit('dialogue', text='new'), written.set()))
            writer.start()
            try:
                self.assertTrue(written.wait(2), 'reader blocked writer during serialization')
            finally:
                release.set()
                reader.join(5)
                writer.join(5)
        self.assertEqual(result[0]['watermark'], 1)
        self.assertEqual([row['kind'] for row in j.events(result[0]['cursor'])['events']], ['dialogue'])


if __name__ == '__main__':
    unittest.main()
