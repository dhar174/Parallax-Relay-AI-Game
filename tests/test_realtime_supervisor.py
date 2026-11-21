"""Outer stop and durable accounting regressions using only local workers."""
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from parallax_relay.realtime import __main__ as cli
from parallax_relay.realtime import physics
from parallax_relay.realtime.journal import Journal
from parallax_relay.realtime.recovery import interruption_receipt, save_receipt
from parallax_relay.realtime.supervise import SupervisionResult, supervise_command


def slot(run_id, cost, **extra):
    return dict(request_id=uuid4().hex, request_run_id=run_id, window=1, role='PYRA',
                phase='commit', sample_tick=0, attempt=1, reservation_quote_usd=float(cost),
                reservation_quote_usd_decimal=cost, **extra)


class SupervisionTests(unittest.TestCase):
    def test_keyboard_interrupt_and_repeat_reap_the_child(self):
        child = MagicMock()
        child.stdin = BytesIO()
        child.poll.return_value = None
        child.wait.side_effect = [KeyboardInterrupt(), KeyboardInterrupt(), KeyboardInterrupt(), -9]
        with patch('parallax_relay.realtime.supervise.subprocess.Popen', return_value=child):
            result = supervise_command(['inert-worker'], control_pipe=True)
        self.assertEqual(result, SupervisionResult('interrupted', 130, -9))
        self.assertTrue(child.stdin.closed)
        self.assertTrue(child.kill.called)
        self.assertEqual(child.wait.call_count, 4)

    def test_deadline_revokes_live_control_pipe_with_and_without_cooperation(self):
        cooperative = (
            'from parallax_relay.realtime.__main__ import _parent_control\n'
            'class LocalSession:\n'
            '    def close(self): raise SystemExit(19)\n'
            '_parent_control(LocalSession(), 2)'
        )
        stopped = supervise_command([sys.executable, '-c', cooperative], timeout_seconds=.5,
                                    cleanup_seconds=2, control_pipe=True)
        self.assertEqual(stopped, SupervisionResult('wall_timeout', 124, 19))
        hard = supervise_command([sys.executable, '-c', 'import time; time.sleep(60)'],
                                 timeout_seconds=.2, cleanup_seconds=.1, control_pipe=True)
        self.assertEqual((hard.status, hard.exit_code), ('wall_timeout', 124))
        self.assertNotEqual(hard.child_exit_code, 0)

    def test_supervisor_waits_only_until_the_shared_deadline(self):
        child = MagicMock()
        child.wait.return_value = 0
        with (patch('parallax_relay.realtime.supervise.subprocess.Popen', return_value=child),
              patch('parallax_relay.realtime.supervise.time.monotonic', side_effect=[100.0, 101.5])):
            result = supervise_command(['inert-worker'], outer_deadline=102.0)
        child.wait.assert_called_once_with(timeout=0.5)
        self.assertEqual(result, SupervisionResult('completed', 0, 0))

    def test_lost_parent_pipe_enforces_child_deadline_even_during_a_stuck_close(self):
        worker = (
            'import time\n'
            'from parallax_relay.realtime.__main__ import _parent_control\n'
            'class StuckLocalSession:\n'
            '    def close(self): time.sleep(60)\n'
            '_parent_control(StuckLocalSession(), 0.15)'
        )
        child = subprocess.Popen([sys.executable, '-c', worker], stdin=subprocess.PIPE)
        try:
            child.stdin.close()
            self.assertEqual(child.wait(timeout=5), 125)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_receipt_prices_unmatched_starts_and_keeps_the_last_whole_tick(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'match'
            journal = Journal(out)
            world = physics.initial_world()
            journal.record_initial(world)
            programs = {role: [] for role in world.robots}
            physics.step(world, programs, 0)
            journal.record_tick(world, programs, 0)
            with (out / 'simulation.jsonl').open('ab') as stream:
                stream.write(b'{"type":"tick"')  # Interrupted before this row became durable.
            known = slot(journal.run_id, '0.02000')
            pending = slot(journal.run_id, '0.05000')
            stopped = slot(journal.run_id, '0.08000')
            for evidence in (known, pending, stopped):
                journal.private('attempt_started', **evidence)
            journal.private('attempt', **known, status='ok', settlement_basis='complete_usage',
                            settled_amount_usd=.015, settled_amount_usd_decimal='0.015')
            journal.private('attempt', **stopped, status='not_dispatched', settlement_basis='not_dispatched',
                            settled_amount_usd=0, settled_amount_usd_decimal='0')
            journal.private('private_notes', notes='ROLE_PRIVATE_SENTINEL')
            receipt = interruption_receipt(out, journal.run_id, SupervisionResult('wall_timeout', 124, -9))
            self.assertEqual(receipt['checkpoint']['last_journaled_tick'], 1)
            self.assertEqual(receipt['checkpoint']['status'], 'partial')
            self.assertFalse(receipt['checkpoint']['finish_marker_seen'])
            accounting = receipt['accounting']
            self.assertEqual((accounting['starts_observed'], accounting['settlements_observed'],
                              accounting['confirmed_not_dispatched']), (3, 2, 1))
            self.assertEqual(accounting['possibly_dispatched_unsettled'][0]['request_id'], pending['request_id'])
            self.assertEqual(accounting['retained_unsettled_usd_decimal'], '0.05000')
            self.assertEqual(accounting['local_estimated_total_usd_decimal'], '0.06500')
            saved = save_receipt(out, receipt)
            self.assertEqual(saved.parent, out.parent)
            self.assertEqual(json.loads(saved.read_bytes()), receipt)
            with self.assertRaises(FileExistsError):
                save_receipt(out, receipt)
            self.assertNotIn('ROLE_PRIVATE_SENTINEL', saved.read_text(encoding='ascii'))

    def test_early_or_unrelated_output_cannot_supply_another_jobs_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'match'
            run_id = str(uuid4())
            stopped = SupervisionResult('interrupted', 130, -9)
            missing = interruption_receipt(out, run_id, stopped)
            self.assertEqual(missing['recording_identity'], 'unavailable')
            self.assertIsNone(missing['accounting'])
            other = Journal(out)
            other.private('attempt_started', **slot(other.run_id, '0.50'))
            mismatch = interruption_receipt(out, run_id, stopped)
            self.assertEqual(mismatch['recording_identity'], 'mismatch')
            self.assertIsNone(mismatch['accounting'])
            self.assertIsNone(mismatch['checkpoint'])

    def test_unpriced_or_partial_evidence_keeps_the_total_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'match'
            journal = Journal(out)
            unpriced = slot(journal.run_id, '0.5')
            unpriced['reservation_quote_usd'] = None
            del unpriced['reservation_quote_usd_decimal']
            journal.private('attempt_started', **unpriced)
            stopped = SupervisionResult('interrupted', 130, -9)
            value = interruption_receipt(out, journal.run_id, stopped)['accounting']
            self.assertIsNone(value['local_estimated_total_usd_decimal'])
            self.assertEqual(len(value['possibly_dispatched_unsettled']), 1)
            with (out / 'private.jsonl').open('ab') as stream:
                stream.write(b'{')
            value = interruption_receipt(out, journal.run_id, stopped)['accounting']
            self.assertEqual(value['status'], 'partial')
            self.assertIsNone(value['local_estimated_total_usd_decimal'])

    def test_conflicting_settlement_retains_the_original_reservation(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'match'
            journal = Journal(out)
            started = slot(journal.run_id, '0.25')
            journal.private('attempt_started', **started)
            journal.private('attempt', **started, status='timeout', settlement_basis='retained_estimate',
                            settled_amount_usd=0, settled_amount_usd_decimal='0')
            record = interruption_receipt(out, journal.run_id, SupervisionResult('wall_timeout', 124, 125))
            accounting = record['accounting']
            self.assertEqual(accounting['settlements_observed'], 0)
            self.assertEqual(accounting['status'], 'partial')
            self.assertEqual(accounting['retained_unsettled_usd_decimal'], '0.25')
            self.assertIsNone(accounting['local_estimated_total_usd_decimal'])

    def test_live_cli_handoff_reports_an_interruption_without_constructing_a_client(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'match'
            def inert_launcher(argv, **options):
                self.assertTrue(options['control_pipe'])
                self.assertEqual(options['outer_deadline'], 340.0)
                self.assertEqual(float(argv[-3]), options['outer_deadline'])
                self.assertEqual(argv[-2], str(out))
                journal = Journal(out, run_id=argv[-1])
                journal.record_initial(physics.initial_world())
                journal.private('private_notes', value='LOCAL_ONLY')
                return SupervisionResult('interrupted', 130, -9)

            output = StringIO()
            with (patch.object(cli, 'supervise_command', side_effect=inert_launcher),
                  patch.object(cli, 'monotonic', return_value=100.0), redirect_stdout(output)):
                code = cli.main(['--live', '--profile', 'dev-bridge-live-v1', '--out', str(out)])
            self.assertEqual(code, 130)
            published = json.loads(output.getvalue())
            self.assertEqual(published['supervision']['checkpoint']['last_journaled_tick'], 0)
            self.assertEqual(json.loads(Path(published['receipt_file']).read_bytes()), published['supervision'])
            self.assertNotIn('LOCAL_ONLY', output.getvalue())

    def test_child_uses_shared_deadline_and_rejects_malformed_arguments(self):
        run_id = str(uuid4())
        argv = ['worker', 'dev-bridge-live-v1', '101.0', 'match', run_id]
        with (patch.object(cli, 'monotonic', return_value=100.0),
              patch.object(cli, '_run', return_value=0) as run):
            with patch.object(sys, 'argv', argv):
                self.assertEqual(cli._live_child(), 0)
            self.assertEqual(run.call_args.kwargs, {'run_id': run_id, 'outer_deadline': 101.0})
            run.reset_mock()
            for text in ('nan', 'inf', 'invalid', '341.0'):
                invalid = argv[:2] + [text] + argv[3:]
                with self.subTest(text=text), patch.object(sys, 'argv', invalid), redirect_stderr(StringIO()):
                    self.assertEqual(cli._live_child(), 2)
            with patch.object(sys, 'argv', argv[:2]), redirect_stderr(StringIO()):
                self.assertEqual(cli._live_child(), 2)
            run.assert_not_called()
