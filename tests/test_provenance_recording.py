"""Provenance must survive the real driver's checkpoint and recovery paths."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.orchestrator import MatchExecutionError, run_match
from parallax_relay.protocol import ROLES
from parallax_relay.recording import Recorder


class ProvenanceRecordingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / 'custom-output-name'

    def agents(self): return {r: ScriptedAgent(r) for r in ROLES}

    def saved(self):
        return json.loads((self.out / 'manifest.json').read_text(encoding='utf-8'))

    async def test_programmatic_settings_prices_timing_and_embedded_manifest(self):
        recorder = Recorder(self.out, {'mode': 'mock', 'settings': {'max_turns': 12}})
        result = await run_match(self.agents(), MatchSettings(max_turns=1),
                                 rates={r: Rates(input_per_million=1, output_per_million=2) for r in ROLES},
                                 recorder=recorder)
        manifest = self.saved()
        self.assertIn('provenance', manifest, 'Recorded runs have no execution identity')
        data = manifest['provenance']
        self.assertEqual(data['execution']['value']['settings']['max_turns'], 1)
        self.assertEqual(manifest['settings']['max_turns'], 1)
        self.assertEqual(data['execution']['value']['pricing']['SPECTRA']['output_per_million'], 2)
        self.assertEqual(data['players']['SPECTRA']['provider'], 'unknown')
        self.assertEqual(data['lifecycle']['stage'], 'ended')
        for field in ('created_at', 'started_at', 'ended_at'):
            self.assertTrue(data['lifecycle'][field].endswith('Z'))
        self.assertGreaterEqual(data['lifecycle']['elapsed_seconds'], 0)
        self.assertEqual(data['lifecycle']['stop_reason'], 'turn_limit')
        self.assertEqual(result.summary()['schema_version'], 2)
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        embedded = json.loads(html.split('const DATA=', 1)[1].split(';\nconst $=', 1)[0])
        self.assertEqual(embedded['manifest'], manifest)

    async def test_start_write_error_recovers_before_any_calls(self):
        recorder = Recorder(self.out, {'mode': 'mock'})
        original = OSError('SECRET_SENTINEL')
        real = recorder._json
        def fail(filename, data):
            if filename == 'manifest.json' and data.get('provenance', {}).get('lifecycle', {}).get('stage') == 'running':
                raise original
            return real(filename, data)
        with patch.object(recorder, '_json', side_effect=fail):
            with self.assertRaises(MatchExecutionError) as ctx:
                await run_match(self.agents(), recorder=recorder)
        self.assertIs(ctx.exception.original_error, original)
        self.assertEqual(ctx.exception.operation, 'begin_match')
        self.assertEqual(ctx.exception.result.budget['calls_started'], 0)
        self.assertEqual(self.saved()['provenance']['lifecycle']['stop_reason'], 'local_error')
        self.assertNotIn('SECRET_SENTINEL', (self.out / 'index.html').read_text(encoding='utf-8'))

    async def test_manifest_failure_after_victory_preserves_end_times_and_original_outcome(self):
        recorder = Recorder(self.out, {'mode': 'mock'})
        real = recorder._json
        seen = []
        original = OSError('SECRET_SENTINEL')
        def fail_once(filename, data):
            if filename == 'manifest.json' and data.get('provenance', {}).get('lifecycle', {}).get('stage') == 'ended':
                seen.append(dict(data['provenance']['lifecycle']))
                if len(seen) == 1: raise original
            return real(filename, data)
        with patch.object(recorder, '_json', side_effect=fail_once):
            with self.assertRaises(MatchExecutionError) as ctx:
                await run_match(self.agents(), recorder=recorder)
        self.assertIs(ctx.exception.original_error, original)
        self.assertTrue(ctx.exception.result.world.win)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]['ended_at'], seen[1]['ended_at'])
        self.assertEqual(seen[0]['elapsed_seconds'], seen[1]['elapsed_seconds'])
        data = self.saved()['provenance']['lifecycle']
        self.assertEqual(data['execution_stop_reason'], 'victory')
        self.assertEqual(data['stop_reason'], 'local_error')

    async def test_cancelled_match_retains_provenance(self):
        started = asyncio.Event()
        class Slow(ScriptedAgent):
            async def respond(self, request):
                started.set()
                await asyncio.sleep(30)
        recorder = Recorder(self.out, {'mode': 'mock'})
        task = asyncio.create_task(run_match({r: Slow(r) for r in ROLES}, recorder=recorder))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertIn('provenance', self.saved())
        life = self.saved()['provenance']['lifecycle']
        self.assertEqual(life['stop_reason'], 'cancelled')
        self.assertEqual(life['stage'], 'ended')

    async def test_reusing_a_recorder_never_overwrites_prior_run(self):
        recorder = Recorder(self.out, {'mode': 'mock'})
        await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        saved = {p.name: p.read_bytes() for p in self.out.iterdir()}
        with self.assertRaises(ValueError):
            await run_match(self.agents(), recorder=recorder)
        self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, saved)

    async def test_external_result_does_not_invent_execution_context(self):
        result = await run_match(self.agents(), MatchSettings(max_turns=1))
        recorder = Recorder(self.out, {'mode': 'mock'})
        recorder.finish(result)
        self.assertIn('provenance', self.saved())
        data = self.saved()['provenance']
        self.assertIsNone(data['execution'])
        self.assertIsNone(data['lifecycle']['started_at'])
        self.assertIsNone(data['lifecycle']['ended_at'])
        self.assertEqual(data['lifecycle']['stage'], 'external_result')

    async def test_persistent_manifest_errors_remain_secondary_to_phase_error(self):
        recorder = Recorder(self.out, {'mode': 'mock'})
        original, secondary = OSError('SECRET_PRIMARY'), OSError('SECRET_SECONDARY')
        real = recorder._bytes
        attempts = []
        def write(name, data):
            if recorder.manifest['provenance']['lifecycle']['stage'] == 'ended':
                attempts.append(name)
                if name == 'manifest.json': raise secondary
            return real(name, data)
        with patch.object(recorder, 'phase', side_effect=original), patch.object(recorder, '_bytes', write):
            with self.assertRaises(MatchExecutionError) as ctx:
                await run_match(self.agents(), recorder=recorder)
        self.assertIs(ctx.exception.original_error, original)
        self.assertEqual(attempts.count('manifest.json'), 2)
        self.assertEqual(len(attempts), 16)
        self.assertEqual([error for op, error in ctx.exception.secondary_errors if op == 'manifest.json'],
                         [secondary, secondary])
        self.assertEqual(self.saved()['provenance']['lifecycle']['stage'], 'running')
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('SECRET_', html)
        self.assertIn('local_error', html)

    async def test_cancellation_survives_end_hook_error(self):
        started = asyncio.Event()
        class Slow(ScriptedAgent):
            async def respond(self, request):
                started.set(); await asyncio.sleep(30)
        recorder = Recorder(self.out, {'mode': 'mock'})
        error = OSError('SECRET_SENTINEL')
        with patch.object(recorder, 'end_match', side_effect=error):
            task = asyncio.create_task(run_match({r: Slow(r) for r in ROLES}, recorder=recorder))
            await started.wait(); task.cancel()
            with self.assertRaises(asyncio.CancelledError) as ctx: await task
        self.assertIn(('end_match', error), ctx.exception.secondary_errors)
        self.assertEqual(ctx.exception.result.stop_reason, 'cancelled')
        self.assertIsNone(self.saved()['provenance']['lifecycle']['ended_at'])
        self.assertNotIn('SECRET_SENTINEL', (self.out / 'index.html').read_text(encoding='utf-8'))

    async def test_classic_custom_recorder_needs_no_new_methods(self):
        class Classic:
            def begin_turn(self, *args): pass
            def call(self, *args): pass
            def phase(self, *args): pass
            def turn(self, *args): pass
            def finish(self, result): self.result = result
        recorder = Classic()
        result = await run_match(self.agents(), MatchSettings(max_turns=1), recorder=recorder)
        self.assertIs(recorder.result, result)
        self.assertEqual(result.world.turn, 1)
