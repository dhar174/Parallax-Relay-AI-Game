"""Circuit Relief uses only information visible in the sampled FLUX observation."""
from io import BytesIO
from itertools import combinations
import unittest

from PIL import Image

from parallax_relay.protocol import ROLES
from parallax_relay.realtime import physics
from parallax_relay.realtime.flux_view import (
    _robot_feet,
    _signature_positions,
    render_circuit_relief,
)
from parallax_relay.realtime.observations import observe, sample_flux_circuit
from parallax_relay.realtime.settings import Settings
from parallax_relay.render import px


def pixels(world):
    png = render_circuit_relief(sample_flux_circuit(world))
    with Image.open(BytesIO(png)) as image:
        return image.convert('RGB')


class CircuitReliefTests(unittest.TestCase):
    def test_power_dominates_and_energy_cell_disappears_after_collection(self):
        world = physics.initial_world()
        idle = pixels(world)
        world.bridge_powered = True
        powered = pixels(world)
        world.cell_collected = True
        collected = pixels(world)
        self.assertEqual(powered.size, (850, 295))
        self.assertLess(max(idle.getpixel((px(6), 219))), 100)
        self.assertEqual(powered.getpixel((px(6), 219)), (240, 255, 248))
        self.assertEqual(powered.getpixel((px(10), 128)), (240, 255, 248))
        self.assertLess(max(collected.getpixel((px(10), 128))), 100)
        path = (px(5), 209, px(7), 230)
        self.assertEqual(powered.crop(path).tobytes(), collected.crop(path).tobytes())

    def test_visible_signatures_fit_when_contacts_share_or_border_the_relay(self):
        world = physics.initial_world()
        world.bridge_powered = True
        for columns, height in (((4, 4, 4), 0), ((3, 4, 4), 0), ((0, 0, 0), 0),
                                ((3, 3, 5), -60),
                                ((4, 4, 4), 10), ((10, 10, 10), 200),
                                ((12, 12, 12), physics.FALL_LIMIT + 1)):
            with self.subTest(columns=columns, height=height):
                for role, column in zip(ROLES, columns):
                    world.robots[role].x = column * physics.TILE
                world.robots['FLUX'].y = height
                sample = sample_flux_circuit(world)
                marks = tuple(_signature_positions(_robot_feet(sample), sample))
                self.assertEqual({role for role, _, _ in marks}, set(ROLES))
                image = pixels(world)
                for _, _, (x, y) in marks:
                    self.assertTrue(12 <= x < 838 and 9 <= y < 286)
                    glyph = image.crop((x - 6, y - 7, x + 7, y + 8))
                    self.assertTrue(any(min(glyph.getpixel((u, v))) > 180
                                        for u in range(glyph.width) for v in range(glyph.height)))
                for (_, _, (x1, y1)), (_, _, (x2, y2)) in combinations(marks, 2):
                    self.assertTrue(abs(x1 - x2) > 24 or abs(y1 - y2) > 18)

    def test_other_roles_private_state_and_finer_position_do_not_affect_the_frame(self):
        world = physics.initial_world()
        settings = Settings.offline()
        before = observe(world, 'FLUX', 1, settings)
        pyra_before = observe(world, 'PYRA', 1, settings)
        spectra_before = observe(world, 'SPECTRA', 1, settings)
        sample = sample_flux_circuit(world)
        image = render_circuit_relief(sample)

        world.heat += 7
        world.shard_collected = True
        world.robots['PYRA'].x += physics.TILE // 4
        world.robots['PYRA'].y += physics.BANK_HEIGHT
        world.robots['SPECTRA'].y += physics.BANK_HEIGHT
        after = observe(world, 'FLUX', 1, settings)

        self.assertNotEqual(observe(world, 'PYRA', 1, settings).image_png, pyra_before.image_png)
        self.assertNotEqual(observe(world, 'SPECTRA', 1, settings).image_png, spectra_before.image_png)
        self.assertEqual((after.image_png, after.hud), (before.image_png, before.hud))
        self.assertEqual(sample_flux_circuit(world), sample)
        self.assertEqual(render_circuit_relief(sample_flux_circuit(world)), image)


if __name__ == '__main__':
    unittest.main()
