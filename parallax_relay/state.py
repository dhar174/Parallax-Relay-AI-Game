"""Game state definitions. Only the engine holds a WorldState.

Agents must receive per-agent observations; WorldState is privileged and must
NEVER be serialized directly into a player request.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Literal

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


@dataclass
class WorldState:
    turn: int
    robots: dict[str, Robot]
    energy: int = 6
    coolant: int = 2
    motor_heat: int = 4
    bridge_extended: bool = False
    exit_unlocked: bool = False
    shard_collected: bool = False
    cell_collected: bool = False
    win: bool = False
    loss: bool = False
    events: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        """Privileged internal snapshot, for spectator/replay/tests ONLY."""
        return asdict(self)


def initial_world() -> WorldState:
    return WorldState(turn=0, robots={
        "SPECTRA": Robot(role="SPECTRA", x=2),
        "PYRA": Robot(role="PYRA", x=3),
        "FLUX": Robot(role="FLUX", x=4),
    })


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
