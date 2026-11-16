import unittest
import importlib.util
import json
from copy import deepcopy
from parallax_relay.state import initial_world

class RoomObservationTests(unittest.TestCase):
    def test_item_positions_do_not_change_other_sensor_views(self):
        from parallax_relay.observations import observe
        world=initial_world('relay_01')
        for field,value,owner in [('shard',8,'SPECTRA'),('cells',(2,4),'FLUX')]:
            changed=deepcopy(world);changed.room=world.room.model_copy(update={field:value})
            for role in ('SPECTRA','PYRA','FLUX'):
                with self.subTest(field=field,role=role):
                    self.assertEqual(observe(world,role).hud_json,observe(changed,role).hud_json)
                    if role==owner:self.assertNotEqual(observe(world,role).image_png,observe(changed,role).image_png)
                    else:self.assertEqual(observe(world,role).image_png,observe(changed,role).image_png)

    def test_public_vent_events_disclose_effect_but_not_exact_heat(self):
        from parallax_relay.state import Action,public_hud
        from parallax_relay.engine import resolve_turn
        world=initial_world('relay_01');changed=deepcopy(world);changed.motor_heats['bridge_0']=5
        actions={'SPECTRA':Action('WAIT'),'PYRA':Action('VENT'),'FLUX':Action('WAIT')}
        a,b=resolve_turn(world,actions),resolve_turn(changed,actions)
        self.assertNotEqual(a.events,b.events)
        for role in world.robots:
            self.assertEqual(public_hud(a,role),public_hud(b,role))
            self.assertIn('vented motor',public_hud(a,role)['recent_events'][0])
    def test_all_certificates_complete_private_goals_and_fixed_script_fails_heldout(self):
        self.assertIsNotNone(importlib.util.find_spec('parallax_relay.room_certificates'),'Certificates are missing')
        from parallax_relay.room_certificates import verify_catalog
        rows=verify_catalog()
        self.assertEqual(len(rows),9)
        self.assertTrue(all(row['win'] and row['private_goals_met'] for row in rows))
        self.assertTrue(all(not row['fixed_script_win'] for row in rows if row['split']=='held_out'))

    def test_relay_sensor_projections_are_private_and_hud_describes_mission(self):
        from parallax_relay.observations import observe
        from parallax_relay.prompts import SYSTEM_RULES
        world=initial_world('relay_01');changed=deepcopy(world);changed.motor_heats['bridge_1']=1
        for role in ('SPECTRA','FLUX'):
            self.assertEqual(observe(world,role).image_png,observe(changed,role).image_png)
            self.assertEqual(observe(world,role).hud_json,observe(changed,role).hud_json)
        self.assertNotEqual(observe(world,'PYRA').image_png,observe(changed,'PYRA').image_png)
        hud=observe(initial_world('ret_01'),'SPECTRA').hud
        self.assertIn('shard',hud['shared_goal'].lower())
        for secret in ('ret_01','retrieval_return','held_out','motor_heats','cells','certificate'):
            self.assertNotIn(secret,json.dumps(hud))
        for coordinate in ('x=4','x=12','x=0 through 12'):
            self.assertNotIn(coordinate,SYSTEM_RULES)
