"""Game state definitions. Only the engine holds a WorldState.

Agents must receive per-agent observations; WorldState is privileged and must
NEVER be serialized directly into a player request.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Literal
from .rooms import RoomDefinition, get_room

WIDTH = 13
MAX_TURNS = 12
GAP = frozenset({5, 6, 7})
EXIT = 12
ARTIFACT = 9
ENERGY_CELL = 10
MOTOR = 4

Role = Literal["SPECTRA", "PYRA", "FLUX", "ECHO"]

PRIVATE_GOALS = {
    "SPECTRA": "Recover the memory shard before team extraction.",
    "PYRA": "Finish the mission without any robot sustaining thermal damage.",
    "FLUX": "Finish team extraction with at least 4 energy units remaining.",
}


@dataclass(frozen=True)
class Action:
    kind: str
    direction: int = 0  # MOVE: -1 or +1
    steps: int = 0      # MOVE: 1 or 2 tiles


@dataclass
class Robot:
    role: str
    x: int
    damage: int = 0


@dataclass(init=False)
class WorldState:
    turn: int
    robots: dict[str, Robot]
    energy: int = 6
    coolant: int = 2
    exit_unlocked: bool = False
    shard_collected: bool = False
    win: bool = False
    loss: bool = False
    events: list[str] = field(default_factory=list)
    room: RoomDefinition
    motor_heats: dict[str,int]
    powered_bridges: set[str]
    collected_cells: set[int]

    def __init__(self,turn,robots,energy=6,coolant=2,motor_heat=None,bridge_extended=False,
                 exit_unlocked=False,shard_collected=False,cell_collected=False,win=False,loss=False,
                 events=None,*,room=None):
        self.room=room or get_room()
        self.turn,self.robots,self.energy,self.coolant=turn,robots,energy,coolant
        self.exit_unlocked,self.shard_collected,self.win,self.loss=exit_unlocked,shard_collected,win,loss
        self.events=list(events or [])
        self.motor_heats={f'bridge_{i}':b.heat for i,b in enumerate(self.room.bridges)}
        self.powered_bridges=set();self.collected_cells=set()
        if motor_heat is not None:self.motor_heat=motor_heat
        if bridge_extended:self.bridge_extended=True
        if cell_collected:self.cell_collected=True

    def _single_bridge(self):
        if len(self.room.bridges)!=1:raise ValueError('Use per-controller state for relay rooms')
        return 'bridge_0'

    @property
    def motor_heat(self):return self.motor_heats[self._single_bridge()]
    @motor_heat.setter
    def motor_heat(self,value):self.motor_heats[self._single_bridge()]=value
    @property
    def bridge_extended(self):return self._single_bridge() in self.powered_bridges
    @bridge_extended.setter
    def bridge_extended(self,value):
        key=self._single_bridge()
        if value:self.powered_bridges.add(key)
        else:self.powered_bridges.discard(key)
    @property
    def cell_collected(self):return set(self.room.cells)<=self.collected_cells
    @cell_collected.setter
    def cell_collected(self,value):
        if value:self.collected_cells.update(self.room.cells)
        else:self.collected_cells.clear()

    def snapshot(self) -> dict:
        """Privileged internal snapshot, for spectator/replay/tests ONLY."""
        value={'turn':self.turn,'robots':{r:asdict(v) for r,v in self.robots.items()},
               'energy':self.energy,'coolant':self.coolant,'exit_unlocked':self.exit_unlocked,
               'shard_collected':self.shard_collected,'win':self.win,'loss':self.loss,'events':list(self.events),
               'room_id':self.room.id,'room_version':self.room.version,'motor_heats':dict(self.motor_heats),
               'powered_bridges':sorted(self.powered_bridges),'collected_cells':sorted(self.collected_cells)}
        if len(self.room.bridges)==1:
            value.update(motor_heat=self.motor_heat,bridge_extended=self.bridge_extended,cell_collected=self.cell_collected)
        return value


def initial_world(room_id: str='split_span') -> WorldState:
    room=get_room(room_id)
    return WorldState(turn=0,robots={r:Robot(r,x) for r,x in zip(('SPECTRA','PYRA','FLUX'),room.starts)},
                      energy=room.energy,coolant=room.coolant,room=room)


def public_hud(world: WorldState, role: str) -> dict:
    """Non-sensitive text provided to a player. Sensory facts stay in PNG."""
    if role not in world.robots:
        raise ValueError(f"Unknown active role: {role}")
    return {
        "turn": world.turn,
        "max_turns": MAX_TURNS,
        "shared_energy": world.energy,
        "shared_coolant": world.coolant,
        "your_role": role,
        "your_x": world.robots[role].x,
        "teammate_positions": {
            r: agent.x for r, agent in world.robots.items() if r != role
        },
        "your_private_goal": PRIVATE_GOALS[role],
        "shared_goal": "Unlock exit at x=12 and extract all three robots by the end of round 12.",
        "action_contract": {
            "MOVE": "direction must be -1 or 1; steps must be 1 or 2",
            "VENT": "PYRA only, if adjacent to motor x=4; costs 1 coolant",
            "REROUTE": "FLUX only, if adjacent to console x=4; costs 2 energy",
            "COLLECT": "SPECTRA can collect a shard at its current tile; FLUX can collect an energy cell at its current tile. Locate items through sensors or messages.",
            "UNLOCK": "FLUX at x=12; costs 1 energy",
            "WAIT": "Do nothing",
        },
        "recent_events": public_events(world.events),
    }


def public_events(events: list[str]) -> list[str]:
    """Public action consequences, excluding the exact thermal sensor reading.

    Engine-produced events contain actions and visible outcomes. New engine
    event types must be audited here before being exposed to players.
    """
    return [re.sub(r"; heat now -?\d+", "", event) for event in events[-12:]]
