import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import run_match
from parallax_relay.policies import WaitAgent
from parallax_relay.provenance import read_provenance,canonical_hash
from parallax_relay.recording import Recorder


class RoomRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_development_room_is_bound_to_v3_native_records(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder=Recorder(Path(temp)/'run',{})
            result=await run_match({r:WaitAgent(r) for r in ('SPECTRA','PYRA','FLUX')},
                MatchSettings(room_id='dev_01',max_turns=1),recorder=recorder)
            self.assertEqual(result.world.room.id,'dev_01')
            manifest=json.loads((recorder.out/'manifest.json').read_text())
            self.assertEqual(manifest['schema_version'],3);self.assertEqual(result.summary()['schema_version'],3)
            provenance=read_provenance(manifest)
            self.assertEqual(provenance['schema_version'],3)
            self.assertEqual(provenance['inputs']['schemas']['value']['request_format_version'],3)
            self.assertEqual(provenance['inputs']['room']['value']['definition']['id'],'dev_01')
            broken=json.loads(json.dumps(manifest));room=broken['provenance']['inputs']['room']
            room['value']['initial_state']['motor_heats']={'unknown':1};room['sha256']=canonical_hash(room['value'])
            with self.assertRaises(ValueError):read_provenance(broken)

    async def test_direct_heldout_run_is_rejected_before_any_agent_call(self):
        calls=[]
        class Agent:
            async def respond(self,request):calls.append(request);raise AssertionError('must not call')
        with self.assertRaisesRegex(ValueError,'held-out'):
            await run_match({r:Agent() for r in ('SPECTRA','PYRA','FLUX')},MatchSettings(room_id='ret_01'))
        self.assertEqual(calls,[])


class RoomInterfaceTests(unittest.TestCase):
    def test_smoke_profile_v1_hash_stays_frozen(self):
        from scripts.live_smoke import load_profile,profile_digest
        self.assertEqual(profile_digest(load_profile()),'4e90aa1af7d2571bf422d5eada7574f1dcfe800f9f6f10844411906aa07ac5b3')

    def test_v3_archive_uses_embedded_definition_instead_of_current_catalog(self):
        from parallax_relay.provenance import RunProvenance
        from parallax_relay.state import initial_world
        record=RunProvenance();record.begin(MatchSettings(),{},initial_world().snapshot())
        data=record.snapshot();room=data['inputs']['room']
        room['value']['id']=room['value']['definition']['id']=room['value']['initial_state']['room_id']='archived_room'
        data['execution']['value']['settings']['room_id']='archived_room'
        for section in (room,data['execution']):section['sha256']=canonical_hash(section['value'])
        self.assertEqual(read_provenance({'provenance':data}),data)

    def test_legacy_provenance_v2_does_not_acquire_current_setting_defaults(self):
        value=json.loads((Path(__file__).parent/'fixtures/legacy_provenance_v2.json').read_text())
        self.assertEqual(read_provenance(value),value['provenance'])
        self.assertNotIn('room_id',value['provenance']['execution']['value']['settings'])

    def test_cli_lists_metadata_and_refuses_heldout_without_output(self):
        from parallax_relay.play import main
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(main(['--list-rooms']),0)
            rows=json.loads(out.getvalue());self.assertEqual(len(rows),9)
            self.assertTrue(all(set(row)=={'id','version','family','split'} for row in rows))
            with tempfile.TemporaryDirectory() as temp:
                dest=Path(temp)/'run'
                self.assertEqual(main(['--mock','--room','ret_01','--out',str(dest)]),2)
                self.assertFalse(dest.exists())
        self.assertIn('held-out',err.getvalue())
