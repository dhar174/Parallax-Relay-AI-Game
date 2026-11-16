"""Room identity, authoritative transitions and hidden-state boundaries."""
import importlib.util
import unittest
from copy import deepcopy
import json

from parallax_relay.state import Action, initial_world
from parallax_relay.engine import resolve_turn


class RoomTests(unittest.TestCase):
    def test_catalog_selects_nine_immutable_rooms_and_rejects_unknown_ids(self):
        self.assertIsNotNone(importlib.util.find_spec('parallax_relay.rooms'), 'Room catalog is missing')
        from parallax_relay.rooms import get_room, rooms
        self.assertEqual([r.id for r in rooms(split='development')], ['split_span','dev_01','dev_02'])
        self.assertEqual(len(rooms(split='held_out')),6)
        with self.assertRaises(ValueError):get_room('../unknown')
        with self.assertRaises(ValueError):get_room('split_span').width=9

    def test_retrieval_requires_shard_and_legacy_extraction_does_not(self):
        for room_id,expected in [('split_span',True),('ret_01',False)]:
            world=initial_world(room_id)
            for robot in world.robots.values():robot.x=world.room.exit
            world.exit_unlocked=True
            after=resolve_turn(world,{role:Action('WAIT') for role in world.robots})
            self.assertEqual(after.win,expected)
            self.assertFalse(world.win)

    def test_relay_controllers_activate_only_their_own_bridge(self):
        world=initial_world('relay_01');diagnostics={}
        first=resolve_turn(world,{'SPECTRA':Action('MOVE',1,2),'PYRA':Action('VENT'),'FLUX':Action('REROUTE')},diagnostics=diagnostics)
        self.assertEqual(first.powered_bridges,{'bridge_0'})
        self.assertEqual(first.robots['SPECTRA'].x,3)
        first.robots['SPECTRA'].x=5
        blocked=resolve_turn(first,{r:Action('MOVE',1,2) if r=='SPECTRA' else Action('WAIT') for r in first.robots})
        self.assertEqual(blocked.robots['SPECTRA'].x,5)
        self.assertEqual(first.motor_heats,{'bridge_0':3,'bridge_1':4})
        self.assertEqual(world.powered_bridges,set())

    def test_room_validation_rejects_ambiguous_controls_and_hidden_objects_in_gaps(self):
        self.assertIsNotNone(importlib.util.find_spec('parallax_relay.rooms'))
        from parallax_relay.rooms import get_room,RoomDefinition
        data=get_room('relay_01').model_dump()
        data['bridges']=(data['bridges'][0],{**data['bridges'][1],'motor':4})
        with self.assertRaises(ValueError):RoomDefinition.model_validate(data)
        data=get_room('split_span').model_dump();data['version']=True
        with self.assertRaises(ValueError):RoomDefinition.model_validate(data)
        data=get_room('ret_01').model_dump();data['shard']=3
        with self.assertRaises(ValueError):RoomDefinition.model_validate(data)

