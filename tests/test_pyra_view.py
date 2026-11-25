"""Thermal Bloom preserves approved heat cues and PYRA's role boundary."""

from io import BytesIO
from itertools import combinations
import unittest

from PIL import Image, ImageChops

from parallax_relay.protocol import ROLES
from parallax_relay.realtime import physics
from parallax_relay.realtime.observations import observe, sample_pyra_thermal
from parallax_relay.realtime.pyra_view import _robot_feet, _signature_positions, render_thermal_bloom
from parallax_relay.realtime.settings import Settings


def pixels(world):
    png = render_thermal_bloom(sample_pyra_thermal(world))
    with Image.open(BytesIO(png)) as image:
        return image.convert('RGB')


class ThermalBloomTests(unittest.TestCase):
    def test_venting_contracts_and_dims_the_motor_and_clears_meter_segments(self):
        world = physics.initial_world()
        images = []
        bright_areas = []
        for heat in range(physics.HEAT_LIMIT + 1):
            world.heat = heat
            image = pixels(world)
            self.assertEqual(image.size, (850, 295))
            images.append(image)
            gray = image.convert('L')
            bright_areas.append(sum(gray.crop((250, 149, 366, 222)).histogram()[146:]))
            meter = [gray.getpixel((90 + 25 * i, 64)) > 100 for i in range(physics.HEAT_LIMIT)]
            self.assertEqual(meter, [i < heat for i in range(physics.HEAT_LIMIT)])
        before, after = images[physics.HEAT_LIMIT], images[physics.HEAT_LIMIT - physics.VENT_COOLING]
        self.assertGreaterEqual(bright_areas[4], 5 * bright_areas[1])
        self.assertTrue(all(left < right for left, right in zip(bright_areas, bright_areas[1:])))
        self.assertIsNone(ImageChops.difference(before, after).crop((510, 0, 850, 295)).getbbox())

    def test_signatures_fit_even_when_robots_cluster_around_the_motor(self):
        world = physics.initial_world()
        for columns, height in (((4, 4, 4), 0), ((3, 4, 4), 0), ((4, 4, 4), 20),
                                ((5, 4, 4), -60), ((12, 12, 12), physics.FALL_LIMIT + 1)):
            with self.subTest(columns=columns, height=height):
                for role, column in zip(ROLES, columns):
                    world.robots[role].x = column * physics.TILE
                world.robots['PYRA'].y = height
                sample = sample_pyra_thermal(world)
                positions = tuple(_signature_positions(_robot_feet(sample)))
                self.assertEqual({role for role, _, _ in positions}, set(ROLES))
                image = pixels(world)
                for _, _, (x, y) in positions:
                    self.assertTrue(10 <= x < 840 and 9 <= y < 286)
                    letter = image.crop((x - 6, y - 7, x + 7, y + 8)).convert('L')
                    self.assertGreater(letter.getextrema()[1], 150)
                for (_, _, (x1, y1)), (_, _, (x2, y2)) in combinations(positions, 2):
                    self.assertTrue(abs(x1 - x2) > 20 or abs(y1 - y2) > 18)

    def test_private_item_states_and_finer_teammate_positions_leave_thermal_view_identical(self):
        world = physics.initial_world()
        settings = Settings.offline()
        before = observe(world, 'PYRA', 1, settings)
        flux = observe(world, 'FLUX', 1, settings)
        spectra = observe(world, 'SPECTRA', 1, settings)
        sample = sample_pyra_thermal(world)
        image = render_thermal_bloom(sample)

        world.cell_collected = world.shard_collected = True
        world.robots['FLUX'].x += physics.TILE // 4
        world.robots['FLUX'].y += physics.BANK_HEIGHT
        world.robots['SPECTRA'].y += physics.BANK_HEIGHT
        after = observe(world, 'PYRA', 1, settings)

        self.assertNotEqual(observe(world, 'FLUX', 1, settings).image_png, flux.image_png)
        self.assertNotEqual(observe(world, 'SPECTRA', 1, settings).image_png, spectra.image_png)
        self.assertEqual((after.image_png, after.hud), (before.image_png, before.hud))
        self.assertEqual(sample_pyra_thermal(world), sample)
        self.assertEqual(render_thermal_bloom(sample_pyra_thermal(world)), image)


if __name__ == '__main__':
    unittest.main()
