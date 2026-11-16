"""Split-aware registration and trusted-host room execution gates; all offline."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from parallax_relay.campaign_models import CampaignSpec, schedule, trial_settings
from parallax_relay.campaign import register, read_registration, run_campaign, CampaignError, frozen_inputs, execute_trial
from parallax_relay.campaign_analysis import analyze
from parallax_relay.provenance import canonical_hash
from parallax_relay.rooms import rooms, catalog_identity


def design(**kw):
    return dict(schema_version=2,protocol_version=2,mode='offline',stage='diagnostic',policies=['wait'],conditions=['disabled'],
                match={'max_turns':1,'max_attempts':1},campaign_max_calls=1000000,**kw)


class RoomCampaignTests(unittest.IsolatedAsyncioTestCase):
    def test_stage_membership_and_protocol_counts(self):
        for stage,count in [('pilot',105),('confirmatory',960)]:
            value=design();value.update(stage=stage,policies=['scripted','wait','uniform']);value.pop('conditions')
            spec=CampaignSpec.model_validate(value);trials=schedule(spec)
            self.assertEqual(len(trials),count)
            self.assertEqual(set(spec.rooms),{r.id for r in rooms(split='development' if stage=='pilot' else 'held_out')})
            self.assertTrue(all(t['split']==('development' if stage=='pilot' else 'held_out') for t in trials))
        for stage,selected in [('diagnostic',['ret_01']),('pilot',['split_span']),('confirmatory',['split_span']),('confirmatory',['ret_01'])]:
            value=design();value.update(stage=stage,rooms=selected,policies=['scripted','wait','uniform']);value.pop('conditions')
            with self.subTest(stage=stage,rooms=selected),self.assertRaises(ValueError):CampaignSpec.model_validate(value)
        legacy=CampaignSpec.model_validate({'schema_version':1,'campaign_max_calls':100000})
        self.assertEqual(legacy.protocol_version,1);self.assertEqual(legacy.rooms,['split_span']);self.assertEqual(len(schedule(legacy)),15)

    async def test_development_native_roundtrip_labels_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';value=design();value['rooms']=['dev_01']
            reg=register(value,root)
            self.assertEqual(reg['schema_version'],2);self.assertEqual(reg['frozen']['catalog'],catalog_identity())
            await run_campaign(root,offline=True)
            report=analyze(root);self.assertEqual(report['schema_version'],2)
            self.assertEqual(report['analysis_version'],2);self.assertEqual(report['completion_status'],'complete')
            self.assertTrue(report['trials'][0]['artifact_available'],report['trials'][0]['artifact_issues'])
            self.assertEqual(report['trials'][0]['family'],'crossing');self.assertEqual(report['trials'][0]['split'],'development')
            self.assertTrue(report['family_summaries']);self.assertTrue(report['split_summaries'])
            self.assertTrue(all('contrasts' not in row for row in report['family_summaries']))
            self.assertEqual(read_registration(root),reg)

    def test_cross_room_summaries_have_no_inferential_intervals_but_cells_retain_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';register(design(),root)
            report=analyze(root)
            for summary in [report['overall'],*report['family_summaries'],*report['split_summaries']]:
                self.assertNotIn('wilson_95',summary['operational_success'])
                self.assertIn('all_planned_bounds',summary['operational_success'])
            self.assertTrue(all('wilson_95' in cell['operational_success'] for cell in report['cells']))

    async def test_historical_registration_is_analyzable_but_not_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);root.joinpath('registration.json').write_text(Path('tests/fixtures/legacy_registration_v1.json').read_text())
            self.assertEqual(analyze(root)['counts']['planned'],1)
            with self.assertRaisesRegex(CampaignError,'fresh registration'):
                await run_campaign(root,offline=True)
            self.assertFalse((root/'started.json').exists());self.assertFalse((root/'.runner.lock').exists())

    async def test_protocol2_drift_stops_before_outputs_or_agents(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';reg=register(design(),root)
            changed=copy.deepcopy(reg['frozen']);changed['source']['status']='unavailable'
            with patch('parallax_relay.campaign.frozen_inputs',return_value=changed),patch('parallax_relay.campaign.make_policy',side_effect=AssertionError('no agent')):
                with self.assertRaisesRegex(CampaignError,'Frozen'):
                    await run_campaign(root,offline=True)
            self.assertFalse((root/'started.json').exists());self.assertFalse((root/'.runner.lock').exists())

    async def test_protocol2_rechecks_identity_before_each_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';reg=register(design(),root)
            changed=copy.deepcopy(reg['frozen']);changed['source']['revision']='b'*40
            with patch('parallax_relay.campaign.frozen_inputs',side_effect=[reg['frozen'],changed]),patch('parallax_relay.campaign.execute_trial') as execute:
                await run_campaign(root,offline=True)
            execute.assert_not_called()
            self.assertEqual(analyze(root)['campaign_stop']['reason'],'frozen_input_drift')

    def test_registration_rejects_rehashed_room_or_split_inconsistency(self):
        from parallax_relay.campaign import validate_registration
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';reg=register(design(),root)
            for key in ['family','split','catalog_sha256','room_sha256']:
                broken=copy.deepcopy(reg);broken['schedule'][0][key]='invalid'
                broken['sha256']=canonical_hash({k:v for k,v in broken.items() if k!='sha256'})
                with self.subTest(key=key),self.assertRaises(CampaignError):validate_registration(broken)

    def test_pilot_transition_freezes_all_but_permitted_stage_differences(self):
        from parallax_relay.campaign import validate_pilot_transition
        pilot=design();pilot.update(stage='pilot',policies=['scripted','wait','uniform']);pilot.pop('conditions')
        confirm=copy.deepcopy(pilot);confirm.update(stage='confirmatory',campaign_max_calls=2000000,scheduler_seed=42)
        a=CampaignSpec.model_validate(pilot);b=CampaignSpec.model_validate(confirm)
        frozen=frozen_inputs(a)
        with patch('parallax_relay.campaign.collect_source',return_value=frozen['source']):
            validate_pilot_transition(a,b,frozen,frozen_inputs(b))
        for section in ['source','environment','catalog','inputs']:
            broken=copy.deepcopy(frozen);broken[section]={}
            with self.subTest(section=section),self.assertRaises(CampaignError):validate_pilot_transition(a,b,frozen,broken)
        b2=b.model_copy(update={'match':b.match.model_copy(update={'max_output_tokens':1024})})
        with self.assertRaises(CampaignError):validate_pilot_transition(a,b2,frozen,frozen)

    async def test_bounded_registered_heldout_trial_and_forged_permit_rejected(self):
        from parallax_relay.room_execution import RoomExecutionPermit
        from parallax_relay.orchestrator import run_match
        from parallax_relay.config import MatchSettings
        from parallax_relay.policies import WaitAgent
        value=design();value.update(stage='confirmatory',policies=['scripted','wait','uniform']);value.pop('conditions')
        clean={'status':'clean','revision':'a'*40,'reason':None}
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=clean):
            pilot=Path(temp)/'pilot';pilot_value=copy.deepcopy(value);pilot_value['stage']='pilot'
            register(pilot_value,pilot)
            with patch('parallax_relay.campaign_analysis.analyze',return_value={'cohort_eligible':True}):
                reg=register(value,Path(temp)/'confirmation',pilot=pilot)
            spec=CampaignSpec.model_validate(reg['spec'])
            trial=next(t for t in reg['schedule'] if t['room']=='relay_01' and t['team']=='wait' and t['condition']=='disabled')
            receipt=await execute_trial(Path(temp)/'native',reg,spec,trial,{})
            self.assertEqual(receipt['stop_reason'],'turn_limit');self.assertEqual(receipt['result']['turns'],1)
            state=json.loads((Path(temp)/'native'/'trials'/trial['trial_id']/'final_state.json').read_text())
            self.assertEqual(set(state['motor_heats']),{'bridge_0','bridge_1'})
            wrong=next(t for t in reg['schedule'] if t['room']=='ret_01')
            permit=RoomExecutionPermit.from_registration(reg,trial)
            with self.assertRaisesRegex(ValueError,'held-out'):permit.validate(wrong['room'])
        class Fake:
            def validate(self,*args):pass
        with self.assertRaisesRegex(ValueError,'held-out'):
            await run_match({r:WaitAgent(r) for r in ('SPECTRA','PYRA','FLUX')},MatchSettings(room_id='ret_01'),room_permit=Fake())
