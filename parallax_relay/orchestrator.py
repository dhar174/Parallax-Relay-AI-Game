"""Lockstep concurrent turns. The only module that applies model actions.

Every phase operates on immutable request values, and asyncio.gather is a
barrier: no current-phase output enters another current-phase input.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field, replace
import json
from time import perf_counter
from typing import Callable, Mapping

from .budget import Budget, BudgetExceeded, Ticket
from .config import MatchSettings, Rates
from .engine import resolve_turn, score
from .observations import observe
from .protocol import (Agent, AgentRequest, BroadcastReply, CommitReply, ChatMessage,
                       ReplyValidationError, ROLES, parse_reply)
from .providers import ProviderError
from .recording import RecordingFinalizationError
from .state import Action, WorldState, initial_world, public_events


@dataclass
class MatchResult:
    world: WorldState
    stop_reason: str
    records: list[dict]
    calls: list[dict]
    budget: dict
    phases: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        terminal = self.world.win or self.world.loss
        return {'schema_version': 2, 'win': self.world.win, 'loss': self.world.loss,
                'completed': terminal, 'turns': self.world.turn,
                'stop_reason': self.stop_reason,
                'scores': score(self.world) if terminal else None,
                'energy': self.world.energy, 'budget': self.budget}


class MatchExecutionError(RuntimeError):
    """Safe public exception; raw errors are for trusted diagnosis only."""
    def __init__(self, result, original_error, operation, secondary_errors=(), original_stop_reason=None):
        self.result = result
        self.original_error = original_error
        self.operation = operation
        self.secondary_errors = tuple(secondary_errors)
        self.original_stop_reason = original_stop_reason
        super().__init__(f'Match execution failed during {operation}')


class _OutputFailure(Exception):
    def __init__(self, operation, error):
        self.operation, self.error = operation, error
        super().__init__('Local output failed')


class _OutputSink:
    def __init__(self, recorder):
        self.recorder = recorder
        self.errors = []

    def emit(self, operation, callback, *args):
        try:
            return callback(*args)
        except Exception as error:
            self.errors.append((operation, error))
            raise _OutputFailure(operation, error) from None

    def __getattr__(self, operation):
        # Only fixed recorder method names supplied by this driver reach here.
        return lambda *args: self.emit(operation, getattr(self.recorder, operation), *args)


@dataclass
class Outcome:
    parsed: BroadcastReply | CommitReply | None
    error: str = ''
    fatal: bool = False


async def _ask(agent: Agent, request: AgentRequest, ticket: Ticket, settings: MatchSettings,
               calls: list[dict], recorder) -> Outcome:
    outcome = Outcome(None, 'no_response')
    current = request
    try:
        for attempt in range(1, settings.max_attempts + 1):
            ticket.start()
            started = perf_counter()
            reply = None
            parsed = None
            error, fatal, retryable, retry_after, status_code = '', False, True, 0, None
            try:
                reply = await asyncio.wait_for(agent.respond(current), timeout=settings.timeout_seconds)
                if reply.status == 'refusal':
                    error, retryable = 'refusal', False
                elif reply.status != 'ok':
                    error = 'incomplete'
                else:
                    parsed = parse_reply(reply.text, request.phase, request.turn)
            except asyncio.CancelledError:
                ticket.settle(None)
                record = {'role': request.role, 'turn': request.turn, 'phase': request.phase,
                          'attempt': attempt, 'status': 'cancelled', 'usage': None,
                          'latency_seconds': round(perf_counter() - started, 4)}
                calls.append(record)
                if recorder:
                    try:
                        recorder.call(record)
                    except _OutputFailure:
                        pass  # Keep cancellation primary; the sink retains this failure.
                raise
            except TimeoutError:
                error = 'timeout'
            except ProviderError as exc:
                error, retryable, fatal = exc.code, exc.retryable, not exc.retryable
                retry_after, status_code = exc.retry_after, exc.status_code
            except ReplyValidationError as exc:
                error = str(exc)  # Fixed safe codes only, never response text.
            except Exception:
                error, fatal, retryable = 'internal_error', True, False
            ticket.settle(reply.usage if reply else None)
            record = {'role': request.role, 'turn': request.turn, 'phase': request.phase,
                      'attempt': attempt, 'status': error or 'ok', 'http_status': status_code,
                      'usage': asdict(reply.usage) if reply else None,
                      'latency_seconds': round(perf_counter() - started, 4)}
            calls.append(record)
            if recorder: recorder.call(record)
            if parsed is not None:
                return Outcome(parsed)
            outcome = Outcome(None, error, fatal)
            if not retryable or attempt == settings.max_attempts:
                break
            # Do not echo raw output, exceptions, or another player's context.
            repair = ('The previous response was incomplete or failed JSON validation. '
                      'Return only the exact schema with the current turn; respect character limits.')
            current = replace(request, repair=repair if error in {
                'incomplete', 'invalid_json_schema', 'stale_turn', 'response_size'
            } else '')
            await asyncio.sleep(max(settings.retry_delay_seconds * (2 ** (attempt - 1)), retry_after))
        return outcome
    finally:
        ticket.release()


async def _phase(agents: Mapping[str, Agent], requests: dict[str, AgentRequest], budget: Budget,
                 settings: MatchSettings, calls: list[dict], recorder) -> dict[str, Outcome]:
    tickets = budget.reserve_phase(requests)
    tasks = [asyncio.create_task(_ask(agents[r], requests[r], tickets[r], settings, calls, recorder)) for r in ROLES]
    try:
        outcomes = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return dict(zip(ROLES, outcomes))


async def run_match(agents: Mapping[str, Agent], settings: MatchSettings | None = None, *,
                    rates: dict[str, Rates | None] | None = None, recorder=None,
                    progress: Callable[[dict], None] | None = None) -> MatchResult:
    """Run one fresh room. The caller owns/cleans up provider clients.

    Fatal provider failures and budget stops leave the world at the last fully
    resolved turn. Interrupted runs are not scored as defeats. Histories are
    bounded and local to a role; providers never receive a WorldState.
    """
    if set(agents) != set(ROLES):
        raise ValueError('This slice requires exactly SPECTRA, PYRA and FLUX')
    settings = settings or MatchSettings()
    world = initial_world()
    budget = Budget(settings, rates or {})
    histories: dict[str, list[dict]] = {r: [] for r in ROLES}
    notes = dict.fromkeys(ROLES, '')
    failures = dict.fromkeys(ROLES, 0)
    calls: list[dict] = []
    records: list[dict] = []
    stop = 'turn_limit'
    cancelled = None
    primary = None
    phases = []
    output = _OutputSink(recorder)
    recorder = output if recorder is not None else None
    try:
        while world.turn < settings.max_turns and not (world.win or world.loss):
            observations = {r: observe(world, r) for r in ROLES}
            if recorder: recorder.begin_turn(world, observations)
            messages: tuple[ChatMessage, ...] = ()
            phase_names = ['broadcast'] + (['negotiate'] if settings.communication_rounds == 2 else []) + ['commit']
            abort = False
            outcomes: dict[str, Outcome] = {}
            for phase in phase_names:
                requests = {r: AgentRequest(
                    observations[r], phase, messages,
                    json.dumps(histories[r], separators=(',', ':')), notes[r],
                    max_output_tokens=settings.max_output_tokens,
                ) for r in ROLES}
                try:
                    outcomes = await _phase(agents, requests, budget, settings, calls, recorder)
                except BudgetExceeded as exc:
                    stop, abort = exc.reason, True
                    break
                for role, outcome in outcomes.items():
                    failures[role] = failures[role] + 1 if outcome.parsed is None else 0
                phase_record = {'turn': world.turn, 'phase': phase,
                                'statuses': {r: o.error or 'ok' for r, o in outcomes.items()}}
                if phase != 'commit':
                    published = tuple(ChatMessage(r, world.turn, phase,
                        o.parsed.message if isinstance(o.parsed, BroadcastReply) else '',
                        o.parsed is None) for r, o in outcomes.items())
                    messages += published
                    phase_record['messages'] = [asdict(m) for m in published]
                else:
                    # Publish only after the barrier, never as individual requests finish.
                    phase_record['sealed_actions'] = {
                        r: asdict(o.parsed.action.to_engine()) if isinstance(o.parsed, CommitReply)
                        else asdict(Action('WAIT')) for r, o in outcomes.items()}
                phases.append(phase_record)
                if recorder: recorder.phase(phase_record)
                if progress: output.emit('progress', progress, phase_record)
                if any(o.fatal for o in outcomes.values()):
                    stop = 'internal_error' if any(o.error == 'internal_error' for o in outcomes.values()) else 'provider_error'
                    abort = True
                    break
                if any(n >= settings.max_consecutive_failures for n in failures.values()):
                    stop, abort = 'unreliable_agent', True
                    break
            if abort:
                break
            actions = {r: o.parsed.action.to_engine() if isinstance(o.parsed, CommitReply) else Action('WAIT')
                       for r, o in outcomes.items()}
            after = resolve_turn(world, actions)
            for role, outcome in outcomes.items():
                if isinstance(outcome.parsed, CommitReply):
                    notes[role] = outcome.parsed.notes
            record = {
                'turn': world.turn + 1,
                'observations': {r: {'image': f'turn_{world.turn:02d}_{r.lower()}.png',
                                     'hud': obs.hud} for r, obs in observations.items()},
                'communications': [asdict(m) for m in messages],
                'sealed_actions': {r: asdict(a) for r, a in actions.items()},
                'private_notes': dict(notes),  # Privileged spectator output only.
                'fallbacks': {r: o.error for r, o in outcomes.items() if o.parsed is None},
                'events': after.events,
                'state_after': after.snapshot(),  # Never used to build player input.
            }
            records.append(record)
            previous_turn = world.turn
            world = after  # Commit the resolved world and its record before persistence.
            if recorder: recorder.turn(record)
            for role in ROLES:
                if settings.history_turns:
                    histories[role].append({
                        'turn': previous_turn, 'your_observation': observations[role].hud,
                        'public_messages': [asdict(m) for m in messages],
                        'your_action': asdict(actions[role]),
                        'events': public_events(after.events),
                    })
                    histories[role] = histories[role][-settings.history_turns:]
            world = after
        if world.win:
            stop = 'victory'
        elif world.loss:
            stop = 'defeat'
    except asyncio.CancelledError as error:
        stop, cancelled = 'cancelled', error
    except _OutputFailure as error:
        stop, primary = 'local_error', (error.operation, error.error)
    except Exception as error:
        stop, primary = 'internal_error', ('driver', error)
    result = MatchResult(world, stop, records, calls, budget.summary(), phases)
    original_stop_reason = stop
    secondary = list(output.errors)
    if primary is not None:
        secondary = [(op, error) for op, error in secondary if error is not primary[1]]
    if recorder:
        for attempt in range(2):
            try:
                output.recorder.finish(result)
                break
            except Exception as error:
                failures = (error.failures if isinstance(error, RecordingFinalizationError)
                            else (('finish', error),))
                for operation, cause in failures:
                    if primary is None and cancelled is None:
                        primary = ('finish:' + operation, cause)
                        result.stop_reason = 'local_error'
                    else:
                        secondary.append((operation, cause))
    if cancelled is not None:
        # Preserve the cancellation instance/type, even if cleanup failed.
        cancelled.result = result
        cancelled.secondary_errors = tuple(secondary)
        raise cancelled from None
    if primary is not None:
        raise MatchExecutionError(result, primary[1], primary[0], secondary,
                                  original_stop_reason) from None
    return result
