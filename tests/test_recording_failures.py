import asyncio
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay import orchestrator as driver
from parallax_relay.agents import ScriptedAgent
from parallax_relay.protocol import ROLES
from parallax_relay.recording import Recorder


class RecordingFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_temp_writes_preserve_final_png_and_viewer(self):
        import traceback
        from parallax_relay.config import MatchSettings
        from parallax_relay.recording import RecordingFinalizationError
        result = await driver.run_match({r: ScriptedAgent(r) for r in ROLES},
                                        MatchSettings(max_turns=1))
        for filename in ('final_spectator.png', 'index.html'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'
                recorder = Recorder(out, {'mode': 'mock'})
                recorder.finish(result)
                target = out / filename
                original_bytes = target.read_bytes()
                original = OSError('SECRET_SENTINEL')
                real_write = Path.write_bytes

                def partial_write(path, data):
                    if path == target.with_suffix(target.suffix + '.tmp'):
                        real_write(path, data[:len(data) // 2])
                        raise original
                    return real_write(path, data)

                result.stop_reason = 'local_error'
                with patch.object(Path, 'write_bytes', partial_write):
                    with self.assertRaises(RecordingFinalizationError) as ctx:
                        recorder.finish(result)
                self.assertEqual(ctx.exception.failures, ((filename, original),))
                self.assertEqual(target.read_bytes(), original_bytes)
                self.assertEqual(recorder.viewer_ready, filename != 'index.html')
                self.assertNotIn('SECRET_SENTINEL', repr(ctx.exception))
                self.assertNotIn('SECRET_SENTINEL', ''.join(traceback.format_exception(ctx.exception)))
                for artifact in out.iterdir():
                    if artifact.suffix in ('.json', '.jsonl', '.html'):
                        self.assertNotIn('SECRET_SENTINEL', artifact.read_text())

    async def test_phase_failure_recovers_zero_turn_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            recorder = Recorder(out, {'mode': 'mock'})
            original = OSError('SECRET_SENTINEL')
            with patch.object(recorder, 'phase', side_effect=original):
                try:
                    await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder)
                except Exception as error:
                    self.assertEqual(type(error).__name__, 'MatchExecutionError')
                    self.assertIs(error.original_error, original)
                    self.assertEqual(error.result.world.turn, 0)
                    self.assertEqual(error.result.stop_reason, 'local_error')
                else:
                    self.fail('A recording failure must raise')
            summary = json.loads((out / 'result.json').read_text())
            self.assertEqual(summary['stop_reason'], 'local_error')
            self.assertEqual(summary['turns'], 0)
            self.assertTrue((out / 'index.html').is_file())

    async def test_write_boundaries_repair_logs_and_keep_resolved_checkpoint(self):
        for method, filename, turns in [('call', 'calls.jsonl', 0), ('phase', 'phases.jsonl', 0),
                                        ('turn', 'replay.jsonl', 1), ('begin_turn', None, 0)]:
            for timing in ('before', 'partial', 'after'):
                with self.subTest(method=method, timing=timing), tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
                    real = getattr(recorder, method)
                    original = OSError('SECRET_SENTINEL')
                    def fail(*args):
                        if timing == 'after': real(*args)
                        if timing == 'partial' and filename:
                            with (out / filename).open('a') as handle: handle.write('{partial')
                        raise original
                    with patch.object(recorder, method, side_effect=fail):
                        with self.assertRaises(driver.MatchExecutionError) as ctx:
                            await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder)
                    error = ctx.exception
                    self.assertIs(error.original_error, original)
                    self.assertEqual(error.result.world.turn, turns)
                    self.assertEqual(len(error.result.records), turns)
                    for filename, rows in [('calls.jsonl', error.result.calls),
                                           ('phases.jsonl', error.result.phases),
                                           ('replay.jsonl', error.result.records)]:
                        saved = [json.loads(line) for line in (out / filename).read_text().splitlines()]
                        self.assertEqual(saved, rows)
                    self.assertEqual(error.result.budget['calls_started'], len(error.result.calls))
                    state = json.loads((out / 'final_state.json').read_text())
                    self.assertEqual(state, error.result.world.snapshot())
                    self.assertEqual(json.loads((out / 'result.json').read_text()), error.result.summary())
                    data = json.loads((out / 'index.html').read_text().split('const DATA=', 1)[1].split(';\nconst $=', 1)[0])
                    self.assertEqual(data['records'], error.result.records)
                    self.assertEqual(data['result'], error.result.summary())
                    import traceback
                    self.assertNotIn('SECRET_SENTINEL', ''.join(traceback.format_exception(error)))
                    for file in out.iterdir():
                        if file.suffix in ('.json', '.jsonl', '.html'):
                            self.assertNotIn('SECRET_SENTINEL', file.read_text())

    async def test_progress_and_unexpected_driver_errors(self):
        for operation in ('progress', 'driver'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                recorder = Recorder(Path(tmp) / 'run', {'mode': 'mock'})
                original = RuntimeError('SECRET_SENTINEL')
                kwargs = {'progress': lambda record: (_ for _ in ()).throw(original)} if operation == 'progress' else {}
                with patch('parallax_relay.orchestrator.resolve_turn', side_effect=original) if operation == 'driver' else contextlib.nullcontext():
                    with self.assertRaises(driver.MatchExecutionError) as ctx:
                        await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder, **kwargs)
                self.assertIs(ctx.exception.original_error, original)
                self.assertEqual(ctx.exception.result.world.turn, 0)
                self.assertEqual(ctx.exception.result.stop_reason, 'internal_error' if operation == 'driver' else 'local_error')

    async def test_finalization_artifacts_are_independent_and_bounded(self):
        from parallax_relay.config import MatchSettings
        names = ['calls.jsonl', 'phases.jsonl', 'replay.jsonl', 'result.json',
                 'final_state.json', 'final_spectator.png', 'index.html']
        for failed in names:
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
                real = recorder._bytes; attempts = []
                original = OSError('SECRET_SENTINEL')
                def write(name, data):
                    attempts.append(name)
                    if name == failed: raise original
                    return real(name, data)
                with patch.object(recorder, '_bytes', side_effect=write):
                    with self.assertRaises(driver.MatchExecutionError) as ctx:
                        await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, MatchSettings(max_turns=1), recorder=recorder)
                self.assertIs(ctx.exception.original_error, original)
                self.assertEqual(attempts, names * 2)
                self.assertEqual(ctx.exception.result.world.turn, 1)
                for name in set(names) - {failed}: self.assertTrue((out / name).exists())
                if failed != 'result.json':
                    self.assertEqual(json.loads((out / 'result.json').read_text())['stop_reason'], 'local_error')
                self.assertEqual(recorder.viewer_ready, failed != 'index.html')

    async def test_transient_finish_failure_after_victory_keeps_game_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
            real = recorder._bytes; original = OSError('SECRET_SENTINEL'); failed = False
            def write(name, data):
                nonlocal failed
                if name == 'index.html' and not failed:
                    failed = True
                    raise original
                real(name, data)
            with patch.object(recorder, '_bytes', side_effect=write):
                with self.assertRaises(driver.MatchExecutionError) as ctx:
                    await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder)
            self.assertEqual(ctx.exception.original_stop_reason, 'victory')
            summary = ctx.exception.result.summary()
            self.assertTrue(summary['completed']); self.assertTrue(summary['win'])
            self.assertEqual(summary['scores'], dict.fromkeys(ROLES, 100))
            self.assertEqual(summary['stop_reason'], 'local_error')
            self.assertTrue(recorder.viewer_ready)

    async def test_original_failure_survives_secondary_finalization_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = Recorder(Path(tmp) / 'run', {'mode': 'mock'})
            original, secondary = OSError('PRIMARY_SECRET'), RuntimeError('SECONDARY_SECRET')
            with patch.object(recorder, 'phase', side_effect=original), patch.object(recorder, 'finish', side_effect=secondary) as finish:
                with self.assertRaises(driver.MatchExecutionError) as ctx:
                    await driver.run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder)
            self.assertIs(ctx.exception.original_error, original)
            self.assertEqual(finish.call_count, 2)
            self.assertTrue(all(e is secondary for _, e in ctx.exception.secondary_errors))

    async def test_cancellation_survives_recording_and_finish_errors(self):
        started = asyncio.Event()
        class Slow(ScriptedAgent):
            async def respond(self, request):
                started.set(); await asyncio.sleep(30)
        with tempfile.TemporaryDirectory() as tmp:
            recorder = Recorder(Path(tmp) / 'run', {'mode': 'mock'})
            with patch.object(recorder, 'call', side_effect=OSError('SECRET')), patch.object(recorder, 'finish', side_effect=OSError('SECONDARY')) as finish:
                task = asyncio.create_task(driver.run_match({r: Slow(r) for r in ROLES}, recorder=recorder))
                await started.wait(); task.cancel()
                with self.assertRaises(asyncio.CancelledError) as ctx: await task
            self.assertEqual(ctx.exception.result.stop_reason, 'cancelled')
            self.assertEqual(ctx.exception.result.world.turn, 0)
            self.assertEqual(finish.call_count, 2)
            self.assertTrue(ctx.exception.secondary_errors)


class RecoveryCLITests(unittest.TestCase):
    def test_cli_reports_safe_failures_and_only_current_replays(self):
        import io
        from parallax_relay.play import main
        for stage in ('phase', 'viewer', 'driver'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
                original = OSError('SECRET_SENTINEL')
                real = recorder._bytes
                def write(name, data):
                    if name == 'index.html': raise original
                    real(name, data)
                fault = (patch.object(recorder, 'phase', side_effect=original) if stage == 'phase'
                         else patch.object(recorder, '_bytes', side_effect=write) if stage == 'viewer'
                         else patch('parallax_relay.orchestrator.resolve_turn', side_effect=original))
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch('parallax_relay.play.Recorder', return_value=recorder), fault, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(['--mock', '--quiet', '--max-turns', '1', '--out', str(out)])
                self.assertEqual(code, 3 if stage == 'driver' else 2)
                summary = json.loads(stdout.getvalue().split('\nReplay:', 1)[0])
                self.assertEqual(summary['stop_reason'], 'internal_error' if stage == 'driver' else 'local_error')
                self.assertEqual('Replay:' in stdout.getvalue(), stage != 'viewer')
                self.assertNotIn('SECRET_SENTINEL', stdout.getvalue() + stderr.getvalue())
                self.assertNotIn('Traceback', stderr.getvalue())
                if stage == 'viewer': self.assertIn('Partial output:', stderr.getvalue())

    def test_client_shutdown_timeout_does_not_mask_recording_failure(self):
        import io
        from parallax_relay.play import main
        closed = []
        class SlowClose(ScriptedAgent):
            async def close(self):
                try: await asyncio.sleep(30)
                finally: closed.append(self.role)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch('parallax_relay.play.ScriptedAgent', SlowClose), \
                 patch('parallax_relay.play.Recorder', return_value=recorder), \
                 patch('parallax_relay.play.CLEANUP_TIMEOUT_SECONDS', 0.01), \
                 patch.object(recorder, 'phase', side_effect=OSError('SECRET_SENTINEL')), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(['--mock', '--quiet', '--out', str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(sorted(closed), sorted(ROLES))
            self.assertIn('Provider cleanup incomplete.', stderr.getvalue())
            self.assertNotIn('SECRET_SENTINEL', stderr.getvalue())


class PhaseCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_write_failure_drains_siblings_and_releases_budget(self):
        from parallax_relay.budget import Budget
        from parallax_relay.config import MatchSettings
        ready = asyncio.Event(); started = []; cancelled = []
        class Gated(ScriptedAgent):
            async def respond(self, request):
                started.append(self.role)
                if len(started) == 3: ready.set()
                await ready.wait()
                if self.role == 'SPECTRA': return await super().respond(request)
                try: await asyncio.sleep(30)
                finally: cancelled.append(self.role)
        budget = Budget(MatchSettings(), {})
        with tempfile.TemporaryDirectory() as tmp:
            recorder = Recorder(Path(tmp) / 'run', {'mode': 'mock'})
            with patch('parallax_relay.orchestrator.Budget', return_value=budget), \
                 patch.object(recorder, 'call', side_effect=OSError('SECRET_SENTINEL')):
                with self.assertRaises(driver.MatchExecutionError) as ctx:
                    await driver.run_match({r: Gated(r) for r in ROLES}, recorder=recorder)
            self.assertEqual(sorted(cancelled), ['FLUX', 'PYRA'])
            self.assertEqual(budget.calls_started, 3)
            self.assertEqual(len(ctx.exception.result.calls), 3)
            self.assertEqual(budget.reserved_calls, 0)
            self.assertEqual(budget.reserved_usd, 0)
            self.assertEqual(ctx.exception.result.world.turn, 0)

    async def test_fresh_cancellation_during_failed_match_cleanup_propagates(self):
        import io
        from parallax_relay.config import load_config
        from parallax_relay import play
        closing = asyncio.Event()
        class SlowClose(ScriptedAgent):
            async def close(self):
                closing.set()
                await asyncio.sleep(30)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'; recorder = Recorder(out, {'mode': 'mock'})
            cfg = load_config(Path('configs/three_models.toml'))
            args = play.parser().parse_args(['--mock', '--quiet', '--out', str(out)])
            with patch('parallax_relay.play.ScriptedAgent', SlowClose), \
                 patch('parallax_relay.play.Recorder', return_value=recorder), \
                 patch.object(recorder, 'phase', side_effect=OSError('SECRET_SENTINEL')), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                task = asyncio.create_task(play._run(args, cfg, cfg.match, {}))
                await closing.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError) as ctx:
                    await task
            self.assertEqual(ctx.exception.result.stop_reason, 'local_error')
            self.assertTrue(any(isinstance(error, driver.MatchExecutionError)
                                for _, error in ctx.exception.secondary_errors))
