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


def _move(world: WorldState, role: str, action: Action, events: list[str], diagnostics: dict) -> None:
    robot = world.robots[role]
    if action.direction not in (-1, 1) or action.steps not in (1, 2):
        events.append(f"{role}: invalid MOVE parameters; no movement")
        diagnostics[role] = 'invalid_parameters'
        return
    destination = robot.x + action.direction * action.steps
    if not 0 <= destination < world.room.width:
        events.append(f"{role}: movement blocked by outer wall")
        diagnostics[role] = 'outer_wall'
        return
    crossed = range(robot.x + action.direction, destination + action.direction, action.direction)
    if any(f'bridge_{i}' not in world.powered_bridges and any(x in bridge.gap for x in crossed)
           for i,bridge in enumerate(world.room.bridges)):
        events.append(f"{role}: movement blocked by unbridged gap")
        diagnostics[role] = 'unbridged_gap'
        return
    robot.x = destination
    diagnostics[role] = 'applied'
    events.append(f"{role}: moved to x={destination}")


def resolve_turn(world: WorldState, actions: dict[str, Action], *, diagnostics: dict | None = None) -> WorldState:
    if world.win or world.loss:
        raise ValueError("Cannot submit actions after the game ends")
    if set(actions) != set(world.robots):
        raise ValueError("Exactly one sealed action for each active robot is required")
    w = deepcopy(world)
    events: list[str] = []
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.clear()
    diagnostics.update({role: 'wait' if act.kind == 'WAIT' else 'applied' for role, act in actions.items()})

    # Parameters are game legality, not a reason to retry a model response.
    # Keep caller-owned commitments intact for histories and spectator records.
    actions = dict(actions)
    for role, act in sorted(actions.items()):
        if act.kind in {'WAIT', 'VENT', 'REROUTE', 'COLLECT', 'UNLOCK'} and (
            act.direction != 0 or act.steps != 0
        ):
            events.append(f'{role}: invalid {act.kind} parameters; treated as WAIT')
            diagnostics[role] = 'invalid_parameters'
            actions[role] = Action('WAIT')

    def controller(role):
        return next(((f'bridge_{i}',b) for i,b in enumerate(w.room.bridges)
                     if abs(w.robots[role].x-b.motor)<=1),None)

    # 1. Controls: VENT precedes REROUTE, independent of agent order.
    for role, act in sorted(actions.items()):
        if act.kind != "VENT":
            continue
        target=controller(role)
        if role != "PYRA" or target is None:
            events.append(f"{role}: VENT invalid (role/range)")
            diagnostics[role] = 'role_or_range'
        elif w.coolant < 1:
            events.append(f"{role}: VENT failed; no coolant")
            diagnostics[role] = 'insufficient_resource'
        else:
            w.coolant -= 1
            key,_=target
            w.motor_heats[key] = max(0, w.motor_heats[key] - 3)
            events.append(f"{role}: vented motor; heat now {w.motor_heats[key]}")

    for role, act in sorted(actions.items()):
        if act.kind != "REROUTE":
            continue
        target=controller(role)
        if role != "FLUX" or target is None:
            events.append(f"{role}: REROUTE invalid (role/range)")
            diagnostics[role] = 'role_or_range'
        elif target[0] in w.powered_bridges:
            events.append(f"{role}: bridge already powered")
            diagnostics[role] = 'already_done'
        elif w.energy < 2:
            events.append(f"{role}: REROUTE failed; insufficient energy")
            diagnostics[role] = 'insufficient_resource'
        else:
            w.energy -= 2
            key,bridge=target
            w.motor_heats[key] += 2
            if w.motor_heats[key] > 4:
                diagnostics[role] = 'overload'
                # A wrong decision has a meaningful, reproducible consequence.
                for victim in w.robots.values():
                    if abs(victim.x - bridge.motor) <= 1:
                        victim.damage += 1
                events.append(f"{role}: motor overloaded; bridge did not extend; nearby robots damaged")
            else:
                w.powered_bridges.add(key)
                events.append(f"{role}: bridge extended safely; energy now {w.energy}")

    # 2. Movement: collisions are not modeled in this first slice.
    for role, act in sorted(actions.items()):
        if act.kind == "MOVE":
            _move(w, role, act, events, diagnostics)

    # 3. Interactions: only available if on the correct tile.
    for role, act in sorted(actions.items()):
        if act.kind == "COLLECT":
            x = w.robots[role].x
            if role == "SPECTRA" and x == w.room.shard and not w.shard_collected:
                w.shard_collected = True
                events.append("SPECTRA: memory shard recovered")
            elif role == "FLUX" and x in w.room.cells and x not in w.collected_cells:
                w.collected_cells.add(x)
                w.energy += w.room.cell_value
                events.append(f"FLUX: recovered energy cell; energy now {w.energy}")
            else:
                events.append(f"{role}: no collectable object available")
                diagnostics[role] = 'nothing_to_collect'
        elif act.kind == "UNLOCK":
            if role != "FLUX" or w.robots[role].x != w.room.exit:
                events.append(f"{role}: UNLOCK invalid (role/location)")
                diagnostics[role] = 'role_or_range'
            elif w.exit_unlocked:
                events.append(f"{role}: exit already unlocked")
                diagnostics[role] = 'already_done'
            elif w.energy < 1:
                events.append(f"{role}: insufficient energy to unlock exit")
                diagnostics[role] = 'insufficient_resource'
            else:
                w.energy -= 1
                w.exit_unlocked = True
                events.append("FLUX: extraction hatch unlocked")
        elif act.kind not in {"MOVE", "VENT", "REROUTE", "WAIT", "COLLECT"}:
            events.append(f"{role}: unknown action '{act.kind}'; treated as WAIT")
            diagnostics[role] = 'unknown_action'

    w.turn += 1
    w.win = bool(w.exit_unlocked and all(r.x == w.room.exit for r in w.robots.values())
                 and (not w.room.requires_shard or w.shard_collected))
    w.loss = bool(w.turn >= w.room.deadline and not w.win)
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
