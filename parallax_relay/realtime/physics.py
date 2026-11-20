"""Fixed-tick physics for the Split Span development platformer.

Positions are integer subunits. A robot's (x, y) is its foot center, positive
y points up, and velocities are subunits per tick. The caller owns the clock.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..protocol import ROLES


TICK_RATE = 60
TILE = 256
HALF_WIDTH = 64
HEIGHT = 192
DRIVE = 16
JUMP_IMPULSE = 20
GRAVITY = 1

GAP_LEFT = 4 * TILE + TILE // 2
GAP_RIGHT = 7 * TILE + TILE // 2
BANK_HEIGHT = TILE // 2
MOTOR_X = 4 * TILE
MOTOR_RANGE = TILE
HEAT_LIMIT = 4
VENT_COOLING = 3
VENT_COOLANT = 1
REROUTE_HEAT = 2
REROUTE_ENERGY = 2
SHARD_X = 9 * TILE
CELL_X = 10 * TILE
COLLECT_RADIUS = TILE // 2
CELL_ENERGY = 2
EXIT_X = 12 * TILE
EXIT_RADIUS = TILE // 2
LEFT_EDGE = -TILE // 2
RIGHT_EDGE = EXIT_X + TILE // 2
FALL_LIMIT = -2 * TILE


@dataclass(frozen=True)
class Solid:
    name: str
    left: int
    right: int
    bottom: int
    top: int


LEFT_BANK = Solid('left_bank', LEFT_EDGE, GAP_LEFT, FALL_LIMIT - HEIGHT, 0)
FAR_BANK = Solid('far_bank', GAP_RIGHT, RIGHT_EDGE, FALL_LIMIT - HEIGHT, BANK_HEIGHT)
DECK = Solid('deck', GAP_LEFT, GAP_RIGHT, -TILE // 4, 0)
BANKS = (LEFT_BANK, FAR_BANK)
POWERED_SURFACES = (*BANKS, DECK)


@dataclass
class Robot:
    x: int
    checkpoint_x: int
    y: int = 0
    vx: int = 0
    vy: int = 0
    grounded: bool = True
    facing: int = 1
    pose: str = 'idle'
    program_cancelled: bool = False
    side_contact: str | None = None

    def pose_state(self) -> dict:
        return {
            'x': self.x, 'y': self.y, 'vx': self.vx, 'vy': self.vy,
            'grounded': self.grounded, 'facing': self.facing, 'pose': self.pose,
        }


@dataclass
class World:
    robots: dict[str, Robot]
    tick: int = 0
    bridge_powered: bool = False
    heat: int = 4
    shard_collected: bool = False
    cell_collected: bool = False
    energy: int = 6
    coolant: int = 2
    completed: bool = False

    @property
    def exit_unlocked(self) -> bool:
        return self.bridge_powered and self.shard_collected

    def snapshot(self) -> dict:
        """Detached host state. Player requests need their own allowlist."""
        return {
            'tick': self.tick,
            'robots': {role: robot.pose_state() for role, robot in self.robots.items()},
            'bridge_powered': self.bridge_powered, 'exit_unlocked': self.exit_unlocked,
            'heat': self.heat, 'shard_collected': self.shard_collected,
            'cell_collected': self.cell_collected, 'energy': self.energy,
            'coolant': self.coolant, 'completed': self.completed,
        }

    def replay_state(self) -> dict:
        """Include the state that can affect a later input, contact or reset."""
        state = self.snapshot()
        state['recovery'] = {
            role: {'checkpoint_x': robot.checkpoint_x,
                   'program_cancelled': robot.program_cancelled,
                   'side_contact': robot.side_contact}
            for role, robot in self.robots.items()
        }
        return state


def initial_world() -> World:
    return World({role: Robot(x, x) for role, x in zip(ROLES, (2 * TILE, 3 * TILE, 4 * TILE))})


@dataclass(frozen=True)
class TickInput:
    direction: int = 0
    jump: bool = False
    interaction: str | None = None


NEUTRAL = TickInput()


def _input_at(program: Sequence[Mapping], offset: int) -> TickInput:
    """Sample an already-validated program, using half-open command intervals."""
    for command in program:
        kind = command['kind']
        duration = command['ticks'] if kind in ('RUN', 'WAIT') else 1
        if offset < duration:
            if kind == 'RUN':
                return TickInput(command['direction'], offset == command['jump_at'])
            if kind == 'JUMP':
                return TickInput(jump=True)
            if kind == 'WAIT':
                return NEUTRAL
            return TickInput(interaction=kind)
        offset -= duration
    return NEUTRAL


def _overlaps(left: int, right: int, other_left: int, other_right: int) -> bool:
    return left < other_right and other_left < right


def _sweep(start: int, delta: int, faces: Iterable[tuple[int, str]]) -> tuple[int, str | None]:
    """Find the first face encountered, with a stable name breaking distance ties."""
    end = start + delta
    low, high = sorted((start, end))
    candidates = ((position, name) for position, name in faces if low <= position <= high)
    return min(candidates, key=lambda face: (abs(face[0] - start), face[1]), default=(end, None))


def _supported(robot: Robot, solids: tuple[Solid, ...]) -> bool:
    return any(robot.y == solid.top and
               _overlaps(robot.x - HALF_WIDTH, robot.x + HALF_WIDTH, solid.left, solid.right)
               for solid in solids)


def _event(world: World, kind: str, text: str, role: str | None = None, **details) -> dict:
    event = {'tick': world.tick, 'kind': kind, 'text': text, **details}
    if role is not None:
        event.update(role=role, **world.robots[role].pose_state())
    return event


def _motor(world: World, role: str, action: str, solids: tuple[Solid, ...]) -> dict:
    robot = world.robots[role]
    owner = 'PYRA' if action == 'VENT' else 'FLUX'
    at_motor = robot.y == DECK.top and abs(robot.x - MOTOR_X) <= MOTOR_RANGE
    if role != owner or not at_motor or not robot.grounded or not _supported(robot, solids):
        return _event(world, 'blocked', f'{role} could not operate the motor from here.', role, action=action)
    if action == 'VENT':
        if world.coolant < VENT_COOLANT:
            return _event(world, 'blocked', 'PYRA had no coolant to vent the motor.', role, action=action)
        world.coolant -= VENT_COOLANT
        world.heat = max(0, world.heat - VENT_COOLING)
        return _event(world, 'vented', 'PYRA vented the motor.', role)
    if world.bridge_powered or world.energy < REROUTE_ENERGY or world.heat + REROUTE_HEAT > HEAT_LIMIT:
        return _event(world, 'blocked', 'The motor rejected the power transfer.', role, action=action)
    world.energy -= REROUTE_ENERGY
    world.heat += REROUTE_HEAT
    world.bridge_powered = True
    return _event(world, 'rerouted', 'FLUX powered the motor and extended the bridge.', role)


def _move(world: World, role: str, control: TickInput, solids: tuple[Solid, ...], events: list[dict]) -> None:
    robot = world.robots[role]
    was_grounded = robot.grounded and _supported(robot, solids)
    jumping = was_grounded and control.jump
    if jumping:
        robot.vy = JUMP_IMPULSE
    elif control.jump:
        events.append(_event(world, 'blocked', f'{role} needs ground support to jump.', role, action='JUMP'))

    previous_x = robot.x
    side = None
    robot.vx = DRIVE * control.direction
    if control.direction:
        robot.facing = control.direction
        moving_right = control.direction > 0
        wall = (RIGHT_EDGE - HALF_WIDTH, 'right_wall') if moving_right else (LEFT_EDGE + HALF_WIDTH, 'left_wall')
        faces = [wall]
        for solid in solids:
            if _overlaps(robot.y, robot.y + HEIGHT, solid.bottom, solid.top):
                faces.append((solid.left - HALF_WIDTH if moving_right else solid.right + HALF_WIDTH, solid.name))
        robot.x, side = _sweep(robot.x, robot.vx, faces)
        if side is not None:
            robot.vx = 0

    robot.vy -= GRAVITY
    ascending = robot.vy > 0
    vertical_contact = None
    if robot.vy:
        faces = ((solid.bottom - HEIGHT if ascending else solid.top, solid.name) for solid in solids
                 if _overlaps(robot.x - HALF_WIDTH, robot.x + HALF_WIDTH, solid.left, solid.right))
        robot.y, vertical_contact = _sweep(robot.y, robot.vy, faces)
    robot.grounded = vertical_contact is not None and not ascending
    if vertical_contact is not None:
        robot.vy = 0

    landed = robot.grounded and not was_grounded
    if landed:
        robot.pose = 'landing'
    elif robot.grounded:
        robot.pose = 'walk' if robot.x != previous_x else 'idle'
    elif jumping and vertical_contact is None:
        robot.pose = 'takeoff'
    else:
        robot.pose = 'ascent' if robot.vy > 0 or (robot.vy == 0 and vertical_contact is None) else 'descent'

    if jumping:
        events.append(_event(world, 'takeoff', f'{role} jumped.', role))
    if side is not None and side != robot.side_contact:
        events.append(_event(world, 'side_contact', f'{role} met a vertical face.', role, surface=side))
    robot.side_contact = side
    if ascending and vertical_contact is not None:
        events.append(_event(world, 'underside_contact', f'{role} hit an underside.', role, surface=vertical_contact))
    if landed:
        events.append(_event(world, 'landing', f'{role} landed.', role, surface=vertical_contact))

    # A restart always puts the entire footprint back on the safe starting bank.
    if robot.grounded and robot.y == 0 and robot.x + HALF_WIDTH <= GAP_LEFT:
        robot.checkpoint_x = max(robot.checkpoint_x, robot.x)


def _collect(world: World, role: str) -> dict:
    robot = world.robots[role]
    on_bank = robot.grounded and robot.y == BANK_HEIGHT
    if role == 'SPECTRA' and on_bank and abs(robot.x - SHARD_X) <= COLLECT_RADIUS and not world.shard_collected:
        world.shard_collected = True
        return _event(world, 'shard_collected', 'SPECTRA recovered the memory shard.', role)
    if role == 'FLUX' and on_bank and abs(robot.x - CELL_X) <= COLLECT_RADIUS and not world.cell_collected:
        world.cell_collected = True
        world.energy += CELL_ENERGY
        return _event(world, 'cell_collected', 'FLUX recovered an energy cell.', role)
    return _event(world, 'blocked', f'{role} found nothing to collect here.', role, action='COLLECT')


def _reset_fall(world: World, role: str, events: list[dict]) -> None:
    robot = world.robots[role]
    events.append(_event(world, 'fell', f'{role} fell below the room.', role))
    robot.x, robot.y = robot.checkpoint_x, 0
    robot.vx = robot.vy = 0
    robot.grounded = True
    robot.pose = 'idle'
    robot.side_contact = None
    robot.program_cancelled = True
    events.append(_event(world, 'respawn', f'{role} returned to its safe checkpoint.', role))


def step(world: World, programs: Mapping[str, Sequence[Mapping]], offset: int) -> list[dict]:
    """Commit one tick of the three sealed programs. Offset zero starts a window."""
    if world.completed:
        raise ValueError('The team checkpoint has already completed')
    if type(offset) is not int or offset < 0 or set(programs) != set(ROLES):
        raise ValueError('A nonnegative tick offset and all three sealed programs are required')
    controls = {
        role: (_input_at(programs[role], offset) if offset == 0 or not world.robots[role].program_cancelled else NEUTRAL)
        for role in ROLES
    }
    if offset == 0:
        for robot in world.robots.values():
            robot.program_cancelled = False
    world.tick += 1
    events: list[dict] = []
    was_unlocked = world.exit_unlocked
    solids = POWERED_SURFACES if world.bridge_powered else BANKS
    for action in ('VENT', 'REROUTE'):
        for role in ROLES:
            if controls[role].interaction == action:
                events.append(_motor(world, role, action, solids))
    if world.bridge_powered:
        solids = POWERED_SURFACES
    for role in ROLES:
        _move(world, role, controls[role], solids, events)
    for role in ROLES:
        if controls[role].interaction == 'COLLECT':
            events.append(_collect(world, role))
        if world.robots[role].y < FALL_LIMIT:
            _reset_fall(world, role, events)
    if world.exit_unlocked and not was_unlocked:
        events.append(_event(world, 'exit_unlocked', 'The extraction hatch unlocked.'))
    if world.exit_unlocked and all(robot.grounded and robot.y == BANK_HEIGHT and abs(robot.x - EXIT_X) <= EXIT_RADIUS
                                   for robot in world.robots.values()):
        world.completed = True
        events.append(_event(world, 'completed', 'All three robots reached extraction.'))
    return events
