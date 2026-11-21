"""Bounded inference barriers. This module has no access to a simulation or a spectator."""
from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from uuid import uuid4

from ..budget import Budget, BudgetExceeded
from ..money import json_fields
from ..protocol import ModelReply, ROLES, ReplyValidationError
from ..providers import ProviderError
from .wire import make_request, parse


FULL_PHASES = ('broadcast', 'negotiate', 'commit')
REDUCED_PHASES = ('broadcast', 'commit')
FORMAT_ERRORS = frozenset({'invalid_json_schema', 'response_size', 'incomplete'})
REPAIR = 'Return only the required JSON shape, echoing the supplied request ID and window.'


class CoordinationStop(Exception):
    """Safe, host-assigned run stop. Started attempts remain available on the coordinator."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Outcome:
    status: str
    value: dict | None = None
    retryable: bool = False
    retry_after: float = 0.0
    fatal: str | None = None


class Coordinator:
    """One session's host-owned request slots, private role memory and budget.

    ``deadline`` is absolute on ``clock``. Inject both ``clock`` and ``sleep`` for
    virtual-time tests. ``emit(kind, **data)`` synchronously persists private
    ``attempt_started`` leases and ``attempt`` settlements. The caller owns the clients.
    """

    def __init__(self, agents, settings, rates, emit, *, clock=time.monotonic,
                 sleep=asyncio.sleep, phases=FULL_PHASES, run_id=None):
        if set(agents) != set(ROLES):
            raise ValueError('Coordinator requires the three active roles')
        if tuple(phases) not in (FULL_PHASES, REDUCED_PHASES):
            raise ValueError('Unknown real-time phase schedule')
        self.agents = dict(agents)
        self.settings = settings
        self.budget = Budget(settings, rates)
        self.emit = emit
        self.clock = clock
        self.sleep = sleep
        self.phases = tuple(phases)
        self.run_id = run_id or str(uuid4())
        self.attempts = []
        self.phase_records = []
        self.notes = dict.fromkeys(ROLES, '')
        self.histories = {role: [] for role in ROLES}
        self.dispositions = {}
        self._failures = dict.fromkeys(ROLES, 0)
        self._transports = {}
        self._workers = set()
        self._last_window = None
        self._busy = False
        self._stopped = None
        self._output_failed = False

    def _emit(self, kind, **data):
        if self._output_failed:
            raise CoordinationStop('local_error')
        try:
            self.emit(kind, **data)
        except Exception:
            self._output_failed = True
            raise CoordinationStop('local_error') from None

    def _reap(self, role, task):
        # Taking the exception prevents a quarantined transport from leaking its
        # exception into the event loop's logger. Its result never re-enters intake.
        if not task.cancelled():
            task.exception()
        if self._transports.get(role) is task:
            del self._transports[role]

    async def _until(self, deadline):
        while (remaining := deadline - self.clock()) > 0:
            await self.sleep(remaining)

    def _decode(self, reply, request, window):
        if not isinstance(reply, ModelReply):
            return _Outcome('internal_error', fatal='internal_error')
        if reply.status == 'refusal':
            return _Outcome('refusal')
        if reply.status != 'ok':
            return _Outcome('incomplete', retryable=True)
        try:
            value = parse(reply.text, request.phase, window, request.request_id, self.settings)
        except ReplyValidationError as exc:
            code = str(exc)
            return _Outcome(code, retryable=code in FORMAT_ERRORS)
        return _Outcome('ok', value)

    async def _attempt(self, role, request, window, tick, number, ticket, deadline):
        started = self.clock()
        expires = min(deadline, started + self.settings.timeout_seconds)
        # The caller checks at dispatch as well. Recheck because a preceding role
        # or synchronous journal write can consume the remaining wall allowance.
        if started >= deadline:
            return _Outcome('timeout')
        identity = dict(request_run_id=self.run_id, window=window, sample_tick=tick,
                        phase=request.phase, role=role, request_id=request.request_id, attempt=number)
        priced = self.budget.rates.get(role) is not None
        quote = json_fields({'reservation_quote_usd': ticket.quote if priced else None})
        # A crash between this durable lease and its settlement leaves a possible
        # dispatch with an exact reserved exposure. A failed write cannot send.
        self._emit('attempt_started', **identity, **quote)
        dispatched_at = None

        async def dispatch():
            nonlocal dispatched_at
            now = self.clock()
            # Our write or a sibling's may consume the last of the deadline.
            if now >= expires or self._output_failed or self._stopped:
                return None
            ticket.start()
            dispatched_at = now
            return await self.agents[role].respond(request)

        transport = timer = None
        outcome = _Outcome('internal_error', fatal='internal_error')
        usage = http_status = None
        interrupted = False
        try:
            transport = asyncio.create_task(dispatch())
            self._transports[role] = transport
            transport.add_done_callback(lambda done: self._reap(role, done))
            timer = asyncio.create_task(self._until(expires))
            # Unlike wait_for(), this does not await a transport's cancellation
            # handshake. A resistant transport keeps its role's dispatch slot.
            await asyncio.wait((transport, timer), return_when=asyncio.FIRST_COMPLETED)
            if timer.done() and not timer.cancelled():
                timer.result()
            if self.clock() >= expires or not transport.done():
                outcome = _Outcome('timeout', retryable=True)
            elif transport.cancelled():
                outcome = _Outcome('cancelled')
            elif dispatched_at is None:
                outcome = _Outcome('not_dispatched', fatal=self._stopped or 'local_error')
            else:
                try:
                    reply = transport.result()
                except ProviderError as exc:
                    http_status = exc.status_code
                    outcome = _Outcome(exc.code, retryable=exc.retryable, retry_after=exc.retry_after,
                                       fatal=None if exc.retryable else 'provider_error')
                else:
                    outcome = self._decode(reply, request, window)
                    if isinstance(reply, ModelReply):
                        usage = reply.usage
                # Parsing and the admission timestamp belong to this serialized
                # event-loop step. Even a completed response loses an exact tie.
                if self.clock() >= expires:
                    outcome, usage, http_status = _Outcome('timeout', retryable=True), None, None
        except asyncio.CancelledError:
            interrupted = True
            outcome = _Outcome('cancelled')
            raise
        except Exception:
            # Agent exceptions and parser internals may contain untrusted text.
            outcome = _Outcome('internal_error', fatal='internal_error')
        finally:
            if timer is not None:
                timer.cancel()
            if transport is not None and not transport.done() and not transport.cancelling():
                transport.cancel()
            if dispatched_at is None:
                settlement = dict(**quote, settlement_basis='not_dispatched',
                                  **json_fields({'settled_amount_usd': Decimal(0) if priced else None}))
            else:
                settlement = ticket.settle(usage)
            record = dict(**identity, status='not_dispatched' if dispatched_at is None else outcome.status,
                          latency_seconds=0.0 if dispatched_at is None else max(0.0, self.clock() - dispatched_at),
                          http_status=http_status,
                          usage=asdict(usage) if usage is not None else None, **settlement)
            if dispatched_at is not None:
                self.attempts.append(record)
            try:
                self._emit('attempt', **record)
            except CoordinationStop:
                if not interrupted:
                    raise
        return outcome

    async def _ask(self, role, request, window, tick, ticket, deadline):
        outcome = _Outcome('quarantined')
        for number in range(1, self.settings.max_attempts + 1):
            if self._stopped or self._output_failed:
                raise CoordinationStop(self._stopped or 'local_error')
            pending = self._transports.get(role)
            if pending is not None and not pending.done():
                return outcome
            if self.clock() >= deadline:
                return _Outcome('timeout')
            if number > 1:
                request = replace(request, request_id=uuid4().hex,
                                  repair=REPAIR if outcome.status in FORMAT_ERRORS else '')
            outcome = await self._attempt(role, request, window, tick, number, ticket, deadline)
            if not outcome.retryable or number == self.settings.max_attempts:
                break
            delay = max(self.settings.retry_delay_seconds * 2 ** (number - 1), outcome.retry_after)
            wake = self.clock() + delay
            if wake >= deadline:
                break
            if delay:
                await self._until(wake)
            else:
                await asyncio.sleep(0)  # Give a cooperative cancelled transport a chance to drain.
        return outcome

    async def _phase(self, observations, window, tick, phase, messages, global_deadline):
        if self.clock() >= global_deadline:
            raise CoordinationStop('time_limit')
        requests = {r: make_request(observations[r], phase, messages, self.histories[r],
                                    self.notes[r], window, uuid4().hex, self.settings) for r in ROLES}
        try:
            tickets = self.budget.reserve_phase(requests)
        except BudgetExceeded as exc:
            raise CoordinationStop(exc.reason) from None
        opened = self.clock()
        if opened >= global_deadline:
            for ticket in tickets.values():
                ticket.release()
            raise CoordinationStop('time_limit')
        deadline = min(global_deadline, opened + self.settings.phase_timeout_seconds)
        outcomes, ready_at = {}, {}

        async def collect(role):
            result = await self._ask(role, requests[role], window, tick, tickets[role], deadline)
            # Exactly one worker owns each slot. Each transport returns at most
            # one payload and quarantined callbacks cannot publish or replace it.
            outcomes[role] = result
            ready_at[role] = self.clock()
            self._emit('ready', window=window, sample_tick=tick, phase=phase, role=role,
                       disposition='ready' if result.value is not None else 'fallback',
                       status=result.status, elapsed_seconds=max(0.0, ready_at[role] - opened))
            if result.fatal:
                self._stopped = result.fatal
                raise CoordinationStop(result.fatal)

        status = 'ok'
        try:
            self._emit('phase_open', window=window, sample_tick=tick, phase=phase)
            for role in ROLES:
                self._workers.add(asyncio.create_task(collect(role)))
            await asyncio.gather(*self._workers)
            for role in ROLES:
                result = outcomes[role]
                self._failures[role] = 0 if result.value is not None else self._failures[role] + 1
                if phase != 'commit' and result.value is not None and result.value['message']:
                    message = dict(role=role, window=window, phase=phase, text=result.value['message'])
                    messages.append(message)
                    self._emit('dialogue', **message)
            if self.clock() >= global_deadline:
                raise CoordinationStop('time_limit')
            if max(self._failures.values()) >= self.settings.max_consecutive_failures:
                raise CoordinationStop('unreliable_agent')
        except CoordinationStop as exc:
            status = exc.reason
            raise
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception:
            status = 'internal_error'
            raise CoordinationStop(status) from None
        finally:
            for worker in self._workers:
                if not worker.done():
                    worker.cancel()
            try:
                if self._workers:
                    await asyncio.gather(*self._workers, return_exceptions=True)
            finally:
                self._workers.clear()
                for ticket in tickets.values():
                    ticket.release()
            closed = self.clock()
            record = dict(window=window, sample_tick=tick, phase=phase, status=status,
                          statuses={r: outcomes[r].status if r in outcomes else 'cancelled' for r in ROLES},
                          elapsed_seconds=max(0.0, closed - opened),
                          barrier_idle_seconds={r: max(0.0, closed - t) for r, t in ready_at.items()})
            self.phase_records.append(record)
            if not self._output_failed:
                try:
                    self._emit('phase_closed', **record)
                except CoordinationStop as exc:
                    record['close_error'] = exc.reason
                    if status == 'ok':
                        raise
        return outcomes

    async def coordinate(self, observations, window, deadline):
        """Return the sealed team programs and public speech. No world ticks occur here."""
        if self._stopped:
            raise CoordinationStop(self._stopped)
        if (self._busy or type(window) is not int or window < 1
                or (self._last_window is not None and window <= self._last_window)):
            raise ValueError('Expected one new window at a time')
        if (set(observations) != set(ROLES)
                or any(observations[r].role != r or observations[r].turn != window for r in ROLES)):
            raise ValueError('Invalid role or observation window')
        sample_ticks = [observations[r].hud.get('sample_tick') for r in ROLES]
        if any(type(tick) is not int or tick < 0 or tick != sample_ticks[0] for tick in sample_ticks):
            raise ValueError('Observations must share one simulation tick')
        self._busy, self._last_window = True, window
        self.dispositions = {}
        messages = []
        try:
            for phase in self.phases:
                outcomes = await self._phase(observations, window, sample_ticks[0], phase, messages, deadline)
            if self.clock() >= deadline:
                raise CoordinationStop('time_limit')
            programs = {}
            for role in ROLES:
                result = outcomes[role]
                self.dispositions[role] = result.status
                programs[role] = result.value['actions'] if result.value is not None else []
                if result.value is not None:
                    self.notes[role] = result.value['notes']
                if self.settings.history_turns:
                    history = self.histories[role]
                    history.append(dict(window=window, observation=observations[role].hud,
                                        your_actions=deepcopy(programs[role]), public_messages=deepcopy(messages)))
                    del history[:-self.settings.history_turns]
            return programs, messages
        except CoordinationStop as exc:
            self._stopped = exc.reason
            raise
        except asyncio.CancelledError:
            self._stopped = 'cancelled'
            raise
        except Exception:
            self._stopped = 'internal_error'
            raise CoordinationStop('internal_error') from None
        finally:
            self._busy = False

    async def close(self, timeout=5.0):
        """Revoke dispatch and bound cooperative draining; false means transport still pending."""
        self._stopped = self._stopped or 'cancelled'
        pending = {task for task in (*self._workers, *self._transports.values()) if not task.done()}
        for task in pending:
            if not task.cancelling():
                task.cancel()
        if pending:
            _, pending = await asyncio.wait(pending, timeout=max(0.0, timeout))
        return not pending
