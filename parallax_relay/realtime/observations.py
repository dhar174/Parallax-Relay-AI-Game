"""One-way projection from the development room to a single player's sensors."""

import json

from ..protocol import Observation, ROLES
from ..render import render_png
from ..rooms import get_room
from ..state import Robot as SchematicRobot, WorldState
from . import physics
from .flux_view import CircuitSample
from .wire import ACTION_COST, MAX_COMMANDS, MAX_RUN_TICKS, RUN_TICKS_PER_POINT


HUD_VERSION = 'realtime-hud-v1'
_SCHEMATIC = get_room('split_span')
_GOALS = {
    'SPECTRA': 'Recover the memory shard that your optical sensor marks.',
    'PYRA': 'Read the thermal ring and vent the motor when it needs cooling.',
    'FLUX': 'Power the bridge and recover the optional energy cell on your circuit display.',
}
_MOTION = {
    'takeoff': 'You jumped.', 'landing': 'You landed.',
    'side_contact': 'Your drive met a vertical face.', 'underside_contact': 'Your ascent hit an underside.',
    'fell': 'You fell below the room.', 'respawn': 'You returned to your safe checkpoint.',
}
_INTERACTION = {
    ('PYRA', 'vented'): 'You vented the motor.', ('FLUX', 'rerouted'): 'You powered the deck.',
    ('SPECTRA', 'shard_collected'): 'You recovered the shard.',
    ('FLUX', 'cell_collected'): 'You recovered the energy cell.',
}
_SURFACES = {'left_bank': 'starting bank', 'far_bank': 'raised bank', 'deck': 'bridge deck',
             'left_wall': 'left wall', 'right_wall': 'right wall'}


def _recent_consequences(events, role, sample_tick):
    rows = []
    for event in reversed(events):
        if event.get('role') != role:
            continue
        tick, kind = event.get('tick'), event.get('kind')
        if type(tick) is not int or not 1 <= tick <= sample_tick or type(kind) is not str:
            continue
        text = _MOTION.get(kind) or _INTERACTION.get((role, kind))
        if kind == 'blocked':
            action = event.get('action')
            if action in ('JUMP', 'COLLECT', 'VENT', 'REROUTE'):
                text = f'Your {action} attempt was blocked.'
        if text is None:
            continue
        surface = event.get('surface')
        if kind in ('landing', 'side_contact', 'underside_contact') and isinstance(surface, str) and surface in _SURFACES:
            text += f' Contact with the {_SURFACES[surface]}.'
        rows.append({'tick': tick, 'kind': kind, 'text': text})
        if len(rows) == 6:
            break
    return list(reversed(rows))


def _column(x: int) -> int:
    nearest = (x + physics.TILE // 2) // physics.TILE
    return max(0, min(_SCHEMATIC.width - 1, nearest))


def _schematic_columns(world: physics.World):
    return tuple(_column(world.robots[name].x) for name in ROLES)


def sample_flux_circuit(world: physics.World) -> CircuitSample:
    """Freeze the same columns, circuit state and own height available to FLUX."""
    return CircuitSample(_schematic_columns(world), world.robots['FLUX'].y,
                         world.bridge_powered, world.cell_collected)


def _image(world: physics.World, role: str, window: int) -> bytes:
    # The same public silhouettes appear on every schematic. Only the requested
    # sensor receives its own heat or item state; exact kinematics belong below.
    robots = {name: SchematicRobot(name, column) for name, column in zip(ROLES, _schematic_columns(world))}
    schematic = WorldState(
        turn=window, robots=robots, room=_SCHEMATIC,
        bridge_extended=world.bridge_powered, exit_unlocked=world.exit_unlocked,
        motor_heat=world.heat if role == 'PYRA' else 0,
        shard_collected=role == 'SPECTRA' and world.shard_collected,
        cell_collected=role == 'FLUX' and world.cell_collected,
    )
    return render_png(schematic, role)


def observe(world: physics.World, role: str, window: int, settings, *, consequences=()) -> Observation:
    """Sample just this role. No complete snapshot or free-form events are needed."""
    if role not in ROLES or type(window) is not int or window < 1:
        raise ValueError('An active role and a positive decision window are required')
    robot = world.robots[role]
    if role == 'SPECTRA':
        feedback = {'shard_recovered': world.shard_collected}
    elif role == 'FLUX':
        feedback = {'cell_recovered': world.cell_collected}
    else:
        feedback = {'coolant_available': world.coolant >= physics.VENT_COOLANT}
    feedback['recent_consequences'] = _recent_consequences(consequences, role, world.tick)
    hud = {
        'schema': HUD_VERSION, 'role': role, 'window': window, 'sample_tick': world.tick,
        'schematic': (
            'TURN is the sampled decision window. The flat floor in the PNG shows horizontal '
            'layout only. Robots snap to the nearest numbered column, with a tie going to the '
            'greater column and clipping at the ends. Within the playable centers the error is '
            'at most half a tile. Use this HUD for height, motion and ground support.'
        ),
        'units_per_tile': physics.TILE,
        'coordinates': 'x is the foot center and y is sole height, positive upward. '
                       'Positions and distances use subunits. Velocities use subunits per tick.',
        'self': {'x': robot.x, 'y': robot.y, 'vx': robot.vx, 'vy': robot.vy,
                 'grounded': robot.grounded, 'facing': robot.facing},
        'terrain': {'columns': _SCHEMATIC.width, 'gap_left': physics.GAP_LEFT,
                    'gap_right': physics.GAP_RIGHT, 'left_height': physics.LEFT_BANK.top,
                    'deck_height': physics.DECK.top, 'far_height': physics.BANK_HEIGHT},
        'movement': {'ticks_per_second': physics.TICK_RATE, 'drive': physics.DRIVE,
                     'half_width': physics.HALF_WIDTH, 'height': physics.HEIGHT,
                     'jump_impulse': physics.JUMP_IMPULSE, 'gravity': physics.GRAVITY},
        'limits': {'window_ticks': settings.window_ticks, 'action_points': settings.action_points,
                   'max_commands': getattr(settings, 'max_commands', MAX_COMMANDS),
                   'max_run_ticks': MAX_RUN_TICKS, 'run_ticks_per_point': RUN_TICKS_PER_POINT,
                   'action_cost': ACTION_COST},
        'interactions': {'motor_range': physics.MOTOR_RANGE, 'collect_radius': physics.COLLECT_RADIUS,
                         'exit_radius': physics.EXIT_RADIUS, 'heat_limit': physics.HEAT_LIMIT,
                         'vent_cooling': physics.VENT_COOLING, 'vent_coolant': physics.VENT_COOLANT,
                         'reroute_heat': physics.REROUTE_HEAT, 'reroute_energy': physics.REROUTE_ENERGY},
        'resources': {'energy': world.energy, 'coolant': world.coolant},
        'your_objective': _GOALS[role], 'your_feedback': feedback,
        'mission': 'Power the bridge, recover the shard, and bring all three robots onto the '
                   'ground at the marked exit. Its lamp lights when the bridge and shard are ready.',
    }
    return Observation(role, window, json.dumps(hud, sort_keys=True, separators=(',', ':')),
                       _image(world, role, window))
