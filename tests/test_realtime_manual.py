import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_realtime_coordination import Agent, Clock, observations, observed

from parallax_relay.protocol import ROLES
from parallax_relay.realtime.coordination import Coordinator, REDUCED_PHASES
from parallax_relay.realtime.manual import ManualAgent, ManualControls
from parallax_relay.realtime.settings import Settings


def plan(request, ticks=1):
    return {**request, 'actions': [dict(kind='WAIT', direction=None, ticks=ticks, jump_at=None)]}


class ManualAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.controls = ManualControls(Settings.offline('manual'), self.emit)

    def emit(self, kind, **data):
        if kind == 'manual_request':
            self.requests.append(data)

    async def open_slot(self, window, request_id):
        request = SimpleNamespace(role='PYRA', window=window, request_id=request_id)
        commit = asyncio.create_task(self.controls.commit(request))
        await observed(lambda: self.requests and self.requests[-1]['request_id'] == request_id)
        return commit, self.requests[-1]

    async def test_reply_completed_at_exact_deadline_is_rejected_by_post(self):
        settings = Settings(phase_timeout_seconds=10.0, max_estimated_cost_usd=None)
        clock = Clock()
        requests = []

        def emit(kind, **data):
            if kind == 'manual_request':
                requests.append(data)
            if kind == 'ready' and data['phase'] == 'commit':
                controls.admitted(data['role'], data['window'], data['status'])

        controls = ManualControls(settings, emit)
        agents = {role: Agent() for role in ROLES}
        agents['PYRA'] = ManualAgent(agents['PYRA'], controls)
        coordinator = Coordinator(agents, settings, {}, emit, clock=clock, sleep=clock.sleep,
                                  phases=REDUCED_PHASES)
        decode = coordinator._decode

        def at_cutoff(reply, request, window):
            outcome = decode(reply, request, window)
            if request.role == 'PYRA' and request.phase == 'commit':
                self.assertEqual(outcome.status, 'ok')
                clock.advance(10.0)
            return outcome

        coordinator._decode = at_cutoff
        match = asyncio.create_task(coordinator.coordinate(observations(1), 1, 40.0))
        await observed(lambda: bool(requests))
        data = plan(requests[0])
        receipt = await asyncio.to_thread(controls.submit, data)
        programs, _ = await match
        self.assertEqual(coordinator.dispositions['PYRA'], 'timeout')
        self.assertEqual(programs['PYRA'], [])
        self.assertFalse(receipt['ok'])
        self.assertEqual(await asyncio.to_thread(controls.submit, data), receipt)

    async def test_concurrent_retries_share_admission_and_conflicts_cannot_replace_plan(self):
        commit, request = await self.open_slot(1, 'initial')
        data = plan(request)
        submitted = asyncio.create_task(asyncio.to_thread(self.controls.submit, data))
        reply = await asyncio.wait_for(commit, timeout=2)
        self.assertEqual(json.loads(reply.text)['actions'], data['actions'])
        self.assertFalse(submitted.done())

        reordered = dict(reversed(list(data['actions'][0].items())))
        retry = asyncio.create_task(asyncio.to_thread(self.controls.submit, {**data, 'actions': [reordered]}))
        conflict = await asyncio.to_thread(self.controls.submit, plan(request, ticks=2))
        self.assertFalse(conflict['ok'])
        self.assertFalse(submitted.done())
        self.assertFalse(retry.done())

        self.controls.admitted('PYRA', 1, 'ok')
        self.assertEqual(await submitted, {'ok': True, 'points': 0})
        self.assertEqual(await retry, {'ok': True, 'points': 0, 'duplicate': True})
        next_commit, _ = await self.open_slot(2, 'following')
        self.assertEqual(await asyncio.to_thread(self.controls.submit, data), await retry)
        self.assertFalse(next_commit.done())
        self.controls.close()
        with self.assertRaises(asyncio.CancelledError):
            await next_commit

    async def test_stale_receipts_and_dispositions_cannot_enter_new_window(self):
        previous, old_request = await self.open_slot(1, 'old')
        previous.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await previous

        commit, request = await self.open_slot(2, 'current')
        self.assertFalse((await asyncio.to_thread(self.controls.submit, plan(old_request)))['ok'])
        self.controls.admitted('PYRA', 1, 'ok')
        submitted = asyncio.create_task(asyncio.to_thread(self.controls.submit, plan(request)))
        await asyncio.wait_for(commit, timeout=2)
        self.controls.admitted('PYRA', 2, 'ok')
        self.assertTrue((await submitted)['ok'])

    async def test_session_close_resolves_delivered_receipt_without_ready(self):
        commit, request = await self.open_slot(1, 'cancelled')
        data = plan(request)
        submitted = asyncio.create_task(asyncio.to_thread(self.controls.submit, data))
        await asyncio.wait_for(commit, timeout=2)
        self.controls.close()
        receipt = await asyncio.wait_for(submitted, timeout=1)
        self.assertFalse(receipt['ok'])
        self.controls.admitted('PYRA', 1, 'ok')
        self.assertEqual(await asyncio.to_thread(self.controls.submit, data), receipt)

    async def test_delayed_callback_cannot_deliver_after_receipt_is_closed(self):
        commit, request = await self.open_slot(1, 'queued')
        data = plan(request)
        deliver = self.controls._deliver
        with (patch.object(self.controls, '_deliver') as queued,
              patch('parallax_relay.realtime.manual._RECEIPT_WAIT_SECONDS', 0.1)):
            receipt = await asyncio.to_thread(self.controls.submit, data)
        self.assertFalse(receipt['ok'])
        queued.assert_called_once()
        deliver(*queued.call_args.args)
        self.controls.close()
        with self.assertRaises(asyncio.CancelledError):
            await commit
        self.assertEqual(await asyncio.to_thread(self.controls.submit, data), receipt)

    async def test_unconfirmed_delivery_can_be_retried_without_replacing_it(self):
        commit, request = await self.open_slot(1, 'delivered')
        data = plan(request)
        with patch('parallax_relay.realtime.manual._RECEIPT_WAIT_SECONDS', 0.1):
            submitted = asyncio.create_task(asyncio.to_thread(self.controls.submit, data))
            await asyncio.wait_for(commit, timeout=2)
            receipt = await submitted
        self.assertFalse(receipt['ok'])
        self.assertIn('has not confirmed', receipt['error'])
        self.controls.admitted('PYRA', 1, 'ok')
        self.assertEqual(await asyncio.to_thread(self.controls.submit, data),
                         {'ok': True, 'points': 0, 'duplicate': True})
