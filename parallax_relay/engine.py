"""Pure turn resolution: controls -> movement -> interactions -> victory.

Every round receives sealed actions concurrently. Controller effects can help
other players' movement in the SAME round; this is an intentional, public rule.
"""

from __future__ import annotations

from copy import deepcopy
from .state import (
    Action, WorldState, GAP, EXIT, ARTIFACT, ENERGY_CELL, MOTOR,
    MAX_TURNS, WIDTH,
)


def _move(world: WorldState, role: str, action: Action, events: list[str]) -> None:
    robot = world.robots[role]
    if action.direction not in (-1, 1) or action.steps not in (1, 2):
        events.append(f"{role}: invalid MOVE parameters; no movement")
        return
    destination = robot.x + action.direction * action.steps
    if not 0 <= destination < WIDTH:
        events.append(f"{role}: movement blocked by outer wall")
        return
    crossed = range(robot.x + action.direction, destination + action.direction, action.direction)
    if not world.bridge_extended and any(x in GAP for x in crossed):
        events.append(f"{role}: movement blocked by unbridged gap")
        return
    robot.x = destination
    events.append(f"{role}: moved to x={destination}")


def resolve_turn(world: WorldState, actions: dict[str, Action]) -> WorldState:
    if world.win or world.loss:
        raise ValueError("Cannot submit actions after the game ends")
    if set(actions) != set(world.robots):
        raise ValueError("Exactly one sealed action for each active robot is required")
    w = deepcopy(world)
    events: list[str] = []

    # Parameters are game legality, not a reason to retry a model response.
    # Keep caller-owned commitments intact for histories and spectator records.
    actions = dict(actions)
    for role, act in sorted(actions.items()):
        if act.kind in {'WAIT', 'VENT', 'REROUTE', 'COLLECT', 'UNLOCK'} and (
            act.direction != 0 or act.steps != 0
        ):
            events.append(f'{role}: invalid {act.kind} parameters; treated as WAIT')
            actions[role] = Action('WAIT')

    # 1. Controls: VENT precedes REROUTE, independent of agent order.
    for role, act in sorted(actions.items()):
        if act.kind != "VENT":
            continue
        if role != "PYRA" or abs(w.robots[role].x - MOTOR) > 1:
            events.append(f"{role}: VENT invalid (role/range)")
        elif w.coolant < 1:
            events.append(f"{role}: VENT failed; no coolant")
        else:
            w.coolant -= 1
            w.motor_heat = max(0, w.motor_heat - 3)
            events.append(f"{role}: vented motor; heat now {w.motor_heat}")

    for role, act in sorted(actions.items()):
        if act.kind != "REROUTE":
            continue
        if role != "FLUX" or abs(w.robots[role].x - MOTOR) > 1:
            events.append(f"{role}: REROUTE invalid (role/range)")
        elif w.bridge_extended:
            events.append(f"{role}: bridge already powered")
        elif w.energy < 2:
            events.append(f"{role}: REROUTE failed; insufficient energy")
        else:
            w.energy -= 2
            w.motor_heat += 2
            if w.motor_heat > 4:
                # A wrong decision has a meaningful, reproducible consequence.
                for victim in w.robots.values():
                    if abs(victim.x - MOTOR) <= 1:
                        victim.damage += 1
                events.append(f"{role}: motor overloaded; bridge did not extend; nearby robots damaged")
            else:
                w.bridge_extended = True
                events.append(f"{role}: bridge extended safely; energy now {w.energy}")

    # 2. Movement: collisions are not modeled in this first slice.
    for role, act in sorted(actions.items()):
        if act.kind == "MOVE":
            _move(w, role, act, events)

    # 3. Interactions: only available if on the correct tile.
    for role, act in sorted(actions.items()):
        if act.kind == "COLLECT":
            x = w.robots[role].x
            if role == "SPECTRA" and x == ARTIFACT and not w.shard_collected:
                w.shard_collected = True
                events.append("SPECTRA: memory shard recovered")
            elif role == "FLUX" and x == ENERGY_CELL and not w.cell_collected:
                w.cell_collected = True
                w.energy += 2
                events.append(f"FLUX: recovered energy cell; energy now {w.energy}")
            else:
                events.append(f"{role}: no collectable object available")
        elif act.kind == "UNLOCK":
            if role != "FLUX" or w.robots[role].x != EXIT:
                events.append(f"{role}: UNLOCK invalid (role/location)")
            elif w.exit_unlocked:
                events.append(f"{role}: exit already unlocked")
            elif w.energy < 1:
                events.append(f"{role}: insufficient energy to unlock exit")
            else:
                w.energy -= 1
                w.exit_unlocked = True
                events.append("FLUX: extraction hatch unlocked")
        elif act.kind not in {"MOVE", "VENT", "REROUTE", "WAIT", "COLLECT"}:
            events.append(f"{role}: unknown action '{act.kind}'; treated as WAIT")

    w.turn += 1
    w.win = bool(w.exit_unlocked and all(r.x == EXIT for r in w.robots.values()))
    w.loss = bool(w.turn >= MAX_TURNS and not w.win)
    if w.win:
        events.append("TEAM SUCCESS: all three robots extracted")
    elif w.loss:
        events.append("TEAM FAILURE: turn limit reached")
    w.events = events
    return w


def score(world: WorldState) -> dict[str, int]:
    """Team-first scoring: losing always scores at most 20 points/player."""
    if not world.win:
        # Partial score is deliberately small and doesn't depend on leakage-prone
        # free-form message judgment.
        return {
            role: 10 * int(role == "SPECTRA" and world.shard_collected)
                  + 10 * int(role == "PYRA" and all(r.damage == 0 for r in world.robots.values()))
                  + 10 * int(role == "FLUX" and world.energy >= 4)
            for role in world.robots
        }
    efficiency = max(0, 10 - max(0, world.turn - 7) * 2)
    clean = all(r.damage == 0 for r in world.robots.values())
    objectives = {
        "SPECTRA": world.shard_collected,
        "PYRA": clean,
        "FLUX": world.energy >= 4,
    }
    return {role: 60 + (30 if objectives[role] else 0) + efficiency for role in world.robots}
