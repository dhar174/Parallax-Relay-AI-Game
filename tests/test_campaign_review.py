"""Antigravity #40 adversarial artifact, ownership and accounting probes."""
import asyncio
import copy
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_campaign import spec, live_spec
from parallax_relay.campaign import register, run_campaign, read_registration, Ledger, CampaignError
from parallax_relay.campaign_analysis import analyze, _valid_summary, write_report
from parallax_relay.provenance import canonical_hash


def rewrite_receipt(root,change):
    path=root/'ledger.jsonl';rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    for row in rows:
        if row['event']=='trial_finished':change(row)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')


class CampaignReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_receipt_cannot_borrow_a_saved_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(policies=['scripted'],conditions=['disabled'],match={'max_turns':7,'max_attempts':1}),root)
            await run_campaign(root,offline=True)
            self.assertTrue(analyze(root)['trials'][0]['operational_success'])
            rewrite_receipt(root,lambda row:row.update(result=None))
            row=analyze(root)['trials'][0]
            self.assertIn('ledger_artifact_disagreement',row['artifact_issues'])
            self.assertFalse(row['artifact_available']);self.assertIsNone(row['operational_success'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';await self.setup_run(root);rewrite_receipt(root,lambda row:row.update(result=None))
            self.assertFalse(analyze(root)['trials'][0]['operational_success'])

    async def test_block_reservation_ids_must_be_registered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';await self.setup_run(root)
            path=root/'ledger.jsonl';original=path.read_text(encoding='utf-8')
            for event in ('block_reserved','block_released'):
                rows=[json.loads(s) for s in original.splitlines()]
                next(row for row in rows if row['event']==event)['block_id']=str(uuid4())
                path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
                with self.subTest(event=event):self.assertIn('block_event_mismatch',analyze(root)['anomalies'])

    async def test_additional_cross_artifact_issue_codes_are_reported_independently(self):
        mutations=[('result_turn_limit_mismatch','result',lambda d:d.update(turns=2)),
                   ('lifecycle_stop_mismatch','result',lambda d:d.update(stop_reason='call_budget')),
                   ('last_checkpoint_mismatch','replay',lambda d:d[0]['state_after'].update(energy=99)),
                   ('duplicate_phase','phases',lambda d:d.append(copy.deepcopy(d[0]))),
                   ('resolved_phase_missing','phases',lambda d:d.clear()),
                   ('usage_shape_mismatch','calls',lambda d:d[0]['usage'].update(input_tokens='bad')),
                   ('settlement_basis_mismatch','calls',lambda d:d[0].update(settlement_basis='retained_estimate')),
                   ('attempt_settlement_mismatch','calls',lambda d:d[0].update(settled_amount_usd=1)),
                   ('duplicate_attempt','calls',lambda d:d.append(copy.deepcopy(d[0]))),
                   ('unpriced_settlement_mismatch','calls',lambda d:d[0].update(settled_amount_usd=1))]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';_,trial=await self.setup_run(root)
            backups={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for expected,name,change in mutations:
                for p,content in backups.items():p.write_bytes(content)
                path=trial/(name+('.json' if name=='result' else '.jsonl'))
                data=json.loads(path.read_text(encoding='utf-8')) if name=='result' else [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
                change(data);path.write_text(json.dumps(data) if name=='result' else ''.join(json.dumps(row)+'\n' for row in data),encoding='utf-8')
                if name=='result':rewrite_receipt(root,lambda row:row.update(result=data))
                with self.subTest(expected=expected):self.assertIn(expected,analyze(root)['trials'][0]['artifact_issues'])
            for p,content in backups.items():p.write_bytes(content)
            calls=[json.loads(s) for s in (trial/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
            calls[0]['usage']['input_tokens']='bad';calls[1]['settlement_basis']='retained_estimate'
            (trial/'calls.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in calls),encoding='utf-8')
            issues=analyze(root)['trials'][0]['artifact_issues']
            self.assertIn('usage_shape_mismatch',issues);self.assertIn('settlement_basis_mismatch',issues)
            for key,expected,value in (('run_id','run_id_mismatch',str(uuid4())),('recording_stop_reason','recording_stop_mismatch','call_budget'),('execution_stop_reason','execution_stop_mismatch','call_budget')):
                for p,content in backups.items():p.write_bytes(content)
                rewrite_receipt(root,lambda row:row.update({key:value}))
                with self.subTest(expected=expected):self.assertIn(expected,analyze(root)['trials'][0]['artifact_issues'])
            for kind,expected in (('stop','campaign_settlement_mismatch'),('balance','unbalanced_estimate_reservations')):
                for p,content in backups.items():p.write_bytes(content)
                rows=[json.loads(s) for s in (root/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
                event=rows[-1] if kind=='stop' else next(r for r in rows if r['event']=='block_reserved')
                key='accounted_estimated_usd' if kind=='stop' else 'reserved_estimated_usd'
                event[key]=1;event[key+'_decimal']='1'
                (root/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
                with self.subTest(expected=expected):self.assertIn(expected,analyze(root)['anomalies'])

    async def test_invalid_live_keys_and_cleanup_cancellation_are_explicit(self):
        from parallax_relay.campaign import main
        from parallax_relay.policies import WaitAgent
        from contextlib import redirect_stderr
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(live_spec(conditions=['disabled']),root)
            for key in ('   ','FAKE\nKEY'):
                with self.subTest(key=repr(key)),self.assertRaises(CampaignError):await run_campaign(root,live=True,environ={'TEST_KEY':key})
                self.assertFalse((root/'started.json').exists())
            error=io.StringIO()
            with patch.dict('os.environ',{'TEST_KEY':'   '}),redirect_stderr(error):
                self.assertEqual(await asyncio.to_thread(main,['run','--campaign',str(root),'--live']),2)
            self.assertIn('Missing selected live credentials',error.getvalue())
        class CancelClose(WaitAgent):
            async def close(self):raise asyncio.CancelledError()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(conditions=['disabled']),root)
            with patch('parallax_relay.campaign.make_policy',side_effect=lambda n,r,t:CancelClose(r)):
                await run_campaign(root,offline=True)
            row=analyze(root)['trials'][0]
            self.assertEqual(row['cleanup_status'],'failed');self.assertEqual(row['stop_reason'],'local_error')


    async def test_priced_campaign_cannot_be_rewritten_as_unpriced(self):
        from parallax_relay.policies import WaitAgent
        from parallax_relay.campaign_validation import BUDGET_MONEY
        class ZeroHTTP:
            async def respond(self,request):return await WaitAgent(request.observation.role).respond(request)
            async def close(self):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';registration=register(live_spec(conditions=['disabled']),root)
            with patch('parallax_relay.campaign.HTTPAgent',side_effect=lambda *a,**k:ZeroHTTP()):
                await run_campaign(root,live=True,environ={'TEST_KEY':'FAKE'})
            self.assertEqual(analyze(root)['overall']['cost']['known_estimated_usd'],0)
            trial=root/'trials'/registration['schedule'][0]['trial_id']
            path=trial/'calls.jsonl';original=path.read_text(encoding='utf-8');calls=[json.loads(s) for s in original.splitlines()]
            calls[0].update(settled_amount_usd=1,settled_amount_usd_decimal='1')
            path.write_text(''.join(json.dumps(row)+'\n' for row in calls),encoding='utf-8')
            self.assertIn('cost_component_mismatch',analyze(root)['trials'][0]['artifact_issues'])
            calls=[json.loads(s) for s in original.splitlines()]
            calls[0]['reservation_quote_usd']=None;calls[0].pop('reservation_quote_usd_decimal',None)
            path.write_text(''.join(json.dumps(row)+'\n' for row in calls),encoding='utf-8')
            self.assertIn('missing_priced_quote',analyze(root)['trials'][0]['artifact_issues'])
            path.write_text(original,encoding='utf-8')
            result=json.loads((trial/'result.json').read_text(encoding='utf-8'))
            for key in BUDGET_MONEY:result['budget'][key]=None;result['budget'].pop(key+'_decimal',None)
            (trial/'result.json').write_text(json.dumps(result),encoding='utf-8')
            rewrite_receipt(root,lambda row:row.update(result=result) if row['trial_id']==registration['schedule'][0]['trial_id'] else None)
            calls=[json.loads(s) for s in (trial/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
            for call in calls:
                for key in ('reservation_quote_usd','settled_amount_usd'):call[key]=None;call.pop(key+'_decimal',None)
            (trial/'calls.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in calls),encoding='utf-8')
            self.assertIn('pricing_team_mismatch',analyze(root)['trials'][0]['artifact_issues'])
    async def setup_run(self,root):
        data=register(spec(conditions=['disabled']),root)
        await run_campaign(root,offline=True)
        return data,root/'trials'/data['schedule'][0]['trial_id']

    async def test_budget_extras_cannot_rewrite_outcome_or_assignment(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';registration,trial=await self.setup_run(root)
            result=json.loads((trial/'result.json').read_text(encoding='utf-8'))
            result['budget'].update(operational_success=True,assignment_id='hijacked')
            (trial/'result.json').write_text(json.dumps(result),encoding='utf-8')
            rewrite_receipt(root,lambda row:row.update(result=result))
            row=analyze(root)['trials'][0]
            self.assertFalse(row['operational_success'])
            self.assertEqual(row['assignment_id'],registration['schedule'][0]['assignment_id'])
            for key in ('input_usage_calls','output_usage_calls','reported_cached_input_tokens',
                        'reported_reasoning_output_tokens','calls_reserved_total','calls_released','reserved_calls'):
                bad=copy.deepcopy(result);bad['budget'][key]='SECRET_SENTINEL'
                self.assertFalse(_valid_summary(bad),key)
            bad=copy.deepcopy(result);bad['energy']='SECRET_SENTINEL'
            self.assertFalse(_valid_summary(bad))
            bad=copy.deepcopy(result);bad['budget'].pop('estimated_cost_usd')
            self.assertFalse(_valid_summary(bad))

    async def test_unvalidated_ledger_strings_never_reach_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';await self.setup_run(root)
            rewrite_receipt(root,lambda row:row.update(execution_stop_reason='=1+1',run_id='not-a-uuid'))
            report=analyze(root)
            self.assertTrue(report['anomalies'])
            self.assertNotIn('=1+1',json.dumps(report))

    async def test_wrong_policy_and_running_lifecycle_are_not_complete_artifacts(self):
        from parallax_relay.policies import policy_identity
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';registration,trial=await self.setup_run(root)
            manifest=json.loads((trial/'manifest.json').read_text(encoding='utf-8'))
            p=manifest['provenance'];p['execution']['value']['policy']=policy_identity('scripted',None,1)
            p['execution']['sha256']=canonical_hash(p['execution']['value'])
            p['lifecycle'].update(stage='running',ended_at=None,elapsed_seconds=None,execution_stop_reason=None,stop_reason=None)
            (trial/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            self.assertFalse(analyze(root)['trials'][0]['artifact_available'])

    async def test_marker_is_rechecked_after_lock_acquisition(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(),root)
            original=Path.mkdir
            def acquire(path,*args,**kwargs):
                if path==root/'.runner.lock':(root/'started.json').write_text('{}',encoding='utf-8')
                return original(path,*args,**kwargs)
            with patch.object(Path,'mkdir',acquire),patch('parallax_relay.campaign.execute_trial') as execute:
                with self.assertRaises(CampaignError):await run_campaign(root,offline=True)
                execute.assert_not_called()
            self.assertFalse((root/'.runner.lock').exists())

    async def test_cancellation_stays_primary_when_cleanup_fails(self):
        from parallax_relay.policies import WaitAgent
        entered=asyncio.Event()
        class Slow(WaitAgent):
            async def respond(self,request):entered.set();await asyncio.Event().wait()
            async def close(self):raise OSError('SECRET_SENTINEL')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(),root)
            with patch('parallax_relay.campaign.make_policy',side_effect=lambda n,r,t:Slow(r)):
                task=asyncio.create_task(run_campaign(root,offline=True));await entered.wait();task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            report=analyze(root)
            self.assertEqual(report['counts']['cancelled'],1)
            self.assertEqual(report['trials'][0]['cleanup_status'],'failed')

    async def test_missing_live_keys_leave_registration_reusable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(live_spec(),root)
            with patch('parallax_relay.campaign.HTTPAgent') as agent:
                with self.assertRaises(ValueError):await run_campaign(root,live=True,environ={})
                agent.assert_not_called()
            self.assertFalse((root/'started.json').exists())
            self.assertFalse((root/'ledger.jsonl').exists())

    async def test_trimmed_credentials_and_existing_lock_are_checked_before_launch(self):
        from parallax_relay.policies import WaitAgent
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(live_spec(conditions=['disabled']),root)
            lock=root/'.runner.lock';lock.write_text('other worker',encoding='utf-8')
            with self.assertRaises(FileExistsError):await run_campaign(root,live=True,environ={'TEST_KEY':'  FAKE  '})
            self.assertEqual(lock.read_text(encoding='utf-8'),'other worker');self.assertFalse((root/'started.json').exists())
            lock.unlink();keys=[]
            def agent(provider,model,key,**kwargs):keys.append(key);return WaitAgent('SPECTRA')
            with patch('parallax_relay.campaign.HTTPAgent',side_effect=agent):
                await run_campaign(root,live=True,environ={'TEST_KEY':'  FAKE  '})
            self.assertTrue(keys);self.assertEqual(set(keys),{'FAKE'})

    async def test_cross_artifact_mismatches_and_incomplete_ledgers_cannot_qualify(self):
        mutations=[('world_energy_mismatch','final_state',lambda d:d.update(energy=d['energy']+1)),
                   ('phase_turn_range_mismatch','phases',lambda d:d[0].update(turn=-1)),
                   ('replay_turn_sequence_mismatch','replay',lambda d:d[0].update(turn=99)),
                   ('usage_totals_mismatch','result',lambda d:d['budget'].update(reported_input_tokens=1)),
                   ('final_state_inconsistent','final_state',lambda d:d.update(win=True)),
                   ('world_turn_mismatch','final_state',lambda d:d.update(turn=2)),
                   ('call_count_mismatch','calls',lambda d:d.pop()),
                   ('resolved_turn_count_mismatch','replay',lambda d:d.clear()),
                   ('cost_settlement_mismatch','result',lambda d:d['budget'].update(estimated_cost_usd=1,known_usage_estimated_usd=1,retained_estimate_usd=0))]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';_,trial=await self.setup_run(root)
            backups={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for expected,name,change in mutations:
                for p,content in backups.items():p.write_bytes(content)
                suffix='.jsonl' if name in ('calls','phases','replay') else '.json';path=trial/(name+suffix)
                data=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if suffix=='.jsonl' else json.loads(path.read_text(encoding='utf-8'))
                change(data)
                path.write_text(''.join(json.dumps(r)+'\n' for r in data) if suffix=='.jsonl' else json.dumps(data),encoding='utf-8')
                if name=='result':rewrite_receipt(root,lambda row:row.update(result=data))
                with self.subTest(expected=expected):self.assertIn(expected,analyze(root)['trials'][0]['artifact_issues'])
            for expected in ('ledger_artifact_disagreement','provenance_drift','input_drift'):
                for p,content in backups.items():p.write_bytes(content)
                if expected=='ledger_artifact_disagreement':
                    rewrite_receipt(root,lambda row:row['result'].update(energy=row['result']['energy']+1))
                else:
                    path=trial/'manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
                    provenance=manifest['provenance']
                    if expected=='provenance_drift':provenance['source']={'status':'clean','revision':'a'*40,'reason':None}
                    else:
                        prompt=provenance['inputs']['prompt'];prompt['value']='different prefix\n'+prompt['value'];prompt['sha256']=canonical_hash(prompt['value'])
                    path.write_text(json.dumps(manifest),encoding='utf-8')
                with self.subTest(expected=expected):self.assertIn(expected,analyze(root)['trials'][0]['artifact_issues'])
            for variant in ('duplicate_start','duplicate_stop','wrong_block','missing_receipt','nan','deep'):
                for p,content in backups.items():p.write_bytes(content)
                rows=[json.loads(s) for s in (root/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
                if variant=='duplicate_start':rows.insert(1,copy.deepcopy(rows[0]))
                elif variant=='duplicate_stop':rows.append(copy.deepcopy(rows[-1]))
                elif variant=='wrong_block':next(r for r in rows if r['event']=='trial_launched')['block_id']=str(uuid4())
                elif variant=='missing_receipt':rows=[r for r in rows if r['event']!='trial_finished']
                extra=''
                if variant=='nan':extra='{"broken":NaN}\n'
                if variant=='deep':extra='['*2000+'0'+']'*2000+'\n'
                for n,row in enumerate(rows,1):row['sequence']=n
                (root/'ledger.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows)+extra,encoding='utf-8')
                report=analyze(root)
                with self.subTest(variant=variant):
                    self.assertFalse(report['cohort_eligible'])
                    self.assertEqual(report['completion_status'],'incomplete')

    async def test_failed_initialization_removes_owned_lock_and_broken_markers_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(),root)
            lock=root/'.runner.lock'
            lock.mkdir();(lock/'owner').write_text('other worker',encoding='utf-8')
            with self.assertRaises(FileExistsError):await run_campaign(root,offline=True)
            self.assertEqual((lock/'owner').read_text(encoding='utf-8'),'other worker')
            (lock/'owner').unlink();lock.rmdir()
            for is_directory in (False,True):
                try:lock.symlink_to(root/'missing',target_is_directory=is_directory)
                except OSError:lock.write_text('other worker',encoding='utf-8')
                with self.subTest(is_directory=is_directory),self.assertRaises(FileExistsError):await run_campaign(root,offline=True)
                self.assertTrue(lock.is_symlink() or lock.exists());lock.unlink()
            with patch('parallax_relay.campaign.atomic_json',side_effect=OSError('SECRET_SENTINEL')),self.assertRaises(OSError):
                await run_campaign(root,offline=True)
            self.assertFalse((root/'.runner.lock').exists())
            for name in ('started.json','ledger.jsonl'):
                marker=root/name
                try:marker.symlink_to(root/'absent')
                except OSError:marker.write_text('{}',encoding='utf-8')
                with self.assertRaises(CampaignError):await run_campaign(root,offline=True)
                self.assertFalse((root/'.runner.lock').exists());marker.unlink()

    async def test_cancel_before_phase_task_entry_releases_reservations(self):
        from parallax_relay.orchestrator import _phase
        from parallax_relay.budget import Budget
        from parallax_relay.config import MatchSettings,Rates
        from parallax_relay.protocol import AgentRequest,Observation,ROLES
        settings=MatchSettings();budget=Budget(settings,{r:Rates(input_per_million=1,output_per_million=1) for r in ROLES})
        original=asyncio.create_task
        def cancelled(coro):task=original(coro);task.cancel();return task
        requests={r:AgentRequest(Observation(r,0,'{}',b''),'commit') for r in ROLES}
        with patch('parallax_relay.orchestrator.asyncio.create_task',cancelled):
            with self.assertRaises(asyncio.CancelledError):await _phase({r:None for r in ROLES},requests,budget,settings,[],None)
        self.assertEqual(budget.reserved_calls,0);self.assertEqual(budget.reserved_usd,0);self.assertEqual(budget.calls_started,0)

    async def test_partial_block_budget_and_unknown_execution_accounting(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign'
            register(spec(policies=['uniform'],repetitions=2,campaign_max_calls=36),root)
            await run_campaign(root,offline=True)
            report=analyze(root)
            self.assertEqual((report['counts']['planned'],report['counts']['launched']),(10,5))
            self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(spec(conditions=['disabled']),root)
            with patch('parallax_relay.campaign.run_match',side_effect=RuntimeError('SECRET_SENTINEL')):
                await run_campaign(root,offline=True)
            report=analyze(root)
            self.assertEqual(report['counts']['unknown_engine'],1)
            self.assertEqual(report['campaign_accounting']['calls_accounted'],3)
            self.assertNotIn('SECRET_SENTINEL',json.dumps(report))

    async def test_sub_ulp_trial_costs_reconcile_through_campaign_and_analysis(self):
        from parallax_relay.budget import Budget
        from parallax_relay.campaign_models import trial_settings
        from parallax_relay.config import Rates
        from parallax_relay.orchestrator import MatchResult
        from parallax_relay.state import initial_world
        from parallax_relay.protocol import ROLES
        cost=Decimal('1e-17')
        async def execute(root,registration,configuration,trial,environ):
            budget=Budget(trial_settings(configuration,trial),{r:Rates(input_per_million=1,output_per_million=1) for r in ROLES})
            budget.calls_started=budget.calls_reserved_total=1
            budget.spent=budget.known_usage_usd=cost
            result=MatchResult(initial_world(),'turn_limit',[],[],budget.summary()).summary()
            return {'trial_id':trial['trial_id'],'stage':'execution','stop_reason':'turn_limit','result':result,
                    'cleanup_status':'ok','elapsed_seconds':0,'run_id':None,'execution_stop_reason':'turn_limit',
                    'recording_stop_reason':'turn_limit','cancelled':False}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(live_spec(conditions=['disabled']),root)
            with patch('parallax_relay.campaign.execute_trial',side_effect=execute):
                await run_campaign(root,live=True,environ={'TEST_KEY':'FAKE'})
            report=analyze(root);accounting=report['campaign_accounting']
            self.assertEqual(accounting['reservation_balance_estimated_usd'],0)
            self.assertEqual(Decimal(accounting['reservation_balance_estimated_usd_decimal']),0)
            self.assertEqual(report['overall']['cost']['known_estimated_usd_decimal'],'3E-17')
            self.assertNotIn('unbalanced_estimate_reservations',report['anomalies'])
        cost=Decimal('0.03333333333333333334')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';register(live_spec(conditions=['disabled']),root)
            with patch('parallax_relay.campaign.execute_trial',side_effect=execute):await run_campaign(root,live=True,environ={'TEST_KEY':'FAKE'})
            path=root/'ledger.jsonl';events=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
            events[-1].pop('accounted_estimated_usd_decimal')
            path.write_text(''.join(json.dumps(row)+'\n' for row in events),encoding='utf-8')
            report=analyze(root)
            self.assertNotIn('campaign_settlement_mismatch',report['anomalies'])
            self.assertGreater(report['campaign_accounting']['legacy_settlement_rounding_uncertainty_usd'],0)

    async def test_frozen_drift_stops_before_trial_setup(self):
        import parallax_relay.campaign as campaign
        clean={'status':'clean','revision':'a'*40,'reason':None}
        with tempfile.TemporaryDirectory() as temp,patch.object(campaign,'collect_source',return_value=clean):
            root=Path(temp)/'campaign';data=register(spec(stage='pilot',policies=['scripted','wait','uniform']),root)
            altered=copy.deepcopy(data['frozen']);altered['source']['revision']='b'*40
            with patch.object(campaign,'frozen_inputs',side_effect=[data['frozen'],altered]),patch.object(campaign,'execute_trial') as execute:
                await run_campaign(root,offline=True);execute.assert_not_called()
            self.assertEqual(analyze(root)['campaign_stop']['reason'],'frozen_input_drift')


class ReportReviewTests(unittest.TestCase):
    def test_atomic_json_failure_preserves_target_and_removes_temporary(self):
        from parallax_relay.campaign import atomic_json
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'record.json';target.write_text('{"original":true}',encoding='utf-8')
            with patch('parallax_relay.campaign.os.fsync',side_effect=OSError('disk failure')),self.assertRaises(OSError):atomic_json(target,{'new':True})
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'original':True})
            self.assertFalse(target.with_suffix('.json.tmp').exists())
    def test_mixed_cost_nullability_and_negative_zero(self):
        from parallax_relay.orchestrator import MatchResult
        from parallax_relay.budget import Budget
        from parallax_relay.config import MatchSettings
        from parallax_relay.state import initial_world
        from parallax_relay.money import json_fields,amount
        result=MatchResult(initial_world(),'turn_limit',[],[],Budget(MatchSettings(),{}).summary()).summary()
        for key in ('estimated_cost_usd','known_usage_estimated_usd','retained_estimate_usd'):
            bad=copy.deepcopy(result);bad['budget'][key]=0
            with self.subTest(key=key):self.assertFalse(_valid_summary(bad))
        self.assertEqual(amount(json_fields({'cost':Decimal('-0')}),'cost'),Decimal(0))

    def test_csv_quotes_carriage_returns_and_neutralizes_all_whitespace_prefixes(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'report';values=['\rvalue','\v=1+1','\f+1','\u00a0@SUM(1)']
            rows=[{'value':value,'nested':{'formula':'=1+1'},'list':['=1+1']} for value in values]
            write_report({'trials':rows,'cells':[],'attempts':[]},out)
            text=(out/'trials.csv').read_bytes().decode('utf-8')
            self.assertTrue(text.startswith('"value","nested","list"\n'))
            # Always quote cells, including CR, rather than relying on the
            # QUOTE_MINIMAL behavior that changed after CPython 3.11.2.
            self.assertIn('"\'\rvalue"',text)
            with (out/'trials.csv').open(encoding='utf-8',newline='') as handle:exported=list(csv.DictReader(handle))
            self.assertEqual(len(exported),len(rows));self.assertTrue(all(row['value'].startswith("'") for row in exported))
            self.assertEqual(json.loads(exported[0]['nested']),{'formula':'=1+1'})
            self.assertEqual(json.loads(exported[0]['list']),['=1+1'])

    def test_success_counts_reject_boolean_denominators(self):
        from parallax_relay.campaign_analysis import success_summary
        for args in ((0,0,True,0),(0,1,1,False)):
            with self.assertRaises(ValueError):success_summary(*args)

    def test_cli_exit_codes_and_actionable_safe_messages(self):
        from contextlib import redirect_stdout, redirect_stderr
        from parallax_relay.campaign import main
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'spec.json';source.write_text(json.dumps(spec(conditions=['disabled'])),encoding='utf-8')
            root=base/'campaign';stdout,stderr=io.StringIO(),io.StringIO()
            with redirect_stdout(stdout),redirect_stderr(stderr):
                self.assertEqual(main(['register','--spec',str(source),'--out',str(root)]),0)
                self.assertEqual(main(['run','--campaign',str(root),'--offline']),0)
                self.assertEqual(main(['analyze','--campaign',str(root),'--out',str(base/'report')]),0)
                self.assertEqual(main(['run','--campaign',str(root),'--offline']),2)
                self.assertIn('already attempted',stderr.getvalue())
                self.assertEqual(main(['run','--campaign',str(root),'--offline','--env-file','unused']),2)
                self.assertIn('Offline campaigns do not read credential files',stderr.getvalue())
                partial=base/'partial';register(spec(campaign_max_calls=1),partial)
                self.assertEqual(main(['run','--campaign',str(partial),'--offline']),4)
                def interrupted(coro):coro.close();raise KeyboardInterrupt()
                with patch('parallax_relay.campaign.asyncio.run',side_effect=interrupted):
                    self.assertEqual(main(['run','--campaign',str(root),'--offline']),130)
                self.assertIn('Interrupted; analyze',stderr.getvalue())
            # Exercise python -m too: its CampaignError class must match the
            # analysis module's, so safe messages survive the entry point.
            import subprocess,sys
            process=subprocess.run([sys.executable,'-m','parallax_relay.campaign','analyze','--campaign',str(base/'missing'),'--out',str(base/'unused')],capture_output=True,text=True)
            self.assertEqual(process.returncode,2);self.assertIn('Missing or invalid campaign JSON',process.stderr)

    def test_registration_validation_rerun_linkage_and_reordered_pilot_roster(self):
        from parallax_relay.campaign_models import CampaignSpec,assignments
        example=json.loads((Path(__file__).resolve().parents[1]/'configs/campaign_offline.json').read_text(encoding='utf-8'))
        CampaignSpec.model_validate(example)
        for override in ({'campaign_max_estimated_cost_usd':True},{'min_trial_interval_seconds':False},
                         {'repetitions':2},{'match':{'communication_rounds':1}}):
            with self.subTest(override=override),self.assertRaises(ValueError):CampaignSpec.model_validate(spec(**override))
        clean={'status':'clean','revision':'a'*40,'reason':None}
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=clean):
            base=Path(temp);original=str(uuid4());root=base/'rerun'
            registration=register(spec(conditions=['disabled'],rerun_of=original,rerun_reason='manual_recheck'),root)
            trial=read_registration(root)['schedule'][0]
            self.assertNotEqual(trial['trial_id'],original);self.assertEqual(trial['rerun_of'],original)
            self.assertEqual(trial['rerun_reason'],'manual_recheck')
            with self.assertRaises(CampaignError):register(spec(),base/'wrong-stage',pilot=root)
            pilot_spec=live_spec(stage='pilot',policies=['scripted','wait','uniform'])
            pilot=base/'pilot';p=register(pilot_spec,pilot)
            confirmation=live_spec(stage='confirmatory',policies=['scripted','wait','uniform'])
            confirmation['roster']=list(reversed(confirmation['roster']))
            with patch('parallax_relay.campaign_analysis.analyze',return_value={'cohort_eligible':True}):
                c=register(confirmation,base/'confirmation',pilot=pilot)
                self.assertEqual(assignments(CampaignSpec.model_validate(p['spec'])),assignments(CampaignSpec.model_validate(c['spec'])))
                altered=copy.deepcopy(confirmation);altered['roster'][0]['model']='changed-model'
                with self.assertRaises(CampaignError):register(altered,base/'changed',pilot=pilot)
            for key,value in (('registration_sha256','bad'),('match_settings_changed',1),('changed_frozen_sections','source'),('changed_frozen_sections',['unknown'])):
                invalid=copy.deepcopy(c);invalid['pilot'][key]=value
                invalid['sha256']=canonical_hash({k:v for k,v in invalid.items() if k!='sha256'})
                (base/'confirmation'/'registration.json').write_text(json.dumps(invalid),encoding='utf-8')
                with self.subTest(key=key,value=value),self.assertRaises(CampaignError):read_registration(base/'confirmation')

    def test_monetary_annotations_reject_unbounded_exponents(self):
        from parallax_relay.money import amount
        for exact in ('1e-999999999999','1e999999999999999999999999999999'):
            with self.assertRaises(ValueError):amount({'cost':0,'cost_decimal':exact},'cost')

    def test_summary_terminal_relations_allow_local_error_after_engine_victory(self):
        from parallax_relay.orchestrator import MatchResult
        from parallax_relay.budget import Budget
        from parallax_relay.config import MatchSettings
        from parallax_relay.state import initial_world
        world=initial_world();world.win=True
        result=MatchResult(world,'local_error',[],[],Budget(MatchSettings(),{}).summary()).summary()
        self.assertTrue(_valid_summary(result))
        result['stop_reason']='turn_limit';self.assertFalse(_valid_summary(result))
        result['win']=False;result['completed']=False;result['scores']=None;result['stop_reason']='victory'
        self.assertFalse(_valid_summary(result))

    def test_registration_missing_frozen_sections_and_noncanonical_ids_fail_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign';original=register(spec(),root)
            for kind in ('source','analysis','experiment_id'):
                data=copy.deepcopy(original)
                if kind=='experiment_id':data['experiment_id']=data['experiment_id'].upper()
                else:data['frozen'].pop(kind)
                data['sha256']=canonical_hash({k:v for k,v in data.items() if k!='sha256'})
                (root/'registration.json').write_text(json.dumps(data),encoding='utf-8')
                with self.subTest(kind=kind),self.assertRaises(CampaignError):read_registration(root)

    def test_statistics_boundaries_and_non_degenerate_bootstrap(self):
        from parallax_relay.campaign_analysis import wilson,percentile,paired_bootstrap
        self.assertEqual(wilson(0,30)[0],0);self.assertEqual(wilson(30,30)[1],1)
        for s,n in ((True,30),(1.0,30),(-1,30),(31,30),(1,0)):
            with self.assertRaises(ValueError):wilson(s,n)
        for p in (-.1,1.1,float('nan'),True):
            with self.assertRaises(ValueError):percentile([0,1],p)
        # Unequal variances and equal assignment weights. Enumerating all 4^4
        # outcomes independently gives support for the seeded interval below.
        result=paired_bootstrap({'a':[(1,0),(0,1),(1,1),(0,0)],'b':[(1,0)]*4})
        self.assertEqual(result['difference_percentage_points'],50)
        self.assertFalse(result['degenerate_interval'])
        self.assertEqual(result['interval_95_percentage_points'],[12.5,87.5])

    def test_csv_failure_is_atomic_and_empty_tables_have_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'report'
            def fail(writer,rows):writer.writerow(next(iter(rows)));raise OSError('SECRET_SENTINEL')
            with patch.object(csv.DictWriter,'writerows',fail),self.assertRaises(OSError):
                write_report({'trials':[{'value':'safe'}],'cells':[],'attempts':[]},out)
            self.assertFalse((out/'trials.csv').exists());self.assertFalse(list(out.glob('*.tmp')))
            fresh=Path(temp)/'empty';write_report({'trials':[],'cells':[],'attempts':[]},fresh)
            with (fresh/'attempts.csv').open(encoding='utf-8',newline='') as handle:
                self.assertEqual(next(csv.reader(handle)),['trial_id','role','turn','phase','attempt','status'])
    def test_csv_neutralizes_formulas_and_preserves_numeric_zero(self):
        strings=['=1+1','+1','-2','@SUM(1)','\tanything','\rvalue',' =1+1']
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'report';report={'trials':[{'value':s,'number':0} for s in strings],'cells':[],'attempts':[]}
            write_report(report,out)
            with (out/'trials.csv').open(encoding='utf-8',newline='') as handle:rows=list(csv.DictReader(handle))
            self.assertTrue(all(row['value'].startswith("'") for row in rows))
            self.assertTrue(all(row['number']=='0' for row in rows))
            self.assertEqual(json.loads((out/'report.json').read_text(encoding='utf-8')),report)

    def test_ledger_decimal_amounts_preserve_sub_ulp_settlements(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ledger=Ledger(root)
            ledger.emit('block_reserved',reserved_estimated_usd=Decimal(1),reserved_calls=1)
            ledger.emit('trial_finished',accounted_estimated_usd=Decimal('1e-17'),
                        released_estimated_usd=Decimal(1)-Decimal('1e-17'))
            rows=[json.loads(s) for s in (root/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(Decimal(rows[0]['reserved_estimated_usd_decimal'])-
                             Decimal(rows[1]['accounted_estimated_usd_decimal'])-
                             Decimal(rows[1]['released_estimated_usd_decimal']),0)
