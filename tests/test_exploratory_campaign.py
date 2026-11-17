"""Offline protocol-3 gates; dummy identities never establish model evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from parallax_relay.campaign import (CampaignError, frozen_inputs, register,
    read_registration, validate_registration, validate_pilot_transition, run_campaign)
from parallax_relay.campaign_analysis import analyze, write_report
from parallax_relay.campaign_models import CampaignSpec
from parallax_relay.campaign_validation import validate_frozen
from parallax_relay.exploratory import profile_spec
from parallax_relay.provenance import canonical_hash

CLEAN = {'status': 'clean', 'revision': 'a'*40, 'reason': None}
ALL_ROOMS = {'split_span','dev_01','dev_02','ret_01','ret_02','ret_03',
             'relay_01','relay_02','relay_03'}


def eligible_pilot_report():
    # Gate-focused analyzer fixture; separate real-driver tests cover artifacts.
    return {'cohort_eligible': True, 'completion_status': 'complete',
            'analysis_source': CLEAN, 'anomalies': [],
            'trials': [{'stop_reason': 'turn_limit', 'cleanup_status': 'ok'} for _ in range(60)]}


class ExploratoryCampaignTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for target in ('parallax_relay.campaign.collect_source',
                       'parallax_relay.campaign_analysis.collect_source',
                       'parallax_relay.provenance.collect_source'):
            mocked=patch(target, return_value=CLEAN)
            mocked.start();self.addCleanup(mocked.stop)

    def test_frozen_identity_covers_all_nine_rooms_with_no_inferential_contract(self):
        spec=CampaignSpec.model_validate(profile_spec('pilot'))
        value=frozen_inputs(spec)
        self.assertEqual(set(value['inputs']),ALL_ROOMS)
        self.assertEqual(value['analysis'],{
            'version':3,'profile_id':'exploratory-under20-v1',
            'evidence_class':'exploratory','method':'descriptive_per_room',
            'bootstrap_resamples':0,'seed':0,'percentile':None,'prng':None,
            'concurrency':1,'primary_contrast':['full','disabled']})
        validate_frozen(value,spec,version=2)
        for key,bad in [('bootstrap_resamples',True),('seed',False),('version',3.0)]:
            broken=copy.deepcopy(value);broken['analysis'][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_frozen(broken,spec,version=2)

    def test_pilot_registration_roundtrips_and_strictly_rejects_rehashed_numeric_schedule_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';registration=register(profile_spec('pilot'),root)
            self.assertEqual(read_registration(root),registration)
            self.assertEqual(len(registration['schedule']),60)
            for key,bad in [('repetition',False),('room_version',True)]:
                changed=copy.deepcopy(registration);changed['schedule'][0][key]=bad
                changed['sha256']=canonical_hash({k:v for k,v in changed.items() if k!='sha256'})
                with self.subTest(key=key),self.assertRaises(CampaignError):
                    validate_registration(changed)

    def test_duplicate_profile_spec_and_registration_keys_are_rejected_at_json_boundary(self):
        from parallax_relay.campaign import main, read_json
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);spec=base/'pilot.json'
            spec.write_text(json.dumps(profile_spec('pilot')).replace('"campaign_max_calls": 10368','"campaign_max_calls": 999999, "campaign_max_calls": 10368'))
            with self.assertRaises(CampaignError):read_json(spec)
            with patch('sys.stderr'):
                self.assertEqual(main(['register','--spec',str(spec),'--out',str(base/'bad')]),2)
            self.assertFalse((base/'bad').exists())
            root=base/'registered';register(profile_spec('pilot'),root)
            path=root/'registration.json'
            path.write_text(path.read_text().replace('"campaign_max_calls": 10368','"campaign_max_calls": 999999, "campaign_max_calls": 10368'))
            with self.assertRaises(CampaignError):read_registration(root)
            legacy=profile_spec('pilot');legacy.update(protocol_version=2,repetitions=5,campaign_max_estimated_cost_usd=500.0)
            spec.write_text(json.dumps(legacy))
            self.assertEqual(CampaignSpec.model_validate(read_json(spec)).protocol_version,2)
            spec.write_text(json.dumps(legacy).replace('"protocol_version": 2','"protocol_version": 3, "protocol_version": 2'))
            with self.assertRaises(CampaignError):read_json(spec)

    def test_validation_requires_eligible_nonbinding_same_profile_pilot_and_freezes_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);pilot=base/'pilot';registration=register(profile_spec('pilot'),pilot)
            with self.assertRaises(CampaignError):register(profile_spec('validation'),base/'missing')
            with self.assertRaises(CampaignError):register(profile_spec('validation'),base/'unrun',pilot=pilot)
            for key,bad in [('stop_reason','spend_budget'),('stop_reason','call_budget'),('cleanup_status','failed')]:
                report=eligible_pilot_report();report['trials'][0][key]=bad
                with patch('parallax_relay.campaign_analysis.analyze',return_value=report):
                    with self.subTest(key=key,value=bad),self.assertRaises(CampaignError):
                        register(profile_spec('validation'),base/('rejected-'+bad),pilot=pilot)
            with patch('parallax_relay.campaign_analysis.analyze',return_value=eligible_pilot_report()):
                value=register(profile_spec('validation'),base/'validation',pilot=pilot)
            self.assertEqual(value['pilot']['registration_sha256'],registration['sha256'])
            self.assertEqual(value['pilot']['changed_frozen_sections'],[])
            self.assertFalse(value['pilot']['match_settings_changed'])
            self.assertEqual(read_registration(base/'validation'),value)
            self.assertEqual(len(value['schedule']),120)
            a=CampaignSpec.model_validate(registration['spec']);b=CampaignSpec.model_validate(value['spec'])
            validate_pilot_transition(a,b,registration['frozen'],value['frozen'])
            for section in ('source','environment','inputs','catalog','analysis'):
                changed=copy.deepcopy(value['frozen']);changed[section]={}
                with self.subTest(section=section),self.assertRaises(CampaignError):
                    validate_pilot_transition(a,b,registration['frozen'],changed)

    def test_reports_are_explicitly_exploratory_without_any_confidence_intervals(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            report=analyze(root)
            self.assertEqual(report['analysis_version'],3)
            self.assertEqual(report['profile_id'],'exploratory-under20-v1')
            self.assertEqual(report['evidence_class'],'exploratory')
            self.assertEqual(report['analysis_method'],'descriptive_per_room')
            self.assertFalse(report['confirmatory_eligible'])
            self.assertEqual(report['contrasts'],[])
            self.assertEqual(report['counts']['planned'],60)
            self.assertEqual(report['counts']['launched'],0)
            self.assertEqual(len(report['descriptive_contrasts']),12)
            self.assertTrue(all(c['observed_difference'] is None for c in report['descriptive_contrasts']))
            self.assertTrue(all(c['all_planned_bounds']==[-1,1] for c in report['descriptive_contrasts']))
            self.assertNotIn('wilson_95',json.dumps(report))
            with patch('parallax_relay.campaign_analysis.paired_bootstrap',side_effect=AssertionError('no inference')):
                write_report(analyze(root),Path(temp)/'report')
            self.assertEqual(json.loads((Path(temp)/'report'/'report.json').read_text())['profile_id'],report['profile_id'])

    def test_interrupted_arm_has_null_observed_rate_and_difference_with_missingness_bounds(self):
        from parallax_relay.campaign import Ledger
        from parallax_relay.campaign_models import trial_exposure
        from parallax_relay.campaign_analysis import success_summary
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';reg=register(profile_spec('pilot'),root)
            spec=CampaignSpec.model_validate(reg['spec'])
            model=next(t for t in reg['schedule'] if t['team']=='models')
            block=[t for t in reg['schedule'] if t['block_id']==model['block_id']]
            first,last=[t for t in block if t['condition'] in ('full','disabled')]
            ledger=Ledger(root)
            ledger.emit('campaign_started',registration_sha256=reg['sha256'],registration_matches=True)
            ledger.emit('block_reserved',block_id=model['block_id'],reserved_calls=sum(trial_exposure(spec,t)[0] for t in block),reserved_estimated_usd=1.25)
            ledger.emit('trial_launched',trial_id=first['trial_id'],block_id=first['block_id'])
            calls,dollars=trial_exposure(spec,first)
            ledger.emit('trial_finished',trial_id=first['trial_id'],stage='setup',stop_reason='setup_failure',result=None,cleanup_status='ok',elapsed_seconds=0,run_id=None,execution_stop_reason=None,recording_stop_reason=None,cancelled=False,accounted_calls=0,accounted_estimated_usd=0,released_calls=calls,released_estimated_usd=dollars)
            ledger.emit('trial_launched',trial_id=last['trial_id'],block_id=last['block_id'])
            report=analyze(root)
            contrast=next(c for c in report['descriptive_contrasts'] if c['team']=='models' and c['room']==model['room'])
            self.assertEqual(contrast[last['condition']]['operational_success']['unknown'],1)
            self.assertIsNone(contrast[last['condition']]['operational_success']['rate'])
            self.assertIsNone(contrast['observed_difference'])
            self.assertNotEqual(contrast['all_planned_bounds'][0],contrast['all_planned_bounds'][1])
            self.assertIsNone(report['overall']['operational_success']['rate'])
            # Preserve the historical protocol-1/2 lower-bound rate convention.
            self.assertEqual(success_summary(0,1,1,1)['rate'],0)

    async def test_low_disk_preflight_precedes_credentials_clients_and_attempt_markers(self):
        class ForbiddenEnvironment(dict):
            def keys(self):raise AssertionError('credentials read before disk preflight')
            def __iter__(self):raise AssertionError('credentials read before disk preflight')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            before={p.name for p in root.iterdir()}
            with patch('parallax_relay.campaign.shutil.disk_usage',return_value=type('Disk',(),{'free':5*1024**3-1})()),patch('parallax_relay.campaign.HTTPAgent',side_effect=AssertionError('client constructed')):
                with self.assertRaisesRegex(CampaignError,'5 GiB'):
                    await run_campaign(root,live=True,environ=ForbiddenEnvironment(OPENAI_API_KEY='FAKE',GEMINI_API_KEY='FAKE'))
            self.assertEqual({p.name for p in root.iterdir()},before)

    def test_cli_low_disk_preflight_precedes_environment_copy_and_env_file(self):
        from parallax_relay.campaign import main
        class ForbiddenEnvironment(dict):
            def keys(self):raise AssertionError('environment copied before disk preflight')
            def __iter__(self):raise AssertionError('environment copied before disk preflight')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            before={p.name for p in root.iterdir()}
            with patch('parallax_relay.campaign.shutil.disk_usage',return_value=type('Disk',(),{'free':5*1024**3-1})()),patch('parallax_relay.campaign.load_env_file',side_effect=AssertionError('credential file read')),patch('parallax_relay.campaign.os.environ',ForbiddenEnvironment(OPENAI_API_KEY='FAKE',GEMINI_API_KEY='FAKE')),patch('sys.stderr') as errors:
                self.assertEqual(main(['run','--campaign',str(root),'--live','--env-file',str(Path(temp)/'credentials')]),2)
            self.assertIn('5 GiB',''.join(call.args[0] for call in errors.write.call_args_list))
            self.assertEqual({p.name for p in root.iterdir()},before)

    async def test_low_disk_between_trials_stops_launches_and_releases_the_entire_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            disks=[type('Disk',(),{'free':5*1024**3})(),type('Disk',(),{'free':2*1024**3-1})()]
            with patch('parallax_relay.campaign.shutil.disk_usage',side_effect=disks),patch('parallax_relay.campaign.HTTPAgent',side_effect=AssertionError('client constructed')):
                await run_campaign(root,live=True,environ={'OPENAI_API_KEY':'FAKE','GEMINI_API_KEY':'FAKE'})
            report=analyze(root)
            self.assertEqual(report['campaign_stop']['reason'],'low_disk_space')
            self.assertEqual(report['completion_status'],'incomplete')
            self.assertFalse(report['cohort_eligible'])
            self.assertEqual(report['counts']['launched'],0)
            self.assertEqual(report['anomalies'],[])
            self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)
            self.assertEqual(report['campaign_accounting']['reservation_balance_estimated_usd'],0)
            self.assertTrue(all(t['unlaunched_reason']=='low_disk_space' for t in report['trials']))

    async def test_preflight_checks_existing_trial_destination_storage_before_clients(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            (root/'trials').mkdir()
            def disk(path):return type('Disk',(),{'free':(5*1024**3-1 if path==root/'trials' else 10*1024**3)})()
            with patch('parallax_relay.campaign.shutil.disk_usage',side_effect=disk),patch('parallax_relay.campaign.HTTPAgent',side_effect=AssertionError('client constructed')):
                with self.assertRaisesRegex(CampaignError,'5 GiB'):
                    await run_campaign(root,live=True,environ={'OPENAI_API_KEY':'FAKE','GEMINI_API_KEY':'FAKE'})
            self.assertFalse((root/'started.json').exists())
            self.assertFalse((root/'ledger.jsonl').exists())
            self.assertEqual(list((root/'trials').iterdir()),[])

    async def test_between_trial_guard_checks_trial_destination_separately_from_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';register(profile_spec('pilot'),root)
            (root/'trials').mkdir()
            readings=iter([5*1024**3,2*1024**3-1])
            def disk(path):return type('Disk',(),{'free':next(readings) if path==root/'trials' else 10*1024**3})()
            with patch('parallax_relay.campaign.shutil.disk_usage',side_effect=disk),patch('parallax_relay.campaign.HTTPAgent',side_effect=AssertionError('client constructed')):
                await run_campaign(root,live=True,environ={'OPENAI_API_KEY':'FAKE','GEMINI_API_KEY':'FAKE'})
            report=analyze(root)
            self.assertEqual(report['campaign_stop']['reason'],'low_disk_space')
            self.assertEqual(report['counts']['launched'],0)
            self.assertEqual(report['anomalies'],[])
            self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)
            self.assertEqual(report['campaign_accounting']['reservation_balance_estimated_usd'],0)

    async def test_real_recording_and_priced_fake_driver_support_both_stages_without_network(self):
        from parallax_relay.policies import WaitAgent
        from parallax_relay.protocol import ModelReply, Usage
        from parallax_relay.room_execution import RoomExecutionPermit
        class FakeHTTP(WaitAgent):
            def __init__(self,provider,model,key,**kwargs):self.provider=provider
            async def respond(self,request):
                self.role=request.role
                reply=await super().respond(request)
                return ModelReply(reply.text,Usage(100,10))
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.HTTPAgent',FakeHTTP),patch('parallax_relay.campaign.asyncio.sleep',new_callable=AsyncMock),patch('parallax_relay.campaign_analysis.paired_bootstrap',side_effect=AssertionError('no inference')):
            base=Path(temp);pilot=base/'pilot'
            register(profile_spec('pilot'),pilot)
            await run_campaign(pilot,live=True,environ={'OPENAI_API_KEY':'FAKE','GEMINI_API_KEY':'FAKE'})
            p=analyze(pilot)
            self.assertEqual(p['completion_status'],'complete',p['anomalies'])
            self.assertTrue(p['cohort_eligible'])
            self.assertEqual(p['counts']['artifact_available'],60)
            validation=base/'validation'
            reg=register(profile_spec('validation'),validation,pilot=pilot)
            trial=next(t for t in reg['schedule'] if t['team']=='wait')
            permit=RoomExecutionPermit.from_registration(reg,trial)
            with self.assertRaisesRegex(ValueError,'held-out'):permit.validate('split_span')
            await run_campaign(validation,live=True,environ={'OPENAI_API_KEY':'FAKE','GEMINI_API_KEY':'FAKE'})
            v=analyze(validation)
            for report,planned,paid_limit in [(p,60,2592),(v,120,5184)]:
                self.assertEqual(report['completion_status'],'complete',report['anomalies'])
                self.assertTrue(report['cohort_eligible'])
                self.assertFalse(report['confirmatory_eligible'])
                self.assertEqual(report['counts']['launched'],planned)
                self.assertEqual(report['counts']['artifact_available'],planned)
                self.assertEqual(report['anomalies'],[])
                self.assertEqual(report['contrasts'],[])
                self.assertTrue(all(c['observed_difference'] is not None for c in report['descriptive_contrasts']))
                self.assertNotIn('wilson_95',json.dumps(report))
                paid_ids={t['trial_id'] for t in report['trials'] if t['team']=='models'}
                self.assertLessEqual(sum(a['trial_id'] in paid_ids for a in report['attempts']),paid_limit)
                self.assertEqual(report['overall']['cost']['retained_estimate_usd'],0)
                self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)
                self.assertEqual(report['campaign_accounting']['reservation_balance_estimated_usd'],0)
            self.assertEqual(len({t['room'] for t in p['trials']}),3)
            self.assertEqual(len({t['room'] for t in v['trials']}),6)

    def test_fixed_profile_retains_unknown_retry_estimates_and_rejects_whole_phase_before_calls(self):
        from decimal import Decimal
        from parallax_relay.budget import Budget, BudgetExceeded
        from parallax_relay.campaign_models import schedule, trial_settings
        from parallax_relay.config import Rates
        from parallax_relay.observations import observe
        from parallax_relay.protocol import AgentRequest
        from parallax_relay.state import initial_world
        spec=CampaignSpec.model_validate(profile_spec('pilot'))
        trial=next(t for t in schedule(spec) if t['team']=='models' and t['condition']=='full')
        settings=trial_settings(spec,trial)
        budget=Budget(settings,{r:Rates.model_validate(p['pricing']) for r,p in trial['players'].items()})
        world=initial_world(trial['room'])
        requests={r:AgentRequest(observe(world,r),'broadcast',max_output_tokens=4096) for r in trial['players']}
        while True:
            before=budget.summary()
            try:tickets=budget.reserve_phase(requests)
            except BudgetExceeded as error:
                self.assertEqual(error.reason,'spend_budget')
                self.assertEqual(budget.summary(),before)
                break
            for ticket in tickets.values():
                for _ in range(settings.max_attempts):
                    ticket.start();ticket.settle(None)
                ticket.release()
        self.assertGreater(budget.calls_started,0)
        self.assertLess(budget.calls_started,216)
        self.assertEqual(budget.known_usage_usd,0)
        self.assertEqual(budget.spent,budget.retained_estimate_usd)
        self.assertGreater(budget.spent,0)
        self.assertLessEqual(budget.spent,Decimal('0.25'))
        self.assertEqual(budget.reserved_usd,0)
        self.assertEqual(budget.reserved_calls,0)
        self.assertEqual(budget.unknown_usage_calls,budget.calls_started)


if __name__=='__main__':unittest.main()
