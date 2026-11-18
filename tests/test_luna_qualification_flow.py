"""A real native-record flow using fake WAIT providers, never model evidence."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from parallax_relay import qualification as q
from parallax_relay.campaign import register, run_campaign, atomic_json, frozen_inputs, _execution_preflight
from parallax_relay.campaign_analysis import analyze, write_report
from parallax_relay.campaign_models import CampaignSpec
from parallax_relay.exploratory import luna_profile_spec
from parallax_relay.policies import WaitAgent
from parallax_relay.room_execution import RoomExecutionPermit
from parallax_relay.provenance import canonical_hash

OLD={'status':'clean','revision':q.ORIGIN_REVISION,'reason':None}
NEW={'status':'clean','revision':'b'*40,'reason':None}


class FakeProvider:
    def __init__(self,*args,**kwargs):pass
    async def respond(self,request):return await WaitAgent(request.role).respond(request)
    async def close(self):pass


class LunaQualificationFlowTests(unittest.TestCase):
    def test_native_supplement_receipt_heldout_and_rehashed_tamper_denial(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);origin=base/'origin';reportroot=base/'origin-report'
            raw=luna_profile_spec('validation')
            raw.update(protocol_version=2,stage='diagnostic',rooms=['split_span','dev_01','dev_02'],
                       campaign_max_calls=20736,campaign_max_estimated_cost_usd=15.0)
            sources=('parallax_relay.campaign.collect_source','parallax_relay.provenance.collect_source',
                     'parallax_relay.campaign_analysis.collect_source')
            with patch(sources[0],return_value=OLD),patch(sources[1],return_value=OLD),patch(sources[2],return_value=OLD),patch(
                    'parallax_relay.campaign.HTTPAgent',FakeProvider),patch('parallax_relay.campaign.asyncio.sleep',new=AsyncMock()):
                reg=register(raw,origin)
                asyncio.run(run_campaign(origin,live=True,environ={'OPENAI_API_KEY':'FAKE'}))
                report=analyze(origin);write_report(report,reportroot)
            self.assertEqual(report['completion_status'],'complete')
            selection={'schema_version':1,'profile_id':q.PROFILE_ID,'origin_source':OLD,
                'environment_sha256':reg['frozen']['environment']['sha256'],
                'inputs_sha256':canonical_hash(reg['frozen']['inputs']),
                'origins':{'fixture':{'campaign':'origin','report':'origin-report','registration_sha256':reg['sha256'],
                    'files':{str(p.relative_to(base)):q.file_hash(p) for p in
                        [origin/'registration.json',origin/'ledger.jsonl',origin/'started.json',reportroot/'report.json',
                         *[reportroot/(n+'.csv') for n in ('trials','cells','attempts')]]}}},
                'selected':[],'missing':[],'history_files':{'origin/registration.json':q.file_hash(origin/'registration.json')},
                'prior_accounting':{'paid_attempts':sum(r['calls_started'] for r in report['trials'] if r['team']=='models'),
                    'estimated_usd_decimal':'0','known_usage_estimated_usd_decimal':'0','retained_estimate_usd_decimal':'0',
                    'original_failed_trial_retained':True,'earlier_q_allowance_usd_decimal':'0.25'}}
            rows={r['trial_id']:r for r in report['trials']}
            for trial in reg['schedule']:
                cell={k:trial[k] for k in ('room','team','condition','repetition')}
                if trial['room']=='split_span' and trial['team']=='models':selection['missing'].append(cell)
                else:
                    selection['selected'].append({'origin':'fixture','trial_id':trial['trial_id'],'cell':cell,
                        'artifacts':q.native_inventory(origin/'trials'/trial['trial_id'],rows[trial['trial_id']]['turns'])})
            selectionpath=base/'selection.json';atomic_json(selectionpath,selection)
            # Source review is independently tested. Here replace only its host
            # identity boundary so actual evidence/registration/permit logic can
            # be exercised in a temporary fixture without changing real Git.
            bridgepath=base/'bridge.json';atomic_json(bridgepath,{'sha256':'d'*64})
            with patch.object(q,'SELECTION_PATH',selectionpath),patch.object(q,'check_bridge',return_value={'sha256':'d'*64}),patch.object(
                    q,'_git',return_value=json.dumps(selection).encode()),patch(sources[0],return_value=NEW),patch(
                    sources[1],return_value=NEW),patch(sources[2],return_value=NEW),patch(
                    'parallax_relay.campaign.HTTPAgent',FakeProvider),patch('parallax_relay.campaign.asyncio.sleep',new=AsyncMock()):
                audit=q.audit_selection(selectionpath,base)
                self.assertEqual((audit['models'],audit['controls']),(10,45))
                supplement=base/'supplement'
                supplementreg=register(luna_profile_spec('qualification'),supplement,
                    qualification_selection=selectionpath,evidence_root=base,source_bridge=bridgepath)
                self.assertIsNone(supplementreg['pilot'])
                asyncio.run(run_campaign(supplement,live=True,environ={'OPENAI_API_KEY':'FAKE'}))
                receipt=q.build_receipt(supplement);receiptpath=base/'qualified.json';atomic_json(receiptpath,receipt)
                self.assertEqual(q.check_receipt(receiptpath)['counts'],{'models':15,'controls':45,'total':60})
                self.assertFalse(receipt['confirmatory_eligible'])
                validation=base/'validation'
                vreg=register(luna_profile_spec('validation'),validation,qualification=receiptpath)
                self.assertEqual(len(vreg['schedule']),120)
                trial=next(t for t in vreg['schedule'] if t['team']=='wait')
                permit=RoomExecutionPermit.from_registration(vreg,trial)
                permit.validate(trial['room'])
                before={p.name for p in validation.iterdir()}
                tampered=copy.deepcopy(receipt);tampered['counts']['models']=16
                tampered['sha256']=canonical_hash({k:v for k,v in tampered.items() if k!='sha256'})
                atomic_json(receiptpath,tampered)
                with self.assertRaises(ValueError):q.check_receipt(receiptpath)
                with self.assertRaises(ValueError):permit.validate(trial['room'])
                with self.assertRaises(ValueError):_execution_preflight(validation,vreg,offline=False,live=True)
                self.assertEqual({p.name for p in validation.iterdir()},before)
                atomic_json(receiptpath,receipt)
                selected=selection['selected'][0];native=origin/'trials'/selected['trial_id']/'turn_00_flux.png'
                saved=native.read_bytes();native.write_bytes(b'corrupt')
                with self.assertRaises(ValueError):q.check_receipt(receiptpath)
                native.write_bytes(saved)
                # Rehashing both receipt and native manifest is insufficient:
                # the committed selection and own-origin provenance still bind.
                duplicate = origin/'trials'/selected['trial_id']/'calls.jsonl'
                original_calls = duplicate.read_bytes()
                modified_calls = original_calls.replace(b'"attempt": 1', b'"attempt": 2, "attempt": 1', 1)
                self.assertNotEqual(modified_calls, original_calls)
                try:
                    duplicate.write_bytes(modified_calls)
                    with self.assertRaises(ValueError):
                        q.check_receipt(receiptpath)
                finally:
                    duplicate.write_bytes(original_calls)
                self.assertTrue(q.check_receipt(receiptpath)['qualified'])


if __name__=='__main__':unittest.main()
