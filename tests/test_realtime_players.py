import asyncio
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import time
import unittest

from PIL import Image

from parallax_relay import observations as baseline
from parallax_relay.protocol import ROLES
from parallax_relay.realtime import physics
from parallax_relay.realtime.coordination import Coordinator
from parallax_relay.realtime.observations import HUD_VERSION, _column, observe
from parallax_relay.realtime.players import ReactiveAgent
from parallax_relay.realtime.settings import Settings
from parallax_relay.realtime.wire import make_request, parse
from parallax_relay.state import initial_world as initial_schematic


class RealtimeObservationTests(unittest.TestCase):
    def setUp(self):
        self.world = physics.initial_world()
        self.settings = Settings.offline()

    def view(self, role, window=1, **kwargs):
        return observe(self.world, role, window, self.settings, **kwargs)

    def test_quantization_bounds_and_all_half_tile_ties(self):
        tile = physics.TILE
        last = initial_schematic('split_span').room.width - 1
        self.assertEqual((_column(-3 * tile), _column((last + 3) * tile)), (0, last))
        for x in range(last * tile + 1):
            self.assertLessEqual(abs(x - _column(x) * tile), tile // 2)
        for column in range(last):
            tie = column * tile + tile // 2
            self.assertEqual((_column(tie - 1), _column(tie)), (column, column + 1))

    def test_original_png_bytes_at_matched_ticks_and_horizontal_landmarks(self):
        old = initial_schematic('split_span')
        unit = physics.TILE
        self.assertEqual((physics.MOTOR_X, physics.SHARD_X, physics.CELL_X, physics.EXIT_X),
                         tuple(c * unit for c in (old.room.bridges[0].motor, old.room.shard,
                                                  old.room.cells[0], old.room.exit)))
        gap = old.room.bridges[0].gap
        self.assertEqual((physics.GAP_LEFT, physics.GAP_RIGHT),
                         ((min(gap) * unit) - unit // 2, (max(gap) * unit) + unit // 2))
        for window, powered, recovered in ((1, False, False), (2, True, False), (3, True, True)):
            old.turn = window
            self.world.tick = (window - 1) * 120
            self.world.bridge_powered = old.bridge_extended = powered
            self.world.shard_collected = old.shard_collected = recovered
            self.world.cell_collected = old.cell_collected = recovered
            old.exit_unlocked = self.world.exit_unlocked
            self.world.heat = old.motor_heat = 3 if powered else 4
            if powered:
                # Includes a half-column tie, one subunit below a tie and the right boundary.
                new_x = (5 * unit + unit // 2, 9 * unit + unit // 2 - 1, physics.RIGHT_EDGE - physics.HALF_WIDTH)
                for role, x, column in zip(ROLES, new_x, (6, 9, 12)):
                    self.world.robots[role].x = x
                    old.robots[role].x = column
            for role in ROLES:
                with self.subTest(window=window, role=role):
                    sample = self.view(role, window)
                    self.assertEqual(sample.image_png, baseline.observe(old, role).image_png)
                    with Image.open(BytesIO(sample.image_png)) as im:
                        self.assertEqual(im.size, (850, 295))
                    self.assertEqual(sample.turn, window)
                    self.assertEqual(sample.hud['sample_tick'], self.world.tick)
                    self.assertEqual(sample.hud['schema'], HUD_VERSION)

    def test_hud_explains_precision_and_exposes_only_own_kinematics(self):
        self.world.tick = 80
        robot = self.world.robots['PYRA']
        robot.x, robot.y, robot.vx, robot.vy, robot.grounded, robot.facing = 1639, 171, -16, 6, False, -1
        pyra = self.view('PYRA', 2)
        self.assertEqual(pyra.hud['self'], {'x': 1639, 'y': 171, 'vx': -16, 'vy': 6,
                                           'grounded': False, 'facing': -1})
        for phrase in ('TURN', 'window', 'flat floor', 'half a tile'):
            self.assertIn(phrase, pyra.hud['schematic'])
        for obsolete in ('max_turns', 'MOVE', 'UNLOCK', 'score', 'deadline'):
            self.assertNotIn(obsolete, pyra.hud_json)
        old = self.view('SPECTRA', 2)
        robot.x += 1  # Still the same visible column.
        robot.vy, robot.checkpoint_x = 117, 9876543
        self.assertEqual(old, self.view('SPECTRA', 2))
        writable = old.hud
        writable['self']['x'] = -111
        self.assertNotEqual(old.hud['self']['x'], -111)
        for role in ('ECHO', 'SPECTATOR', 'unknown'):
            with self.assertRaises(ValueError):
                self.view(role)

    def test_altering_a_private_reading_cannot_change_another_request_observation(self):
        for field, value, owner in (('heat', 1, 'PYRA'), ('shard_collected', True, 'SPECTRA'),
                                    ('cell_collected', True, 'FLUX')):
            original = {r: self.view(r) for r in ROLES}
            previous = getattr(self.world, field)
            setattr(self.world, field, value)
            for role in ROLES:
                with self.subTest(field=field, role=role):
                    sample = self.view(role)
                    if role == owner:
                        self.assertNotEqual(original[role].image_png, sample.image_png)
                        if field == 'heat':
                            self.assertEqual(original[role].hud_json, sample.hud_json)
                    else:
                        self.assertEqual(original[role], sample)
            setattr(self.world, field, previous)
        self.assertEqual(len({self.view(r).hud['your_objective'] for r in ROLES}), len(ROLES))

    def test_falls_and_blocked_actions_have_bounded_role_local_feedback(self):
        self.world.tick = 15
        events = [{'role': 'PYRA', 'tick': t, 'kind': 'takeoff'} for t in range(1, 9)]
        events.extend([
            {'role': 'PYRA', 'tick': 9, 'kind': 'landing', 'surface': 'deck'},
            {'role': 'PYRA', 'tick': 10, 'kind': 'fell', 'text': 'private sentinel'},
            {'role': 'PYRA', 'tick': 10, 'kind': 'respawn', 'x': 'private sentinel'},
            {'role': 'PYRA', 'tick': 11, 'kind': 'blocked', 'action': 'JUMP', 'text': 'private sentinel'},
            {'role': 'PYRA', 'tick': 12, 'kind': 'side_contact', 'surface': 'private sentinel'},
            {'role': 'FLUX', 'tick': 13, 'kind': 'rerouted', 'text': 'private sentinel'},
            {'role': 'PYRA', 'tick': 16, 'kind': 'vented'},
            {'role': 'PYRA', 'tick': 14, 'kind': 'shard_collected'},
            {'role': 'PYRA', 'tick': 15, 'kind': 'unknown.private.sentinel'},
        ])
        sample = self.view('PYRA', 2, consequences=events)
        rows = sample.hud['your_feedback']['recent_consequences']
        self.assertEqual([row['kind'] for row in rows], ['takeoff', 'landing', 'fell', 'respawn', 'blocked', 'side_contact'])
        self.assertIn('bridge deck', rows[1]['text'])
        self.assertIn('JUMP', rows[-2]['text'])
        self.assertNotIn('sentinel', sample.hud_json)
        self.assertEqual(self.view('SPECTRA', 2, consequences=events).hud['your_feedback']['recent_consequences'], [])
        self.assertEqual(self.view('PYRA', 3).hud['your_feedback']['recent_consequences'], [])


class ReactivePlayerTests(unittest.IsolatedAsyncioTestCase):
    async def reply(self, role, sample, phase='commit', messages=()):
        settings = Settings.offline()
        request = make_request(sample, phase, messages, [], '', sample.turn, 'one-issued-request', settings)
        agent = ReactiveAgent(role)
        try:
            reply = await agent.respond(request)
            self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens), (0, 0))
            return parse(reply.text, phase, sample.turn, request.request_id, settings)
        finally:
            await agent.close()

    async def test_reroute_requires_a_published_thermal_report_and_sufficient_reach(self):
        world, settings = physics.initial_world(), Settings.offline()
        flux = observe(world, 'FLUX', 1, settings)
        actions = (await self.reply('FLUX', flux))['actions']
        self.assertNotIn('REROUTE', [a['kind'] for a in actions])
        pyra = observe(world, 'PYRA', 1, settings)
        speech = (await self.reply('PYRA', pyra, phase='broadcast'))['message']
        public = [{'role': 'PYRA', 'window': 1, 'phase': 'broadcast', 'text': speech}]
        self.assertEqual((await self.reply('FLUX', flux, messages=public))['actions'][0]['kind'], 'REROUTE')
        world.robots['FLUX'].x = 0
        far = observe(world, 'FLUX', 1, settings)
        self.assertEqual((await self.reply('FLUX', far, messages=public))['actions'][0]['kind'], 'RUN')
        world.robots['PYRA'].x = physics.MOTOR_X
        for heat in range(8):
            world.heat = heat
            sample = observe(world, 'PYRA', 1, settings)
            message = (await self.reply('PYRA', sample, phase='broadcast'))['message']
            self.assertIn(f'reads {heat} ', message)
            actions = (await self.reply('PYRA', sample))['actions']
            self.assertEqual(any(a['kind'] == 'VENT' for a in actions), heat > 2)

    async def test_moving_only_the_private_png_marker_changes_the_same_window_commit(self):
        world, settings = physics.initial_world(), Settings.offline()
        world.bridge_powered = True
        for role, field, column in (('SPECTRA', 'shard', 9), ('FLUX', 'cells', 10)):
            world.robots[role].x = column * physics.TILE
            world.robots[role].y = physics.BANK_HEIGHT
            sample = observe(world, role, 2, settings)
            self.assertEqual((await self.reply(role, sample))['actions'][0]['kind'], 'COLLECT')
            other = initial_schematic('split_span')
            other.turn, other.bridge_extended = 2, True
            other.room = other.room.model_copy(update={field: 11 if field == 'shard' else (11,)})
            for name in ROLES:
                other.robots[name].x = world.robots[name].x // physics.TILE
            shifted = replace(sample, image_png=baseline.observe(other, role).image_png)
            actions = (await self.reply(role, shifted))['actions']
            self.assertEqual(actions[0]['kind'], 'RUN')
            self.assertEqual(actions[0]['direction'], 1)
        with self.assertRaisesRegex(ValueError, 'different player'):
            await self.reply('SPECTRA', observe(world, 'PYRA', 1, settings))

    async def test_sealed_feedback_controllers_extract_within_four_windows_and_jump_timing_matters(self):
        world, settings = physics.initial_world(), Settings.offline()
        agents = {role: ReactiveAgent(role) for role in ROLES}
        coordinator = Coordinator(agents, settings, {}, lambda *_args, **_kwargs: None)
        events, missed, launch_offsets = [], [], []
        try:
            for window in range(1, 5):
                samples = {r: observe(world, r, window, settings, consequences=events) for r in ROLES}
                programs, _speech = await coordinator.coordinate(samples, window, time.monotonic() + 20)
                self.assertEqual(set(coordinator.dispositions.values()), {'ok'})
                leaps = [a for a in programs['SPECTRA'] if a['jump_at'] is not None]
                if leaps and leaps[0]['jump_at'] > 0 and not missed:
                    wrong_world, wrong_programs = deepcopy(world), deepcopy(programs)
                    jump = next(a for a in wrong_programs['SPECTRA'] if a['jump_at'] is not None)
                    jump['jump_at'] = 0
                    for offset in range(settings.window_ticks):
                        missed.extend(physics.step(wrong_world, wrong_programs, offset))
                    self.assertFalse(wrong_world.shard_collected)
                    launch_offsets = [a['jump_at'] for r in ROLES for a in programs[r] if a['jump_at'] is not None]
                for offset in range(settings.window_ticks):
                    events.extend(physics.step(world, programs, offset))
                    if world.completed:
                        break
                if world.completed:
                    break
        finally:
            self.assertTrue(await coordinator.close())
            await asyncio.gather(*(a.close() for a in agents.values()))
        self.assertTrue(world.completed)
        self.assertTrue(2 <= window <= 4)
        self.assertTrue(world.bridge_powered and world.shard_collected and world.cell_collected and world.exit_unlocked)
        self.assertEqual(len(set(launch_offsets)), 3)
        self.assertEqual({e['role'] for e in events if e['kind'] == 'landing' and e['surface'] == 'far_bank'}, set(ROLES))
        self.assertTrue(any(e['role'] == 'SPECTRA' and e['kind'] == 'side_contact' and e['surface'] == 'far_bank'
                            for e in missed if 'role' in e))
        for robot in world.robots.values():
            self.assertTrue(robot.grounded)
            self.assertLessEqual(abs(robot.x - physics.EXIT_X), physics.EXIT_RADIUS)
