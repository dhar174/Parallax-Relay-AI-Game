import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

import httpx

from parallax_relay.config import Rates
from parallax_relay.protocol import ModelReply, Observation, ROLES, Usage
from parallax_relay.providers import HTTPAgent, ProviderError
from parallax_relay.realtime.coordination import Coordinator, CoordinationStop, REDUCED_PHASES
from parallax_relay.realtime.journal import Journal
from parallax_relay.realtime.settings import Settings


def observations(window, tick=0):
    return {role: Observation(role, window, json.dumps({'role': role, 'window': window,
                        'sample_tick': tick, 'private_sentinel': f'private-{role}'}), role.encode())
            for role in ROLES}


def valid(request, **changes):
    data = {'window': request.window, 'request_id': request.request_id}
    if request.phase == 'commit':
        data.update(actions=[dict(kind='WAIT', direction=None, ticks=1, jump_at=None)],
                    notes=f'note-{request.role}-{request.window}')
    else:
        data['message'] = f'{request.role} {request.phase} {request.window}'
    return ModelReply(json.dumps({**data, **changes}), Usage(3, 2))


class Agent:
    def __init__(self, handler=None):
        self.handler = handler
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return await self.handler(request) if self.handler else valid(request)


class Clock:
    """Advance only when the test explicitly supplies a timestamp."""

    def __init__(self):
        self.now = 0.0
        self.waiters = {}

    def __call__(self):
        return self.now

    async def sleep(self, delay):
        waiter = asyncio.get_running_loop().create_future()
        self.waiters[waiter] = self.now + delay
        try:
            await waiter
        finally:
            del self.waiters[waiter]

    def advance(self, target):
        assert self.now <= target
        self.now = target
        for waiter, until in self.waiters.items():
            if until <= target and not waiter.done():
                waiter.set_result(None)


async def observed(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), timeout=2)


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    def coordinator(self, handlers=None, *, settings=None, emit=None, rates=None, clock=None,
                    phases=('broadcast', 'negotiate', 'commit')):
        self.log = []
        self.agents = {r: Agent((handlers or {}).get(r)) for r in ROLES}
        def record(kind, **data):
            self.log.append((kind, data))
            if emit:
                emit(kind, **data)
        options = {'clock': clock, 'sleep': clock.sleep} if clock else {}
        return Coordinator(self.agents, settings or Settings.offline('test'), rates or {},
                           record, phases=phases, **options)

    async def test_freezes_role_inputs_and_publishes_only_completed_batches_in_roster_order(self):
        gates = {r: asyncio.Event() for r in ROLES}
        async def hold(request):
            if request.phase == 'broadcast':
                await gates[request.role].wait()
            return valid(request)
        coordinator = self.coordinator(dict.fromkeys(ROLES, hold))
        task = asyncio.create_task(coordinator.coordinate(observations(1), 1, time.monotonic() + 30))
        await observed(lambda: all(len(agent.requests) == 1 for agent in self.agents.values()))
        gates['FLUX'].set()
        await observed(lambda: any(k == 'ready' and d['role'] == 'FLUX' for k, d in self.log))
        self.assertFalse(any(k == 'dialogue' for k, _ in self.log))
        self.assertTrue(all(len(agent.requests) == 1 for agent in self.agents.values()))
        for role in ('PYRA', 'SPECTRA'):
            gates[role].set()
        programs, speech = await task
        self.assertEqual([m['role'] for m in speech], list(ROLES) * 2)
        self.assertEqual(len(coordinator.attempts), 9)
        self.assertEqual(len({a['request_id'] for a in coordinator.attempts}), 9)
        self.assertEqual([d['role'] for k, d in self.log if k == 'dialogue'], list(ROLES) * 2)
        for role, agent in self.agents.items():
            self.assertEqual([len(req.messages) for req in agent.requests], [0, 3, 6])
            self.assertTrue(all(req.observation is agent.requests[0].observation for req in agent.requests))
            self.assertEqual(programs[role][0]['kind'], 'WAIT')
            for req in agent.requests:
                for other in set(ROLES) - {role}:
                    self.assertNotIn(f'private-{other}', req.prompt_text())
        for kind, data in self.log:
            if kind in ('attempt', 'ready', 'phase_closed'):
                self.assertNotIn('note-', json.dumps(data))
                self.assertNotIn('actions', data)
        speech[0]['text'] = 'mutated return value'
        programs['PYRA'][0]['ticks'] = 120
        await coordinator.coordinate(observations(2, 120), 2, time.monotonic() + 30)
        for role, agent in self.agents.items():
            payload = json.loads(agent.requests[3].prompt_text())
            self.assertEqual(payload['your_private_notes'], f'note-{role}-1')
            self.assertEqual(payload['your_recent_history'][0]['your_actions'][0]['ticks'], 1)
            self.assertNotIn('mutated return value', agent.requests[3].prompt_text())
            for other in set(ROLES) - {role}:
                self.assertNotIn(f'private-{other}', agent.requests[3].prompt_text())

    async def test_strict_deadline_accepts_earlier_commit_and_rejects_boundary_and_late(self):
        clock = Clock()
        ready = {r: asyncio.Event() for r in ROLES}
        async def hold(request):
            if request.phase == 'commit':
                await ready[request.role].wait()
            return valid(request)
        settings = Settings(phase_timeout_seconds=10.0, max_estimated_cost_usd=None)
        coordinator = self.coordinator(dict.fromkeys(ROLES, hold), settings=settings, clock=clock)
        task = asyncio.create_task(coordinator.coordinate(observations(1), 1, 45.0))
        await observed(lambda: all(len(a.requests) == 3 for a in self.agents.values()))
        clock.advance(9.999)
        ready['SPECTRA'].set()
        await observed(lambda: any(k == 'ready' and d['phase'] == 'commit' for k, d in self.log))
        self.assertFalse(task.done())
        clock.advance(10.0)
        ready['PYRA'].set()
        programs, _ = await task
        clock.advance(10.001)
        ready['FLUX'].set()
        self.assertEqual([bool(programs[r]) for r in ROLES], [True, False, False])
        self.assertEqual(coordinator.notes, {'SPECTRA': 'note-SPECTRA-1', 'PYRA': '', 'FLUX': ''})
        self.assertEqual(coordinator.dispositions, dict(SPECTRA='ok', PYRA='timeout', FLUX='timeout'))
        self.assertEqual(coordinator.budget.summary()['unknown_usage_calls'], 2)

    async def test_retry_only_for_format_or_transient_and_never_discloses_raw_output(self):
        async def repairable(req):
            if req.phase == 'broadcast' and not req.repair:
                return ModelReply('sensitive-format-sentinel', Usage(2, 1))
            return valid(req)
        async def long_backoff(req):
            if req.phase == 'broadcast':
                raise ProviderError('http_error', True, 429, retry_after=30)
            return valid(req)
        async def illegal(req):
            if req.phase == 'commit':
                return valid(req, actions=[dict(kind='RUN', direction=1, ticks=91, jump_at=None)])
            return valid(req)
        settings = Settings(max_attempts=2, retry_delay_seconds=0, phase_timeout_seconds=1.0,
                            max_estimated_cost_usd=None)
        coordinator = self.coordinator(dict(SPECTRA=repairable, PYRA=long_backoff, FLUX=illegal), settings=settings)
        programs, _ = await coordinator.coordinate(observations(1), 1, time.monotonic() + 10)
        initial, repair = self.agents['SPECTRA'].requests[:2]
        self.assertNotEqual(initial.request_id, repair.request_id)
        self.assertIs(initial.observation, repair.observation)
        self.assertEqual(initial.messages, repair.messages)
        self.assertNotIn('sensitive-format-sentinel', repair.prompt_text())
        self.assertNotIn('sensitive-format-sentinel', json.dumps(coordinator.attempts))
        self.assertTrue(repair.repair)
        self.assertFalse(programs['FLUX'])
        self.assertEqual(coordinator.dispositions['FLUX'], 'invalid_action_plan')
        self.assertEqual([len(a.requests) for a in self.agents.values()], [4, 3, 3])
        summary = coordinator.budget.summary()
        self.assertEqual((summary['calls_started'], summary['calls_reserved_total'], summary['calls_released'],
                          summary['reserved_calls']), (10, 18, 8, 0))

    async def test_stale_cross_window_cross_session_and_other_roles_cannot_replace_commit(self):
        old = {}
        async def retained(req):
            if req.phase == 'commit':
                if req.role in old:
                    return old[req.role]
                old[req.role] = valid(req)
            return valid(req)
        coordinator = self.coordinator(dict.fromkeys(ROLES, retained))
        await coordinator.coordinate(observations(1), 1, time.monotonic() + 10)
        previous_notes = dict(coordinator.notes)
        programs, _ = await coordinator.coordinate(observations(2, 120), 2, time.monotonic() + 10)
        self.assertTrue(all(not p for p in programs.values()))
        self.assertEqual(coordinator.notes, previous_notes)
        self.assertTrue(all(s in ('stale_request_id', 'stale_window') for s in coordinator.dispositions.values()))
        async def duplicate(req):
            return old['SPECTRA'] if req.role == 'PYRA' and req.phase == 'commit' else valid(req)
        second = self.coordinator(dict.fromkeys(ROLES, duplicate))
        programs, _ = await second.coordinate(observations(1), 1, time.monotonic() + 10)
        self.assertEqual([bool(programs[r]) for r in ROLES], [True, False, True])
        self.assertEqual(second.dispositions['PYRA'], 'stale_request_id')
        self.assertNotIn(old['SPECTRA'].text, json.dumps(second.notes))

    async def test_resistant_transport_is_quarantined_and_late_usage_never_double_settles(self):
        clock, release = Clock(), asyncio.Event()
        async def resistant(req):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                return ModelReply(valid(req).text, Usage(9999, 9999))
        settings = Settings(phase_timeout_seconds=5.0, max_consecutive_failures=5)
        rates = dict.fromkeys(ROLES, Rates(input_per_million=1.0, output_per_million=1.0))
        coordinator = self.coordinator({'PYRA': resistant}, settings=settings, clock=clock, rates=rates)
        task = asyncio.create_task(coordinator.coordinate(observations(1), 1, 90.0))
        try:
            await observed(lambda: len(coordinator.attempts) == 2)
            clock.advance(5.0)
            programs, speech = await task
            self.assertFalse(programs['PYRA'])
            self.assertEqual([m['role'] for m in speech], ['SPECTRA', 'FLUX'] * 2)
            self.assertEqual(len(self.agents['PYRA'].requests), 1)
            self.assertEqual([p['statuses']['PYRA'] for p in coordinator.phase_records],
                             ['timeout', 'quarantined', 'quarantined'])
            original = coordinator.budget.summary()
            self.assertEqual((original['calls_started'], original['unknown_usage_calls'], original['reserved_calls']),
                             (7, 1, 0))
            self.assertGreater(float(original['retained_estimate_usd']), 0)
            self.assertFalse(await coordinator.close(timeout=0))
        finally:
            release.set()
            await coordinator.close(timeout=1)
        self.assertEqual(coordinator.budget.summary(), original)
        self.assertEqual(len(coordinator.attempts), 7)

    async def test_budget_admission_and_global_expiry_start_zero_calls(self):
        rates = dict.fromkeys(ROLES, Rates(input_per_million=1.0, output_per_million=1.0))
        for reason, limits, deadline in [('call_budget', {'max_calls': 5, 'max_attempts': 2}, 100.0),
                                         ('spend_budget', {'max_estimated_cost_usd': 0.000001}, 100.0),
                                         ('time_limit', {}, 0.0)]:
            with self.subTest(reason=reason):
                coordinator = self.coordinator(settings=Settings(**limits), clock=Clock(), rates=rates)
                with self.assertRaises(CoordinationStop) as caught:
                    await coordinator.coordinate(observations(1), 1, deadline)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(coordinator.attempts, [])
                self.assertEqual(self.log, [])
                self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)

    async def test_global_expiry_during_commit_returns_no_team_and_preserves_earlier_speech(self):
        clock, wait = Clock(), asyncio.Event()
        async def hold(req):
            if req.phase == 'commit':
                await wait.wait()
            return valid(req)
        coordinator = self.coordinator({'FLUX': hold}, clock=clock, phases=REDUCED_PHASES)
        task = asyncio.create_task(coordinator.coordinate(observations(1), 1, 2.0))
        await observed(lambda: len(coordinator.attempts) == 5)
        clock.advance(2.0)
        with self.assertRaises(CoordinationStop) as caught:
            await task
        self.assertEqual(caught.exception.reason, 'time_limit')
        self.assertTrue(all(n == '' for n in coordinator.notes.values()))
        self.assertEqual(len([k for k, _ in self.log if k == 'dialogue']), 3)
        self.assertEqual(coordinator.phase_records[-1]['status'], 'time_limit')
        self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)

    async def test_refusal_breaker_and_fatal_provider_status_are_separate(self):
        async def refuses(req):
            return ModelReply('', Usage(3, 0), 'refusal')
        async def fatal(req):
            raise ProviderError('quota_exhausted', False, 429)
        for handler, reason, phases in ((refuses, 'unreliable_agent', 3), (fatal, 'provider_error', 1)):
            with self.subTest(reason=reason):
                coordinator = self.coordinator({'PYRA': handler}, settings=Settings(max_attempts=2,
                                               max_estimated_cost_usd=None, retry_delay_seconds=0))
                with self.assertRaises(CoordinationStop) as caught:
                    await coordinator.coordinate(observations(1), 1, time.monotonic() + 5)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(len(self.agents['PYRA'].requests), phases)
                self.assertTrue(all(not note for note in coordinator.notes.values()))
                self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)

    async def test_recording_failure_and_cancellation_account_for_all_started_attempts(self):
        def broken(kind, **data):
            if kind == 'attempt':
                raise OSError('private file path sentinel')
        coordinator = self.coordinator(emit=broken)
        with self.assertRaises(CoordinationStop) as caught:
            await coordinator.coordinate(observations(1), 1, time.monotonic() + 5)
        self.assertEqual(caught.exception.reason, 'local_error')
        self.assertEqual(len(coordinator.attempts), 3)
        self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)
        self.assertFalse(any(k == 'dialogue' for k, _ in self.log))

        async def hangs(req):
            await asyncio.Event().wait()
        coordinator = self.coordinator(dict.fromkeys(ROLES, hangs))
        task = asyncio.create_task(coordinator.coordinate(observations(1), 1, time.monotonic() + 5))
        await observed(lambda: all(a.requests for a in self.agents.values()))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([a['status'] for a in coordinator.attempts], ['cancelled'] * 3)
        self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)
        self.assertTrue(await coordinator.close(timeout=1))

    async def test_phase_close_recording_failure_preserves_primary_provider_stop(self):
        async def quota(req):
            raise ProviderError('quota_exhausted', False, 429)
        def broken_at_close(kind, **data):
            if kind == 'phase_closed':
                raise OSError('private file path sentinel')
        coordinator = self.coordinator({'PYRA': quota}, emit=broken_at_close)
        with self.assertRaises(CoordinationStop) as caught:
            await coordinator.coordinate(observations(1), 1, time.monotonic() + 5)
        self.assertEqual(caught.exception.reason, 'provider_error')
        self.assertEqual(coordinator.phase_records[-1]['status'], 'provider_error')
        self.assertEqual(coordinator.phase_records[-1]['close_error'], 'local_error')
        self.assertEqual(coordinator.budget.summary()['reserved_calls'], 0)

    async def test_durable_lease_precedes_every_dispatch_and_pairs_with_its_settlement(self):
        charges = dict.fromkeys(ROLES, Rates(input_per_million=0.1, output_per_million=0.5))
        seen_at_dispatch = {}
        with TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / 'run')
            private_log = journal.out / 'private.jsonl'

            def private_events(kind, **data):
                if kind in ('attempt_started', 'attempt'):
                    journal.private(kind, **data)

            async def inspect(req):
                rows = [json.loads(line) for line in private_log.read_text(encoding='utf-8').splitlines()]
                seen_at_dispatch[req.request_id] = [row['kind'] for row in rows
                                                     if row['data']['request_id'] == req.request_id]
                if req.role == 'PYRA' and req.phase == 'broadcast' and not req.repair:
                    return ModelReply('malformed', Usage(1, 0))
                return valid(req)

            settings = Settings(max_attempts=2, retry_delay_seconds=0)
            runner = self.coordinator(dict.fromkeys(ROLES, inspect), settings=settings, rates=charges,
                                      emit=private_events)
            await runner.coordinate(observations(1), 1, time.monotonic() + 10)
            rows = [json.loads(line) for line in private_log.read_text(encoding='utf-8').splitlines()]
            starts = {r['data']['request_id']: r['data'] for r in rows if r['kind'] == 'attempt_started'}
            self.assertEqual(len(starts), 10)
            self.assertEqual(seen_at_dispatch, dict.fromkeys(starts, ['attempt_started']))
            for end in runner.attempts:
                start = starts[end['request_id']]
                self.assertEqual(set(start), {'request_run_id', 'window', 'sample_tick', 'phase', 'role',
                                              'request_id', 'attempt', 'reservation_quote_usd',
                                              'reservation_quote_usd_decimal'})
                self.assertEqual(start, {key: end[key] for key in start})
                self.assertEqual(start['request_run_id'], runner.run_id)
                self.assertGreater(float(start['reservation_quote_usd_decimal']), 0)
            self.assertEqual(len(rows), 20)

    async def test_failed_lease_write_prevents_http_dispatch_and_consumes_zero_calls(self):
        sent = []
        async def intercepted(request):
            sent.append(request)
            return httpx.Response(503)
        def fail_lease(kind, **data):
            if kind == 'attempt_started':
                raise OSError('write failure')
        async with httpx.AsyncClient(transport=httpx.MockTransport(intercepted)) as client:
            agents = {role: HTTPAgent('openai', 'fixture', 'offline', client=client) for role in ROLES}
            runner = Coordinator(agents, Settings.offline('test'), {}, fail_lease)
            with self.assertRaises(CoordinationStop) as caught:
                await runner.coordinate(observations(1), 1, time.monotonic() + 10)
            self.assertEqual(caught.exception.reason, 'local_error')
            self.assertEqual(sent, [])
            self.assertEqual(runner.attempts, [])
            self.assertEqual(runner.budget.calls_started, 0)
            self.assertEqual(runner.budget.reserved_calls, 0)

    async def test_lease_write_crossing_deadline_closes_known_undispatched_exposure(self):
        clock = Clock()
        def slow_lease(kind, **data):
            if kind == 'attempt_started':
                clock.advance(5.0)
        rates = dict.fromkeys(ROLES, Rates(input_per_million=1.0, output_per_million=1.0))
        runner = self.coordinator(clock=clock, emit=slow_lease, rates=rates)
        with self.assertRaises(CoordinationStop) as caught:
            await runner.coordinate(observations(1), 1, 5.0)
        self.assertEqual(caught.exception.reason, 'time_limit')
        self.assertTrue(all(not agent.requests for agent in self.agents.values()))
        self.assertEqual(runner.attempts, [])
        starts = [data for kind, data in self.log if kind == 'attempt_started']
        ends = [data for kind, data in self.log if kind == 'attempt']
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]['request_id'], starts[0]['request_id'])
        self.assertEqual(ends[0]['status'], 'not_dispatched')
        self.assertEqual(ends[0]['settlement_basis'], 'not_dispatched')
        self.assertEqual(ends[0]['settled_amount_usd_decimal'], '0')
        self.assertGreater(float(ends[0]['reservation_quote_usd_decimal']), 0)
        self.assertEqual(runner.budget.calls_started, 0)
