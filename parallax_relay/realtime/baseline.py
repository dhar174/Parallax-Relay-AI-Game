"""Stream the native Split Span scripted match to the local spectator."""
from __future__ import annotations

import asyncio

from ..agents import ScriptedAgent
from ..config import MatchSettings
from ..orchestrator import MatchExecutionError, run_match
from ..protocol import AgentRequest, ModelReply, Observation, ROLES
from ..state import WorldState, public_events
from .physics import TILE
from .settings import Settings


# Synthetic response times apply inside the offline agents' actual concurrent calls.
_DELAYS = {'SPECTRA': 0.16, 'PYRA': 0.40, 'FLUX': 0.65}


class _PacedScriptedAgent(ScriptedAgent):
    def __init__(self, role: str, delay: float):
        super().__init__(role)
        self.delay = delay

    async def respond(self, request: AgentRequest) -> ModelReply:
        if self.delay:
            await asyncio.sleep(self.delay)
        return await super().respond(request)


class _BaselineRecorder:
    """Project native recorder callbacks onto the spectator's event contract."""

    def __init__(self, session):
        self.session = session
        self.facing = dict.fromkeys(ROLES, 1)

    def _world(self, snapshot: dict) -> dict:
        # The native game occupies a level lane and resolves whole tiles at once.
        return {
            'tick': snapshot['turn'],
            'robots': {
                role: {'x': robot['x'] * TILE, 'y': 0, 'vx': 0, 'vy': 0,
                       'grounded': True, 'facing': self.facing[role], 'pose': 'idle'}
                for role, robot in snapshot['robots'].items()
            },
            'bridge_powered': snapshot['bridge_extended'], 'heat': snapshot['motor_heat'],
            'shard_collected': snapshot['shard_collected'], 'cell_collected': snapshot['cell_collected'],
            'exit_unlocked': snapshot['exit_unlocked'], 'energy': snapshot['energy'],
            'coolant': snapshot['coolant'], 'completed': snapshot['win'],
        }

    def begin_turn(self, world: WorldState, observations: dict[str, Observation]) -> None:
        if world.turn == 0:
            self.session.emit('state', tick=0, window=0, world=self._world(world.snapshot()))
        window = world.turn + 1
        for role, observation in observations.items():
            self.session.store_feed(role, window, observation.image_png)
            self.session.emit('observation', tick=world.turn, window=window, role=role)

    def phase_event(self, event: dict) -> None:
        tick = event['turn']
        window = tick + 1
        if event['kind'] == 'phase_open':
            self.session.emit('phase_open', tick=tick, sample_tick=tick, window=window, phase=event['phase'])
        elif event['kind'] == 'ready':
            self.session.emit('ready', tick=tick, sample_tick=tick, window=window, phase=event['phase'],
                              role=event['role'], disposition=event['disposition'])

    def phase(self, record: dict) -> None:
        # The orchestrator calls this once with the complete roster-ordered batch.
        for message in record.get('messages', ()):
            if message['text']:
                self.session.emit('dialogue', tick=record['turn'], window=record['turn'] + 1,
                                  phase=record['phase'], role=message['role'], text=message['text'])
        self.session.emit('phase_closed', tick=record['turn'], sample_tick=record['turn'],
                          window=record['turn'] + 1, phase=record['phase'], statuses=dict(record['statuses']))

    def turn(self, record: dict) -> None:
        tick = record['turn']
        # A tile turn is instantaneous. Advertise its release only after the
        # native engine has committed the resolution, then publish its state.
        self.session.emit('window_started', tick=tick, window=tick, start_tick=tick,
                          starts=dict.fromkeys(ROLES, tick),
                          plans={r: [dict(action)] for r, action in record['sealed_actions'].items()},
                          dispositions={r: record['fallbacks'].get(r, 'ok') for r in ROLES},
                          sources={r: {'source': 'scripted_fixture'} for r in ROLES})
        for role, action in record['sealed_actions'].items():
            if action['kind'] == 'MOVE' and record['action_outcomes'][role] == 'applied':
                self.facing[role] = action['direction']
        world = self._world(record['state_after'])
        self.session.emit('state', tick=tick, window=tick, world=world)
        for text in public_events(record['events']):
            speaker = text.partition(':')[0]
            if speaker in ROLES:
                self.session.emit('consequence', tick=tick, window=tick, role=speaker, text=text,
                                  event_kind=record['sealed_actions'][speaker]['kind'].lower())
            else:
                self.session.emit('consequence', tick=tick, window=tick, text=text, event_kind='team_outcome')
        self.session.emit('checkpoint', tick=tick, window=tick, world=world)

    def call(self, record: dict) -> None:
        # The session routes attempts (including measured latency) to its private journal.
        self.session.emit('attempt', window=record['turn'] + 1, sample_tick=record['turn'], **record)

    def finish(self, result) -> None:
        """The session owner publishes one result after run_match returns."""


async def run_baseline(session, settings: Settings, *, paced: bool = True) -> tuple[str, bool]:
    """Run the offline tile fixture to its native turn bound and report its outcome."""
    recorder = _BaselineRecorder(session)
    agents = {role: _PacedScriptedAgent(role, _DELAYS[role] if paced else 0) for role in ROLES}
    match = MatchSettings(communication_rounds=settings.communication_rounds,
                          timeout_seconds=settings.phase_timeout_seconds)
    try:
        result = await run_match(agents, match, recorder=recorder, phase_event=recorder.phase_event)
    except MatchExecutionError as error:
        result = error.result
    finally:
        await asyncio.gather(*(agent.close() for agent in agents.values()))
    return result.stop_reason, result.world.win or result.world.loss
