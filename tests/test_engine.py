import copy
import unittest
from parallax_relay import Action, initial_world, resolve_turn
from parallax_relay.state import public_hud
from parallax_relay.engine import score
from parallax_relay.scripted import PLAN
from parallax_relay.render import render_png


def commands(**kwargs):
    return {role: kwargs.get(role, Action("WAIT"))
            for role in ("SPECTRA","PYRA","FLUX")}


class ParallaxTests(unittest.TestCase):
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
