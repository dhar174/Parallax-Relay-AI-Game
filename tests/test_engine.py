import copy
import unittest
from parallax_relay import Action, initial_world, resolve_turn
from parallax_relay.state import public_hud, ARTIFACT, ENERGY_CELL, EXIT
from parallax_relay.engine import score
from parallax_relay.scripted import PLAN
from parallax_relay.render import render_png


def commands(**kwargs):
    return {role: kwargs.get(role, Action("WAIT"))
            for role in ("SPECTRA","PYRA","FLUX")}


class ParallaxTests(unittest.TestCase):
    def non_move_cases(self):
        cases = [('WAIT', 'PYRA'), ('VENT', 'PYRA'), ('REROUTE', 'FLUX'),
                 ('COLLECT', 'SPECTRA'), ('COLLECT', 'FLUX'), ('UNLOCK', 'FLUX')]
        for kind, role in cases:
            world = initial_world()
            world.motor_heat = 2  # A canonical REROUTE can safely succeed.
            if kind == 'COLLECT':
                world.robots[role].x = ARTIFACT if role == 'SPECTRA' else ENERGY_CELL
            elif kind == 'UNLOCK':
                world.robots[role].x = EXIT
            yield kind, role, world

    def test_non_move_parameters_are_engine_illegal_without_mutating_inputs(self):
        for kind, role, world in self.non_move_cases():
            for direction, steps in [(1, 0), (-1, 0), (0, 1), (0, -1), (42, 99)]:
                with self.subTest(kind=kind, role=role, direction=direction, steps=steps):
                    actions = commands(**{role: Action(kind, direction, steps)})
                    original_world, original_actions = world.snapshot(), dict(actions)
                    after = resolve_turn(world, actions)
                    expected = resolve_turn(world, commands()).snapshot()
                    actual = after.snapshot()
                    actual.pop('events'); expected.pop('events')
                    self.assertEqual(actual, expected)
                    self.assertIn(f'{role}: invalid {kind} parameters; treated as WAIT', after.events)
                    self.assertEqual(after.turn, 1)
                    self.assertEqual(world.snapshot(), original_world)
                    self.assertEqual(actions, original_actions)

    def test_canonical_non_move_actions_keep_their_effects(self):
        for kind, role, world in self.non_move_cases():
            with self.subTest(kind=kind, role=role):
                after = resolve_turn(world, commands(**{role: Action(kind)}))
                if kind == 'VENT':
                    self.assertEqual((after.motor_heat, after.coolant), (0, 1))
                elif kind == 'REROUTE':
                    self.assertTrue(after.bridge_extended)
                    self.assertEqual((after.energy, after.motor_heat), (4, 4))
                elif kind == 'COLLECT' and role == 'SPECTRA':
                    self.assertTrue(after.shard_collected)
                elif kind == 'COLLECT':
                    self.assertTrue(after.cell_collected)
                    self.assertEqual(after.energy, 8)
                elif kind == 'UNLOCK':
                    self.assertTrue(after.exit_unlocked)
                    self.assertEqual(after.energy, 5)
                else:
                    self.assertEqual((after.energy, after.coolant, after.motor_heat), (6, 2, 2))
                self.assertFalse(any('invalid' in event for event in after.events))

    def test_invalid_control_does_not_suppress_other_roles_or_change_ordering(self):
        actions = commands(PYRA=Action('VENT'), FLUX=Action('REROUTE', 1, 0))
        after = resolve_turn(initial_world(), actions)
        self.assertEqual((after.motor_heat, after.coolant, after.energy), (1, 1, 6))
        self.assertFalse(after.bridge_extended)
        self.assertEqual(after.snapshot(), resolve_turn(
            initial_world(), dict(reversed(list(actions.items())))).snapshot())
        # Invalid venting must not protect the team from a valid, unsafe reroute.
        after = resolve_turn(initial_world(), commands(
            PYRA=Action('VENT', 42, 99), FLUX=Action('REROUTE')))
        self.assertEqual((after.motor_heat, after.coolant, after.energy), (6, 2, 4))
        self.assertGreater(after.robots['FLUX'].damage, 0)

    def test_scripted_game_wins_and_fulfills_all_objectives(self):
        w = initial_world()
        for action in PLAN:
            w = resolve_turn(w, action)
        self.assertTrue(w.win)
        self.assertEqual(w.turn,7)
        self.assertEqual(w.energy,5)
        self.assertTrue(w.shard_collected)
        self.assertTrue(w.cell_collected)
        self.assertEqual(score(w), {"SPECTRA":100,"PYRA":100,"FLUX":100})

    def test_bridge_requires_vent_for_safe_activation(self):
        w = resolve_turn(initial_world(),commands(FLUX=Action("REROUTE")))
        self.assertFalse(w.bridge_extended)
        self.assertEqual(w.energy,4)
        self.assertGreater(w.robots["FLUX"].damage,0)
        w2 = resolve_turn(initial_world(),commands(PYRA=Action("VENT"),FLUX=Action("REROUTE")))
        self.assertTrue(w2.bridge_extended)
        self.assertEqual(w2.robots["FLUX"].damage,0)

    def test_gap_is_impassable_without_bridge(self):
        w=resolve_turn(initial_world(),commands(FLUX=Action("MOVE",direction=1,steps=2)))
        self.assertEqual(w.robots["FLUX"].x,4)

    def test_private_goals_do_not_leak_into_other_hud(self):
        w=initial_world()
        spectator_goal=public_hud(w,"SPECTRA")["your_private_goal"]
        flux_hud=public_hud(w,"FLUX")
        self.assertNotIn(spectator_goal,str(flux_hud))
        self.assertNotIn("motor_heat",str(flux_hud))
        self.assertNotIn("shard_collected",str(flux_hud))

    def test_simultaneous_resolution_is_action_dict_order_invariant(self):
        w=initial_world()
        a=commands(PYRA=Action("VENT"),FLUX=Action("REROUTE"))
        self.assertEqual(resolve_turn(w,a).snapshot(),resolve_turn(w,dict(reversed(list(a.items())))).snapshot())
        self.assertFalse(w.bridge_extended) # pure, doesn't mutate original

    def test_render_distinct_valid_pngs(self):
        w=initial_world()
        imgs={r:render_png(w,r) for r in ("SPECTRA","PYRA","FLUX","ECHO")}
        for raw in imgs.values():
            self.assertEqual(raw[:8],b"\x89PNG\r\n\x1a\n")
        self.assertEqual(len(set(imgs.values())),4)


if __name__=="__main__":
    unittest.main()
