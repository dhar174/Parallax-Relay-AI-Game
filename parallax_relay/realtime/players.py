"""Offline feedback controllers for the real-time room's three player seats."""

import asyncio
from dataclasses import dataclass
from io import BytesIO
import json
import math

from PIL import Image

from ..protocol import ModelReply, ROLES, Usage
from ..render import FLOOR_Y, H, W, px


# These are colors and glyph measurements from the public sensor format.
# The controller never imports the room, its private landmark locations or its solver.
_EXIT_EDGE = (120, 134, 153)
_POWERED_FLOORS = {(70, 127, 119), (82, 103, 122)}
_HEAT_CORE = {(228, 107, 63), (181, 158, 87)}
_HEAT_RING = (200, 95, 65)
_FEED = (114, 219, 203)
_SHARD = (225, 171, 245)
_CELL = (66, 213, 187)
_THERMAL_READY = 'The motor is cool enough to reroute.'
_VENT_READY = 'I will cool it enough to reroute on the first tick.'
_FEED_READY = 'I can reroute on the first tick.'


@dataclass(frozen=True)
class _Readings:
    deck: bool
    exit_column: int | None
    motor_column: int | None = None
    heat: int | None = None
    pickup_column: int | None = None


def _read_sensor(observation, hud) -> _Readings:
    """Read the visible glyphs on this one 850×295 schematic."""
    role = observation.role
    terrain = hud['terrain']
    columns = range(terrain['columns'])
    with Image.open(BytesIO(observation.image_png)) as im:
        if im.size != (W, H) or im.mode != 'RGB':
            raise ValueError('Unsupported sensor image')
        gap_middle = (terrain['gap_left'] + terrain['gap_right']) // (2 * hud['units_per_tile'])
        deck = im.getpixel((px(gap_middle), FLOOR_Y + 5)) in _POWERED_FLOORS
        exit_column = next((c for c in columns
                            if im.getpixel((px(c) - 17, FLOOR_Y - 70)) == _EXIT_EDGE), None)
        motor = heat = pickup = None
        if role == 'PYRA':
            motor = next((c for c in columns if im.getpixel((px(c), FLOOR_Y - 2)) in _HEAT_CORE), None)
            if motor is not None:
                # The thermal glyph has a 14 px base radius plus 5 px per heat unit.
                # A robot can cover its top. Its bottom stays below the silhouettes.
                cy = FLOOR_Y - 10
                bottom = next((y for y in range(H - 1, cy, -1) if im.getpixel((px(motor), y)) == _HEAT_RING), None)
                if bottom is not None:
                    heat = (bottom - cy - 14) // 5
        if role == 'FLUX':
            motor = next((c for c in columns if im.getpixel((px(c), FLOOR_Y + 26)) == _FEED), None)
        if role in ('SPECTRA', 'FLUX'):
            color = _SHARD if role == 'SPECTRA' else _CELL
            for c in columns:
                # Robot initials can overlap a marker. Look for its remaining solid fill.
                patch = im.crop((px(c) - 13, FLOOR_Y - 64, px(c) + 14, FLOOR_Y - 29))
                if color in {value for _, value in patch.getcolors(maxcolors=patch.width * patch.height)}:
                    pickup = c
                    break
    return _Readings(deck, exit_column, motor, heat, pickup)


def _reachable_motor(hud, reading):
    robot = hud['self']
    return (reading.motor_column is not None and robot['grounded'] and
            robot['y'] == hud['terrain']['deck_height'] and
            abs(robot['x'] - reading.motor_column * hud['units_per_tile']) <= hud['interactions']['motor_range'])


def _thermal_status(hud, reading):
    rules = hud['interactions']
    if reading.heat is None:
        return 'unknown'
    if reading.heat + rules['reroute_heat'] <= rules['heat_limit']:
        return 'cool'
    if (_reachable_motor(hud, reading) and hud['resources']['coolant'] >= rules['vent_coolant']
            and hud['limits']['action_points'] >= hud['limits']['action_cost']):
        if max(0, reading.heat - rules['vent_cooling']) + rules['reroute_heat'] <= rules['heat_limit']:
            return 'vent'
        return 'more_cooling'
    return 'unavailable'


def _feed_ready(hud, reading):
    return (_reachable_motor(hud, reading)
            and hud['resources']['energy'] >= hud['interactions']['reroute_energy']
            and hud['limits']['action_points'] >= hud['limits']['action_cost'])


def _heard(request, role, phrases):
    return any(m.role == role and m.turn == request.window and not m.fallback and
               any(phrase in m.text for phrase in phrases) for m in request.messages)


def _command(kind, direction=None, ticks=None, jump_at=None):
    return {'kind': kind, 'direction': direction, 'ticks': ticks, 'jump_at': jump_at}


def _ceil(numerator, denominator):
    return -(-numerator // denominator)


def _run(hud, target, available_points, available_ticks):
    """Aim the apex at the raised face using the observed foot position and terrain."""
    if target is None:
        return None
    robot, limits, motion, terrain = (hud[k] for k in ('self', 'limits', 'movement', 'terrain'))
    distance = target - robot['x']
    direction = 1 if distance > 0 else -1
    drive = motion['drive']
    per_point = limits['run_ticks_per_point']
    ticks = min(_ceil(abs(distance), drive), limits['max_run_ticks'], available_ticks,
                available_points * per_point)
    jump_at = None
    if (direction == 1 and robot['grounded'] and robot['y'] < terrain['far_height']
            and target >= terrain['gap_right']):
        apex_ticks = max(1, motion['jump_impulse'] // motion['gravity'] - 1)
        launch_x = terrain['gap_right'] - motion['half_width'] - apex_ticks * drive
        offset = max(0, _ceil(launch_x - robot['x'], drive))
        if offset < ticks:
            with_jump = min(ticks, (available_points - limits['action_cost']) * per_point)
            if offset < with_jump:
                ticks, jump_at = with_jump, offset
            else:
                ticks = offset  # Keep the takeoff point for a later window.
    return _command('RUN', direction, ticks, jump_at) if ticks > 0 else None


def _motor_plan(request, hud, reading):
    role, limits = request.role, hud['limits']
    thermal = _thermal_status(hud, reading) if role == 'PYRA' else None
    cool = thermal in ('cool', 'vent') if role == 'PYRA' else _heard(request, 'PYRA', (_THERMAL_READY, _VENT_READY))
    feed = _feed_ready(hud, reading) if role == 'FLUX' else _heard(request, 'FLUX', (_FEED_READY,))
    actions = []
    if role == 'PYRA' and thermal in ('vent', 'more_cooling'):
        actions.append(_command('VENT'))
    elif role == 'FLUX' and cool and feed:
        actions.append(_command('REROUTE'))

    terrain = hud['terrain']
    if role in ('PYRA', 'FLUX') and reading.motor_column is not None and not _reachable_motor(hud, reading):
        target = reading.motor_column * hud['units_per_tile']
    elif cool and feed:
        # Close half the distance to the far face, leaving space between
        # teammates. Confirm deck support on a fresh sample before jumping.
        halfway = (hud['self']['x'] + terrain['gap_right']) // 2
        half_width = hud['movement']['half_width']
        target = min(terrain['gap_right'] - half_width, max(terrain['gap_left'] + half_width, halfway))
    else:
        target = terrain['gap_left'] - hud['movement']['half_width']
    if len(actions) < limits['max_commands']:
        run = _run(hud, target, limits['action_points'] - len(actions) * limits['action_cost'],
                   limits['window_ticks'] - len(actions))
        if run:
            actions.append(run)
    return actions


def _crossing_plan(hud, reading):
    limits, robot = hud['limits'], hud['self']
    points, ticks = limits['action_points'], limits['window_ticks']
    cost = limits['action_cost']
    tile = hud['units_per_tile']
    exit_x = None if reading.exit_column is None else reading.exit_column * tile
    target = exit_x
    actions = []
    if reading.pickup_column is not None:
        target = reading.pickup_column * tile
        radius = hud['interactions']['collect_radius']
        if (robot['grounded'] and robot['y'] == hud['terrain']['far_height']
                and abs(target - robot['x']) <= radius and points >= cost):
            actions.append(_command('COLLECT'))
            points, ticks = points - cost, ticks - 1
            target = exit_x
        elif limits['max_commands'] >= 2:
            # Reserve a collection only if the remaining drive can reach it.
            run = _run(hud, target, points - cost, ticks - 1)
            if run:
                end = robot['x'] + run['direction'] * run['ticks'] * hud['movement']['drive']
                settled = robot['grounded']
                if run['jump_at'] is not None:
                    elapsed = run['ticks'] - run['jump_at']
                    impulse, gravity = hud['movement']['jump_impulse'], hud['movement']['gravity']
                    altitude = robot['y'] + elapsed * impulse - gravity * elapsed * (elapsed + 1) // 2
                    settled = elapsed * gravity > impulse and altitude <= hud['terrain']['far_height']
                if settled and abs(target - end) <= radius:
                    return [run, _command('COLLECT')]
    if (target == exit_x and target is not None and abs(robot['x'] - target) <= hud['interactions']['exit_radius']
            and robot['grounded'] and robot['y'] == hud['terrain']['far_height']):
        return actions
    if len(actions) < limits['max_commands']:
        run = _run(hud, target, points, ticks)
        if run:
            actions.append(run)
    return actions


def _speak(request, hud, reading, actions):
    role = request.role
    if not reading.deck and role == 'PYRA':
        thermal = _thermal_status(hud, reading)
        lead = (f'My thermal ring reads {reading.heat} at column {reading.motor_column}. '
                if reading.heat is not None else '')
        return lead + {'cool': _THERMAL_READY, 'vent': _VENT_READY,
                       'more_cooling': 'I will vent, but the motor needs another cycle.',
                       'unknown': 'I cannot read the thermal ring.',
                       'unavailable': 'I cannot cool it from here.'}[thermal]
    if not reading.deck and role == 'FLUX':
        if _feed_ready(hud, reading):
            return f'I see the feed at column {reading.motor_column}. {_FEED_READY}'
        return 'I need a supported position in range of the powered feed and enough energy.'
    if request.phase == 'negotiate':
        leap = next((a for a in actions if a['jump_at'] is not None), None)
        if leap:
            return f'I will jump {leap["jump_at"]} ticks into my run to clear the raised bank.'
    if reading.pickup_column is not None:
        item = 'shard' if role == 'SPECTRA' else 'cell'
        return f'My sensor marks the {item} at column {reading.pickup_column}. I will recover it.'
    if reading.exit_column is not None:
        return f'My exit frame is at column {reading.exit_column}. I will meet you there.'
    return 'I am checking my position and ground support.'


class ReactiveAgent:
    """An explicit offline controller with only its current authorized player request."""

    def __init__(self, role: str, delay_seconds: float = 0.0):
        if role not in ROLES or not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise ValueError('An active role and a finite nonnegative response delay are required')
        self.role = role
        self.delay_seconds = delay_seconds

    async def respond(self, request) -> ModelReply:
        if request.role != self.role:
            raise ValueError('Request assigned to a different player')
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        hud = request.observation.hud
        reading = _read_sensor(request.observation, hud)
        actions = _crossing_plan(hud, reading) if reading.deck else _motor_plan(request, hud, reading)
        body = {'request_id': request.request_id, 'window': request.window}
        if request.phase == 'commit':
            body.update(actions=actions or [_command('WAIT', ticks=1)], notes='')
        elif request.phase in ('broadcast', 'negotiate'):
            body['message'] = _speak(request, hud, reading, actions)
        else:
            raise ValueError('Unknown real-time phase')
        return ModelReply(json.dumps(body, separators=(',', ':')), Usage(0, 0))

    async def close(self):
        pass
