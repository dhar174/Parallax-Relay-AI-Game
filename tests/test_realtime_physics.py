"""Development-room regressions for the authoritative fixed-tick simulation."""

import json
import unittest
from copy import deepcopy
from hashlib import sha256

from parallax_relay.realtime import physics as game


def command(kind, *, ticks=None, direction=None, jump_at=None):
    return {'kind': kind, 'direction': direction, 'ticks': ticks, 'jump_at': jump_at}


def run(ticks, direction=1, jump_at=None):
    return command('RUN', ticks=ticks, direction=direction, jump_at=jump_at)


def wait(ticks):
    return command('WAIT', ticks=ticks)


def programs(spectra=(), pyra=(), flux=()):
    return dict(zip(game.ROLES, (list(spectra), list(pyra), list(flux))))


def play(world, plans, ticks=120):
    events = []
    for offset in range(ticks):
        if world.completed:
            break
        events.extend(game.step(world, plans, offset))
    return events


def worked_windows():
    return [
        programs([run(80)], [command('VENT'), run(48)], [command('REROUTE'), run(48)]),
        programs([run(36, jump_at=0), wait(6), command('COLLECT')],
                 [run(65, jump_at=16)], [run(52, jump_at=0)]),
        programs([run(50)], [run(34)], [command('COLLECT'), run(34)]),
    ]


def kinds(events):
    return [event['kind'] for event in events]


class RealtimeSchedulingTests(unittest.TestCase):
    def test_snapshots_are_detached_and_replay_covers_recovery(self):
        world = game.initial_world()
        snapshot = json.loads(json.dumps(world.snapshot()))
        self.assertEqual(world.snapshot(), snapshot)
        self.assertEqual([512, 768, 1024], [snapshot['robots'][r]['x'] for r in game.ROLES])
        self.assertEqual((0, 4, 6, 2), (world.tick, world.heat, world.energy, world.coolant))
        snapshot['robots']['SPECTRA']['x'] = 0
        self.assertEqual(512, world.robots['SPECTRA'].x)
        replay = world.replay_state()
        world.robots['SPECTRA'].program_cancelled = True
        self.assertFalse(replay['recovery']['SPECTRA']['program_cancelled'])
        self.assertNotEqual(replay, world.replay_state())

    def test_invalid_input_batch_cannot_advance_or_clear_suppression(self):
        world = game.initial_world()
        world.robots['SPECTRA'].program_cancelled = True
        original = world.replay_state()
        for plans, offset in (({'SPECTRA': [run(2)]}, 0), (programs(), -1), (programs(), True)):
            with self.assertRaises(ValueError):
                game.step(world, plans, offset)
            self.assertEqual(original, world.replay_state())

    def test_half_open_commands_jump_once_and_unused_ticks_release_drive(self):
        world = game.initial_world()
        plans = programs([wait(2), run(2, -1, 1), run(1), wait(1)])
        states = []
        events = []
        for offset in range(7):
            events.extend(game.step(world, plans, offset))
            states.append(world.snapshot()['robots']['SPECTRA'])
        self.assertEqual([512, 512, 496, 480, 496, 496, 496], [s['x'] for s in states])
        self.assertEqual([0, 0, 0, 19, 37, 54, 70], [s['y'] for s in states])
        self.assertEqual([0, 0, -16, -16, 16, 0, 0], [s['vx'] for s in states])
        self.assertEqual((4, 'takeoff', -1), (events[0]['tick'], events[0]['pose'], events[0]['facing']))
        self.assertEqual(['takeoff'], kinds(events))
        second = programs([command('JUMP'), run(1, -1)])
        self.assertEqual(['blocked'], kinds(game.step(world, second, 0)))
        game.step(world, second, 1)
        self.assertEqual((480, 99, 14), (world.robots['SPECTRA'].x, world.robots['SPECTRA'].y, world.robots['SPECTRA'].vy))

    def test_different_map_order_and_spectator_sampling_replay_every_tick(self):
        def replay(reverse_keys, sample_every):
            world = game.initial_world()
            hashes, events = [], []
            for plans in worked_windows():
                if reverse_keys:
                    plans = dict(reversed(plans.items()))
                original = deepcopy(plans)
                for offset in range(120):
                    events.extend(game.step(world, plans, offset))
                    if world.tick % sample_every == 0:
                        # A viewer may freely read and transform its detached frame.
                        world.snapshot()['robots'].clear()
                    payload = json.dumps(world.replay_state(), sort_keys=True).encode()
                    hashes.append(sha256(payload).hexdigest())
                    if world.completed:
                        break
                self.assertEqual(original, plans)
            return hashes, events

        hashes, events = replay(False, 3)
        self.assertEqual(281, len(hashes))
        self.assertEqual((hashes, events), replay(True, 17))


class RealtimeContactTests(unittest.TestCase):
    def test_discrete_jump_curve_and_immediate_next_takeoff(self):
        world = game.initial_world()
        plans = programs([command('JUMP')])
        events = []
        robot = world.robots['SPECTRA']
        for k in range(1, 40):
            events.extend(game.step(world, plans, k - 1))
            self.assertEqual(k * (39 - k) // 2, robot.y)
            self.assertEqual(k == 39, robot.grounded)
            if k in (19, 20):
                self.assertEqual(190, robot.y)
            if k == 21:
                self.assertEqual('descent', robot.pose)
        events.extend(game.step(world, plans, 0))
        self.assertEqual([(1, 'takeoff'), (39, 'landing'), (40, 'takeoff')],
                         [(e['tick'], e['kind']) for e in events])
        self.assertEqual([19, 0, 19], [e['y'] for e in events])
        for event in events:
            self.assertTrue({'role', 'x', 'y', 'vx', 'vy', 'facing', 'pose', 'grounded'} <= event.keys())
            self.assertEqual(event['kind'], event['pose'])

    def test_leaving_a_ledge_and_touching_only_a_boundary_supply_no_jump(self):
        world = game.initial_world()
        robot = world.robots['SPECTRA']
        robot.x = game.GAP_LEFT + game.HALF_WIDTH - game.DRIVE
        events = game.step(world, programs([run(1)]), 0)
        self.assertEqual([], events)
        self.assertEqual((1216, -1, False, 'descent'), (robot.x, robot.y, robot.grounded, robot.pose))
        robot.y, robot.vy, robot.grounded = 0, 0, True
        events = game.step(world, programs([command('JUMP')]), 0)
        self.assertEqual(['blocked'], kinds(events))
        self.assertEqual('JUMP', events[0]['action'])
        self.assertFalse(robot.grounded)

    def test_unpowered_gap_from_every_reachable_lower_takeoff_and_reverse_witness(self):
        # All reachable x centers are on this lattice, including the outer wall.
        for x in range(game.LEFT_EDGE + game.HALF_WIDTH, game.GAP_LEFT + game.HALF_WIDTH, game.DRIVE):
            with self.subTest(x=x):
                world = game.initial_world()
                world.robots['SPECTRA'].x = x
                events = play(world, programs([run(90, jump_at=0)]), 90)
                self.assertEqual(1, kinds(events).count('takeoff'))
                self.assertFalse(any(e.get('surface') == 'far_bank' and e['kind'] == 'landing' for e in events))
                self.assertLess(world.robots['SPECTRA'].x, game.GAP_RIGHT)

        world = game.initial_world()
        robot = world.robots['SPECTRA']
        robot.x = game.GAP_RIGHT - game.HALF_WIDTH + game.DRIVE
        robot.y = game.BANK_HEIGHT
        events = play(world, programs([run(45, -1, 0)]), 45)
        self.assertEqual([(45, 'left_bank', 1152, 0)],
                         [(e['tick'], e['surface'], e['x'], e['y']) for e in events if e['kind'] == 'landing'])
        self.assertFalse(world.bridge_powered)

    def test_changing_only_jump_offset_changes_which_surface_catches_the_robot(self):
        checkpoint = game.initial_world()
        play(checkpoint, programs([run(48)], [command('VENT')], [command('REROUTE')]), 48)
        self.assertEqual(5 * game.TILE, checkpoint.robots['SPECTRA'].x)
        early, timed = deepcopy(checkpoint), deepcopy(checkpoint)
        failed = play(early, programs([run(60, jump_at=0)]), 60)
        passed = play(timed, programs([run(60, jump_at=24)]), 60)
        self.assertEqual([(49, 'takeoff'), (84, 'side_contact'), (87, 'landing')],
                         [(e['tick'], e['kind']) for e in failed])
        self.assertEqual(('deck', 1856, 0), (failed[-1]['surface'], failed[-1]['x'], failed[-1]['y']))
        self.assertEqual([(73, 'takeoff'), (103, 'landing')], [(e['tick'], e['kind']) for e in passed])
        self.assertEqual(('far_bank', 2160, 128), (passed[-1]['surface'], passed[-1]['x'], passed[-1]['y']))

    def test_extending_deck_does_not_lift_an_intersecting_robot_and_catches_from_above(self):
        for height, velocity, expected_y, caught in ((-16, -3, -20, False), (5, -5, 0, True)):
            with self.subTest(height=height):
                world = game.initial_world()
                robot = world.robots['SPECTRA']
                robot.x, robot.y, robot.vy, robot.grounded = 6 * game.TILE, height, velocity, False
                events = game.step(world, programs(pyra=[command('VENT')], flux=[command('REROUTE')]), 0)
                self.assertTrue(world.bridge_powered)
                self.assertEqual((expected_y, caught), (robot.y, robot.grounded))
                self.assertEqual(caught, 'landing' in kinds(events))

    def test_underside_and_nearest_floor_stop_a_fast_vertical_body(self):
        world = game.initial_world()
        world.bridge_powered = True
        robot = world.robots['SPECTRA']
        robot.x = 6 * game.TILE
        robot.y = game.DECK.bottom - game.HEIGHT - 1
        robot.vy, robot.grounded = 10, False
        events = game.step(world, programs(), 0)
        self.assertEqual(['underside_contact'], kinds(events))
        self.assertEqual(('deck', 'descent', -256, 0, False),
                         (events[0]['surface'], robot.pose, robot.y, robot.vy, robot.grounded))
        robot.x, robot.y, robot.vy = game.GAP_RIGHT, 400, -800
        landed = game.step(world, programs(), 0)[0]
        self.assertEqual(('landing', 'far_bank', 128), (landed['kind'], landed['surface'], robot.y))

    def test_coplanar_surface_tie_uses_stable_geometry_id(self):
        world = game.initial_world()
        world.bridge_powered = True
        robot = world.robots['SPECTRA']
        robot.x, robot.y, robot.grounded = game.GAP_LEFT, 1, False
        event = game.step(world, programs(), 0)[0]
        self.assertEqual(('landing', 'deck', 0), (event['kind'], event['surface'], robot.y))

    def test_fall_restores_furthest_safe_full_footprint_and_cancels_one_role(self):
        world = game.initial_world()
        plans = programs([run(90, jump_at=88)], [wait(80), run(12)])
        events = play(world, plans)
        failed = [e for e in events if e['kind'] in ('fell', 'respawn')]
        self.assertEqual(['fell', 'respawn'], kinds(failed))
        self.assertLess(failed[0]['y'], game.FALL_LIMIT)
        self.assertEqual(failed[0]['tick'], failed[1]['tick'])
        safe_x = game.GAP_LEFT - game.HALF_WIDTH
        self.assertEqual((safe_x, 0), (failed[1]['x'], failed[1]['y']))
        self.assertNotIn('takeoff', kinds(events))
        self.assertTrue(world.robots['SPECTRA'].program_cancelled)
        self.assertEqual(safe_x, world.robots['SPECTRA'].x)
        self.assertEqual(3 * game.TILE + 12 * game.DRIVE, world.robots['PYRA'].x)
        game.step(world, programs([run(1)]), 0)
        self.assertEqual(safe_x + game.DRIVE, world.robots['SPECTRA'].x)
        self.assertFalse(world.robots['SPECTRA'].program_cancelled)

    def test_robots_can_pass_and_walls_clip_the_body(self):
        world = game.initial_world()
        play(world, programs([run(16)], [run(16, -1)]), 16)
        self.assertEqual((768, 512), (world.robots['SPECTRA'].x, world.robots['PYRA'].x))
        right = world.robots['FLUX']
        right.x, right.y = game.RIGHT_EDGE - game.HALF_WIDTH - game.DRIVE, game.BANK_HEIGHT
        events = play(world, programs([run(90, -1)], flux=[run(90)]), 90)
        self.assertEqual(game.LEFT_EDGE + game.HALF_WIDTH, world.robots['SPECTRA'].x)
        self.assertEqual(game.RIGHT_EDGE - game.HALF_WIDTH, right.x)
        self.assertEqual({'left_wall', 'right_wall'}, {e['surface'] for e in events if e['kind'] == 'side_contact'})
        self.assertEqual((0, 'idle', 1), (right.vx, right.pose, right.facing))


class RealtimePuzzleTests(unittest.TestCase):
    def test_motor_order_cost_and_privacy(self):
        world = game.initial_world()
        plans = programs(pyra=[command('VENT')], flux=[command('REROUTE')])
        events = game.step(world, dict(reversed(plans.items())), 0)
        self.assertEqual(['vented', 'rerouted'], kinds(events))
        self.assertTrue(world.bridge_powered)
        self.assertEqual((3, 1, 4), (world.heat, world.coolant, world.energy))
        for event in events:
            self.assertNotIn('heat', event)
            self.assertNotRegex(event['text'], r'\d')
        game.step(world, programs(flux=[command('REROUTE')]), 0)
        self.assertEqual(4, world.energy)

    def test_hot_motor_wrong_role_range_air_and_resources_block_operations(self):
        for reason in ('hot', 'wrong_role', 'out_of_range', 'airborne', 'coolant', 'energy'):
            with self.subTest(reason=reason):
                world = game.initial_world()
                plans = programs(pyra=[command('VENT')], flux=[command('REROUTE')])
                if reason == 'hot':
                    plans['PYRA'] = []
                elif reason == 'wrong_role':
                    plans = programs([command('VENT')], [command('REROUTE')])
                elif reason == 'out_of_range':
                    world.robots['PYRA'].x = game.MOTOR_X - game.MOTOR_RANGE - 1
                elif reason == 'airborne':
                    world.robots['PYRA'].grounded = False
                    world.robots['PYRA'].y = 1
                elif reason == 'coolant':
                    world.coolant = 0
                else:
                    world.energy = 1
                start_energy = world.energy
                events = game.step(world, plans, 0)
                self.assertIn('blocked', kinds(events))
                self.assertFalse(world.bridge_powered)
                self.assertEqual(start_energy, world.energy)

    def test_collection_uses_grounded_post_motion_position_and_inclusive_radius(self):
        world = game.initial_world()
        world.bridge_powered = True
        spectra, flux = world.robots['SPECTRA'], world.robots['FLUX']
        spectra.x, spectra.y, spectra.grounded = game.SHARD_X - game.COLLECT_RADIUS, game.BANK_HEIGHT + 1, False
        flux.x, flux.y = game.CELL_X + game.COLLECT_RADIUS, game.BANK_HEIGHT
        events = game.step(world, programs([command('COLLECT')], flux=[command('COLLECT')]), 0)
        self.assertEqual(['landing', 'shard_collected', 'cell_collected', 'exit_unlocked'], kinds(events))
        self.assertEqual(8, world.energy)
        again = game.step(world, programs([command('COLLECT')], flux=[command('COLLECT')]), 0)
        self.assertEqual(['blocked', 'blocked'], kinds(again))
        self.assertEqual(8, world.energy)

    def test_worked_document_timeline_and_complete_third_window(self):
        world = game.initial_world()
        first, second, third = worked_windows()
        events = play(world, first)
        self.assertEqual([(1, 'vented'), (1, 'rerouted')], [(e['tick'], e['kind']) for e in events])
        self.assertEqual([1792, 1536, 1792], [world.robots[r].x for r in game.ROLES])
        events = play(world, second)
        self.assertEqual([2288, 2496, 2544], [world.robots[r].x for r in game.ROLES])
        self.assertTrue(all(b.y == 128 and b.grounded for b in world.robots.values()))
        landings = {e['role']: e['tick'] for e in events if e['kind'] == 'landing'}
        self.assertEqual({'SPECTRA': 151, 'PYRA': 167, 'FLUX': 151}, landings)
        self.assertIn((163, 'shard_collected'), [(e['tick'], e['kind']) for e in events])
        self.assertTrue(world.exit_unlocked)
        events = play(world, third)
        self.assertEqual([(241, 'cell_collected'), (281, 'completed')], [(e['tick'], e['kind']) for e in events])
        self.assertTrue(world.completed)
        final = world.replay_state()
        with self.assertRaises(ValueError):
            game.step(world, programs(), 0)
        self.assertEqual(final, world.replay_state())

    def test_omitting_each_checkpoint_requirement_prevents_success(self):
        for omission in ('vent', 'reroute', 'collect', 'one_at_exit'):
            with self.subTest(omission=omission):
                world = game.initial_world()
                first, second, third = worked_windows()
                if omission == 'vent':
                    first['PYRA'][0] = wait(1)
                elif omission == 'reroute':
                    first['FLUX'][0] = wait(1)
                elif omission == 'collect':
                    second['SPECTRA'][-1] = wait(1)
                else:
                    third['PYRA'] = []
                for plans in (first, second, third):
                    play(world, plans)
                self.assertFalse(world.completed)


if __name__ == '__main__':
    unittest.main()
