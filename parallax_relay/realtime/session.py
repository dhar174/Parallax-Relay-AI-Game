"""Run one fresh local match. Only this driver can advance its physics clock."""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
import json
import math
from pathlib import Path
from threading import Event, Lock, Thread
import time

from ..protocol import ROLES
from ..provenance import collect_environment, collect_source
from ..rooms import get_room
from .coordination import Coordinator, CoordinationStop, FULL_PHASES, REDUCED_PHASES
from .flux_view import render_circuit_relief
from .journal import Journal
from .manual import ManualAgent, ManualControls
from .observations import observe, sample_flux_circuit, sample_pyra_thermal
from .physics import initial_world, step
from .players import ReactiveAgent
from .pyra_view import render_thermal_bloom
from .settings import make_live_agents
from .wire import contract_identity


_ILLUSTRATIONS = {
    'FLUX': (sample_flux_circuit, render_circuit_relief),
    'PYRA': (sample_pyra_thermal, render_thermal_bloom),
}


class Session:
    def __init__(self, out: Path, mode, settings, *, profile=None, paced=True, latency='demo', run_id=None,
                 outer_deadline=None):
        if mode not in {'reactive', 'manual', 'baseline', 'test', 'live'}:
            raise ValueError('Unknown source')
        if (mode == 'live') != (profile is not None):
            raise ValueError('Live execution requires the named live profile')
        if profile is not None and settings != profile.settings:
            raise ValueError('Live settings must match the named profile')
        if outer_deadline is not None and (mode != 'live' or not math.isfinite(outer_deadline)):
            raise ValueError('Expected a finite live supervisor deadline')
        self.mode = mode
        self.settings = settings
        self.profile = profile
        self._outer_deadline = outer_deadline
        if latency not in ('demo', 'historical') or (latency == 'historical' and mode != 'test'):
            raise ValueError('Measured latency replay requires the offline transport fixture')
        self.latency = latency
        self.paced = paced
        self.journal = Journal(out, run_id=run_id)
        self.world = initial_world()
        self._durable_view = self.world.snapshot() if mode != 'baseline' else None
        self._start_lock = Lock()
        self._done = Event()
        self._closing = Event()
        self._thread = None
        self._loop = None
        self._task = None
        self.result = None
        self.window = 0
        self._started_at = None
        self._budget = None
        self._controls = ManualControls(settings, self.emit)
        self._sample_descriptions = {}
        self._illustrated_samples = {}
        self._latest_view = None
        self._feedback = {role: deque(maxlen=6) for role in ROLES}
        if mode != 'baseline':
            self.journal.record_initial(self.world)
        self.emit('match', mode=mode, room='Split Span' if mode == 'baseline' else 'Raised Span',
                  window_ticks=1 if mode == 'baseline' else settings.window_ticks,
                  action_points=0 if mode == 'baseline' else settings.action_points,
                  max_windows=12 if mode == 'baseline' else settings.max_windows,
                  sources={r: self._source(r) for r in ROLES},
                  tick_rate=settings.tick_rate, clock_mode=settings.clock_mode)
        if mode != 'baseline':
            self.emit('state', world=self._durable_view)
        self.journal.private('configuration', version=1, settings=settings.model_dump(), latency=latency,
                             room_version='split-span-turn-v1' if mode == 'baseline' else 'raised-span-physics-v1',
                             contract=None if mode == 'baseline' else contract_identity(),
                             source=collect_source(Path(__file__).resolve().parents[2]),
                             environment=collect_environment(),
                             players={r: self._source(r) for r in ROLES},
                             rates={r: v.model_dump() for r, v in profile.rates.items()} if profile else {})

    def _source(self, role):
        if self.profile:
            player = self.profile.players[role]
            return {'source': 'live_model', 'provider': player.provider, 'model': player.model}
        if self.mode == 'test':
            from .fixture_transport import FIXTURE_ROSTER
            provider, model = FIXTURE_ROSTER[role]
            return {'source': 'offline_test_transport', 'provider': provider, 'model': model}
        return {'source': {'baseline': 'scripted_fixture', 'manual': 'manual',
                           'reactive': 'reactive_local'}[self.mode]}

    def emit(self, kind, **data):
        if self._started_at is not None:
            data.setdefault('wall_seconds', round(time.monotonic() - self._started_at, 6))
        if kind in ('attempt_started', 'attempt'):
            self.journal.private(kind, **data)
            return
        if kind == 'dialogue':
            data['source'] = ('reactive_local' if self.mode == 'manual'
                              else self._source(data['role'])['source'])
        self.journal.emit(kind, **data)
        if kind == 'state':
            self._latest_view = data['world']
        if self.mode == 'manual' and kind == 'ready' and data.get('phase') == 'commit':
            self._controls.admitted(data['role'], data['window'], data['status'])

    def events(self, after):
        recording_error = self._done.is_set() and self.result.get('recording_error')
        page = self.journal.events(after)
        if recording_error:
            page['recording_error'] = True
            page['last_recorded_world'] = self._durable_view if self.mode != 'baseline' else self._latest_view
        return page

    def store_feed(self, role, window, png):
        self.journal.store_feed(role, window, png)
        if role in _ILLUSTRATIONS and self.mode != 'baseline':
            project, _ = _ILLUSTRATIONS[role]
            self._illustrated_samples[role, window] = project(self.world)
        view = self._latest_view if self.mode == 'baseline' else self.world.snapshot()
        room = get_room('split_span')
        if role == 'PYRA':
            details = f"Thermal reading {view['heat']} at motor column {room.bridges[0].motor}."
        elif role == 'FLUX':
            cell = 'recovered' if view['cell_collected'] else f'at column {room.cells[0]}'
            details = f"Circuit from motor column {room.bridges[0].motor} to the bridge. Energy cell {cell}."
        else:
            shard = 'recovered' if view['shard_collected'] else f'at column {room.shard}'
            details = f"Optical console at column {room.bridges[0].motor}. Memory shard {shard}."
        deck = 'extended' if view['bridge_powered'] else 'retracted'
        positions = ', '.join(f"{name} at {min(12, max(0, (robot['x'] + 128) // 256))}"
                              for name, robot in view['robots'].items())
        self._sample_descriptions[role, window] = (
            f'{role} horizontal sensor, window {window}. {positions}. Bridge {deck}. {details}')

    def feed_description(self, role, window):
        return self._sample_descriptions.get((role, window), '')

    def feed(self, role, window):
        return self.journal.feed(role, window)

    def illustrated_feed(self, role, window):
        sample = self._illustrated_samples.get((role, window))
        if sample is None:
            return None
        _, render = _ILLUSTRATIONS[role]
        return render(sample)

    def status(self):
        return {'mode': self.mode, 'status': 'ended' if self._done.is_set() else
                'running' if self._thread else 'idle', 'run_id': self.journal.run_id,
                'window_ticks': 1 if self.mode == 'baseline' else self.settings.window_ticks,
                'action_points': 0 if self.mode == 'baseline' else self.settings.action_points}

    def submit(self, data):
        if self.mode != 'manual':
            return {'ok': False, 'error': 'Manual input is available in a manual run.'}
        return self._controls.submit(data)

    def start(self):
        with self._start_lock:
            if self._thread is not None or self._closing.is_set():
                return False
            self._thread = Thread(target=self._worker, name='parallax-match', daemon=True)
            self._thread.start()
            return True

    def wait(self):
        self._done.wait()
        return self.result.copy()

    def close(self):
        self._closing.set()
        with self._start_lock:
            loop, task, worker = self._loop, self._task, self._thread
        if loop and task and not self._done.is_set():
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(task.cancel)
        if worker:
            worker.join(timeout=self.settings.cleanup_seconds)

    def _worker(self):
        try:
            asyncio.run(self._run())
        finally:
            self._done.set()

    def _write_result(self):
        path = self.journal.out / 'result.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.result, indent=2), encoding='utf-8')
        temporary.replace(path)

    async def _run(self):
        self._started_at = time.monotonic()
        deadline = self._started_at + self.settings.wall_seconds
        if self._outer_deadline is not None:
            deadline = min(deadline, self._outer_deadline)
        with self._start_lock:
            self._loop, self._task = asyncio.get_running_loop(), asyncio.current_task()
        reason, completed = 'internal_error', False
        try:
            if self._closing.is_set():
                raise asyncio.CancelledError
            if self._started_at >= deadline:
                raise CoordinationStop('time_limit')
            if self.mode == 'baseline':
                from .baseline import run_baseline
                reason, completed = await run_baseline(self, self.settings, paced=self.paced)
            else:
                reason = await self._play_physics(deadline)
                completed = self.world.completed
        except CoordinationStop as exc:
            reason = exc.reason
            completed = self.world.completed
        except asyncio.CancelledError:
            reason = 'cancelled'
        except OSError:
            reason = 'local_error'
        except Exception as exc:
            # Untrusted provider details and exceptional text never enter the UI.
            try:
                self.journal.private('host_failure', error_type=type(exc).__name__)
            except (OSError, RuntimeError):
                pass
        finally:
            self._controls.close()
            final_view = self._durable_view if self.mode != 'baseline' else self._latest_view
            if self.mode != 'baseline':
                completed = final_view['completed']
            self.result = {'run_id': self.journal.run_id, 'stop_reason': reason,
                           'completed': completed, 'tick': self.journal.tick,
                           'window': self.journal.window, 'mode': self.mode}
            try:
                if self.mode != 'baseline':
                    self.journal.finish(reason)
                if self._budget is not None:
                    self.journal.private('budget', summary=self._budget.summary())
                self._write_result()
                # Journal.emit attaches the identity after validating reserved fields.
                self.emit('result', world=final_view, **{k: v for k, v in self.result.items() if k != 'run_id'})
            except (OSError, RuntimeError):
                self.result.update(stop_reason='local_error', simulation_stop=reason, recording_error=True)
                with suppress(OSError):
                    self._write_result()

    async def _play_physics(self, deadline):
        delays = (0.15, 0.85, 0.45) if self.paced else (0., 0., 0.)
        if self.profile:
            agents = make_live_agents(self.profile)
        elif self.mode == 'test':
            from .fixture_transport import fixture_agents, historical_delays
            if self.latency == 'historical':
                delays = historical_delays(scale=1.0)
            agents = fixture_agents(self.settings, delays)
        else:
            agents = {role: ReactiveAgent(role, delay_seconds=delay) for role, delay in zip(ROLES, delays)}
            if self.mode == 'manual':
                agents = {r: ManualAgent(agent, self._controls) for r, agent in agents.items()}
        phases = FULL_PHASES if self.settings.communication_rounds == 2 else REDUCED_PHASES
        coordinator = Coordinator(agents, self.settings, self.profile.rates if self.profile else {},
                                  self.emit, phases=phases, run_id=self.journal.run_id)
        self._budget = coordinator.budget
        try:
            for window in range(1, self.settings.max_windows + 1):
                if time.monotonic() >= deadline:
                    raise CoordinationStop('time_limit')
                self.window = window
                sample_tick = self.world.tick
                observations = {r: observe(self.world, r, window, self.settings,
                                           consequences=self._feedback[r]) for r in ROLES}
                for role, sample in observations.items():
                    self.store_feed(role, window, sample.image_png)
                    self.journal.private('role_observation', role=role, sample_window=window, hud=sample.hud)
                    self.emit('observation', role=role, window=window, tick=self.world.tick)
                programs, _ = await self._coordinate(coordinator, observations, window, deadline)
                self.journal.private('private_notes', notes=coordinator.notes)
                started_at = time.monotonic()
                largest_lag = 0.
                for offset in range(self.settings.window_ticks):
                    due = started_at + offset / self.settings.tick_rate
                    if self.paced:
                        await asyncio.sleep(max(0, due - time.monotonic()))
                        largest_lag = max(largest_lag, time.monotonic() - due)
                    if time.monotonic() >= deadline:
                        raise CoordinationStop('time_limit')
                    self._step(programs, offset, release=coordinator.dispositions if offset == 0 else None,
                               sample_tick=sample_tick)
                    if self.world.completed:
                        break
                self.emit('checkpoint', window=window, tick=self.world.tick, world=self.world.snapshot())
                self.journal.private('pacing', period='action', max_lag_seconds=largest_lag,
                                     ticks=offset + 1, seconds=time.monotonic() - started_at)
                if self.world.completed:
                    return 'checkpoint'
            return 'window_limit'
        finally:
            cleanup_deadline = time.monotonic() + self.settings.cleanup_seconds
            drained = await coordinator.close(timeout=self.settings.cleanup_seconds)
            closers = [asyncio.create_task(agent.close()) for agent in agents.values()]
            done, pending = await asyncio.wait(closers, timeout=max(0, cleanup_deadline - time.monotonic()))
            for task in pending:
                task.cancel()
            for task in done:
                if not task.cancelled():
                    task.exception()
            self.journal.private('cleanup', attempts_drained=drained, clients_outstanding=len(pending))

    async def _coordinate(self, coordinator, observations, window, deadline):
        if self.settings.clock_mode == 'freeze':
            return await coordinator.coordinate(observations, window, deadline)
        intake = asyncio.create_task(coordinator.coordinate(observations, window, deadline))
        neutral = {role: [] for role in ROLES}
        period = 1 / self.settings.tick_rate
        next_tick = time.monotonic() + period
        initial_tick = self.world.tick
        largest_lag = 0.
        try:
            closed_at = None
            while True:
                if closed_at is None:
                    await asyncio.wait({intake}, timeout=max(0., next_tick - time.monotonic()))
                    if intake.done():
                        intake.result()  # A fatal or cancelled phase cannot release controls.
                        closed_at = time.monotonic()
                horizon = closed_at if closed_at is not None else time.monotonic()
                if time.monotonic() >= deadline:
                    raise CoordinationStop('time_limit')
                for _ in range(4):
                    if next_tick > horizon:
                        break
                    largest_lag = max(largest_lag, time.monotonic() - next_tick)
                    self._step(neutral, 0)
                    next_tick += period
                    if self.world.completed:
                        raise CoordinationStop('checkpoint')
                if closed_at is not None and next_tick > closed_at:
                    break
                await asyncio.sleep(0)
            return await intake
        finally:
            if not intake.done():
                intake.cancel()
                with suppress(asyncio.CancelledError, CoordinationStop):
                    await intake
            self.journal.private('pacing', period='discussion', max_lag_seconds=largest_lag,
                                 ticks=self.world.tick - initial_tick)

    def _step(self, programs, offset, *, release=None, sample_tick=None):
        consequences = step(self.world, programs, offset)
        self.journal.record_tick(self.world, programs, offset)
        self._durable_view = self.world.snapshot()
        tick = self.world.tick
        if release is not None:
            self.emit('window_started', window=self.window, tick=tick, start_tick=tick,
                      plans=programs, dispositions=release,
                      starts={r: tick for r in ROLES}, sources={r: self._source(r) for r in ROLES},
                      sample_tick=sample_tick, observation_age_ticks=tick - 1 - sample_tick)
        if release is not None or consequences or tick % 3 == 0:
            self.emit('state', window=self.window, tick=tick, world=self._durable_view)
        for consequence in consequences:
            if consequence.get('role') in self._feedback:
                self._feedback[consequence['role']].append(consequence)
            payload = dict(consequence)
            event_kind = payload.pop('kind')
            self.emit('consequence', window=self.window, event_kind=event_kind, **payload)
