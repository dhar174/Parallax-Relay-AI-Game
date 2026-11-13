import copy
import unittest
from parallax_relay.state import initial_world, public_hud
from parallax_relay.render import render_png


class VisibilityTests(unittest.TestCase):
    def test_exact_heat_does_not_leak_through_events(self):
        world = initial_world()
        world.events = ['PYRA: vented motor; heat now 937']
        for role in world.robots:
            self.assertNotIn('937', str(public_hud(world, role)))

    def test_action_contract_does_not_reveal_hidden_item_locations(self):
        for role in initial_world().robots:
            contract = str(public_hud(initial_world(), role)['action_contract'])
            self.assertNotIn('x=9', contract)
            self.assertNotIn('x=10', contract)

    def test_heat_changes_only_thermal_and_spectator_pixels(self):
        a = initial_world(); b = copy.deepcopy(a); b.motor_heat = 1
        for role in ('SPECTRA', 'FLUX'):
            self.assertEqual(render_png(a, role), render_png(b, role))
        self.assertNotEqual(render_png(a, 'PYRA'), render_png(b, 'PYRA'))

    def test_shard_changes_only_optical_and_spectator_pixels(self):
        a = initial_world(); b = copy.deepcopy(a); b.shard_collected = True
        for role in ('PYRA', 'FLUX'):
            self.assertEqual(render_png(a, role), render_png(b, role))
        self.assertNotEqual(render_png(a, 'SPECTRA'), render_png(b, 'SPECTRA'))

    def test_cell_changes_only_electromagnetic_and_spectator_pixels(self):
        a = initial_world(); b = copy.deepcopy(a); b.cell_collected = True
        for role in ('PYRA', 'SPECTRA'):
            self.assertEqual(render_png(a, role), render_png(b, role))
        self.assertNotEqual(render_png(a, 'FLUX'), render_png(b, 'FLUX'))
