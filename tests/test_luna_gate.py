"""Protocol-four registration and denial tests, without any provider calls."""
import copy
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.campaign import CampaignError, CampaignSpec, frozen_inputs, register, read_json
from parallax_relay.campaign_validation import validate_frozen
from parallax_relay.exploratory import luna_profile_spec, luna_profile_analysis

CLEAN={'status':'clean','revision':'a'*40,'reason':None}


class LunaGateTests(unittest.TestCase):
    def test_frozen_protocol4_covers_all_nine_rooms_and_descriptive_contract(self):
        spec=CampaignSpec.model_validate(luna_profile_spec('qualification'))
        value=frozen_inputs(spec)
        self.assertEqual(len(value['inputs']),9)
        self.assertEqual(value['analysis'],luna_profile_analysis())
        with patch('parallax_relay.campaign.collect_source',return_value=CLEAN):
            value=frozen_inputs(spec)
        validate_frozen(value,spec)
        value['analysis']['version']=True
        with self.assertRaises(ValueError):validate_frozen(value,spec)

    def test_unbound_supplement_and_validation_cannot_register(self):
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN):
            for stage in ('qualification','validation'):
                path=Path(temp)/stage
                with self.subTest(stage=stage),self.assertRaises(CampaignError):
                    register(luna_profile_spec(stage),path)
                self.assertFalse(path.exists())

    def test_duplicate_protocol4_and_downgrade_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'spec.json'
            for ending in (4,2):
                path.write_text('{"protocol_version":4,"protocol_version":'+str(ending)+'}')
                with self.subTest(ending=ending),self.assertRaises(CampaignError):read_json(path)

    def test_direct_forged_heldout_permit_denied_even_with_recomputed_hash(self):
        from parallax_relay.room_execution import RoomExecutionPermit
        from parallax_relay.provenance import canonical_hash
        from parallax_relay.campaign_models import schedule
        spec=CampaignSpec.model_validate(luna_profile_spec('validation'))
        with patch('parallax_relay.campaign.collect_source',return_value=CLEAN):value=frozen_inputs(spec)
        trial=schedule(spec)[0]
        reg={'schema_version':2,'spec':spec.model_dump(mode='json'),'pilot':None,
             'qualification':{'kind':'qualified','receipt_path':'/no/such/receipt',
                'receipt_sha256':'b'*64,'selection_sha256':'c'*64,'source_bridge_sha256':'d'*64},
             'schedule':[trial],'frozen':value}
        reg['sha256']=canonical_hash(reg)
        permit=RoomExecutionPermit(json.dumps(reg),json.dumps(trial),json.dumps(value))
        with self.assertRaises(ValueError):permit.validate(trial['room'])

    def test_direct_permit_rejects_duplicate_json_before_using_a_qualified_binding(self):
        from parallax_relay.room_execution import RoomExecutionPermit
        from parallax_relay.campaign_models import schedule, trial_exposure
        from parallax_relay.provenance import canonical_hash
        spec=CampaignSpec.model_validate(luna_profile_spec('validation'))
        binding={'kind':'qualified','receipt_path':'/fixture/receipt','receipt_sha256':'b'*64,
                 'selection_sha256':'c'*64,'source_bridge_sha256':'d'*64}
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN),patch(
                'parallax_relay.qualification.check_receipt',return_value={
                    'sha256':'b'*64,'selection_sha256':'c'*64,'source_bridge_sha256':'d'*64}):
            reg=register(luna_profile_spec('validation'),Path(temp)/'validation',qualification=Path('/fixture/receipt'))
        trial=reg['schedule'][0]
        raw=json.dumps(reg).replace('"pilot": null','"pilot": {}, "pilot": null')
        permit=RoomExecutionPermit(raw,json.dumps(trial),json.dumps(reg['frozen']))
        with patch('parallax_relay.qualification.check_binding',return_value=binding):
            with self.assertRaises(ValueError):permit.validate(trial['room'])

    def test_protocol4_analysis_is_descriptive_and_unknown_outcomes_stay_unknown(self):
        from parallax_relay.campaign_analysis import analyze
        binding={'kind':'selection','selection_path':'/fixture/selection','evidence_root':'/fixture/evidence',
                 'source_bridge_path':'/fixture/bridge','selection_sha256':'c'*64,'source_bridge_sha256':'d'*64}
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN),patch(
                'parallax_relay.qualification.selection_binding',return_value=binding):
            root=Path(temp)/'qualification'
            register(luna_profile_spec('qualification'),root,qualification_selection=Path('/fixture/selection'),
                     evidence_root=Path('/fixture/evidence'),source_bridge=Path('/fixture/bridge'))
            report=analyze(root)
            self.assertEqual((report['analysis_version'],report['profile_id']),(4,'exploratory-luna-under20-v1'))
            self.assertFalse(report['confirmatory_eligible'])
            self.assertEqual(report['counts']['planned'],5)
            self.assertIsNone(report['overall']['operational_success']['rate'])
            self.assertNotIn('wilson_95',json.dumps(report))
            self.assertEqual(report['contrasts'],[])

    def test_luna_preflight_denies_low_disk_or_missing_evidence_before_environment_and_clients(self):
        from parallax_relay.campaign import run_campaign, main
        binding={'kind':'selection','selection_path':'/fixture/selection','evidence_root':'/fixture/evidence',
                 'source_bridge_path':'/fixture/bridge','selection_sha256':'c'*64,'source_bridge_sha256':'d'*64}
        class ForbiddenEnvironment(dict):
            def keys(self):raise AssertionError('environment copied before gate')
            def __iter__(self):raise AssertionError('environment copied before gate')
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN),patch(
                'parallax_relay.qualification.selection_binding',return_value=binding):
            root=Path(temp)/'qualification'
            register(luna_profile_spec('qualification'),root,qualification_selection=Path('/fixture/selection'),
                     evidence_root=Path('/fixture/evidence'),source_bridge=Path('/fixture/bridge'))
            before={p.name for p in root.iterdir()}
            with patch('parallax_relay.campaign._available_disk_bytes',return_value=5*1024**3-1),patch(
                    'parallax_relay.campaign.HTTPAgent',side_effect=AssertionError('client constructed')):
                with self.assertRaisesRegex(CampaignError,'5 GiB'):
                    asyncio.run(run_campaign(root,live=True,environ=ForbiddenEnvironment(OPENAI_API_KEY='FAKE')))
            with patch('parallax_relay.campaign._available_disk_bytes',return_value=10*1024**3),patch(
                    'parallax_relay.qualification.check_binding',side_effect=ValueError('invalid evidence')),patch(
                    'parallax_relay.campaign.load_env_file',side_effect=AssertionError('credentials read')),patch(
                    'parallax_relay.campaign.os.environ',ForbiddenEnvironment(OPENAI_API_KEY='FAKE')),patch('sys.stderr'):
                self.assertEqual(main(['run','--campaign',str(root),'--live','--env-file','/fixture/credentials']),2)
            self.assertEqual({p.name for p in root.iterdir()},before)


if __name__=='__main__':unittest.main()
