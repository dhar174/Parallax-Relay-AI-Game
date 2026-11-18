"""Native-vs-ledger reconciliation and completed-match qualification regressions."""
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from parallax_relay.campaign import register, run_campaign, atomic_json
from parallax_relay.campaign_analysis import analyze
from parallax_relay.exploratory import luna_profile_spec
from parallax_relay.money import amount
from parallax_relay.policies import WaitAgent
from parallax_relay.protocol import Usage
from parallax_relay import qualification as q

CLEAN={'status':'clean','revision':'b'*40,'reason':None}
BINDING={'kind':'selection','selection_path':'/fixture/selection','evidence_root':'/fixture/evidence',
         'source_bridge_path':'/fixture/bridge','selection_sha256':'c'*64,'source_bridge_sha256':'d'*64}


class PricedFakeProvider:
    def __init__(self,*args,**kwargs):pass
    async def respond(self,request):
        return replace(await WaitAgent(request.role).respond(request),usage=Usage(10,10))
    async def close(self):pass


class LunaAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)/'supplement'
        cls.patches=[patch(name,return_value=CLEAN) for name in (
            'parallax_relay.campaign.collect_source','parallax_relay.provenance.collect_source',
            'parallax_relay.campaign_analysis.collect_source')]
        cls.patches += [patch.object(q,'selection_binding',return_value=BINDING),
                       patch.object(q,'check_binding',return_value=BINDING),
                       patch('parallax_relay.campaign.HTTPAgent',PricedFakeProvider),
                       patch('parallax_relay.campaign.asyncio.sleep',new=AsyncMock())]
        for p in cls.patches:p.start()
        try:
            cls.reg=register(luna_profile_spec('qualification'),cls.root,
                qualification_selection=Path('/fixture/selection'),evidence_root=Path('/fixture/evidence'),
                source_bridge=Path('/fixture/bridge'))
            asyncio.run(run_campaign(cls.root,live=True,environ={'OPENAI_API_KEY':'FAKE'}))
            cls.ledger=(cls.root/'ledger.jsonl').read_text()
            if not analyze(cls.root)['cohort_eligible']:raise AssertionError('Invalid native test fixture')
        except BaseException:
            for p in reversed(cls.patches):p.stop()
            cls.temp.cleanup();raise

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):p.stop()
        cls.temp.cleanup()

    def tearDown(self):(self.root/'ledger.jsonl').write_text(self.ledger)

    def test_rebalanced_ledger_cannot_understate_native_paid_attempts_or_costs(self):
        rows=[json.loads(line) for line in self.ledger.splitlines()]
        receipt=next(r for r in rows if r['event']=='trial_finished')
        stopped=next(r for r in rows if r['event']=='campaign_stopped')
        receipt['accounted_calls']-=1;receipt['released_calls']+=1;stopped['accounted_calls']-=1
        for row,key,delta in ((receipt,'accounted_estimated_usd',Decimal('-.000001')),
                              (receipt,'released_estimated_usd',Decimal('.000001')),
                              (stopped,'accounted_estimated_usd',Decimal('-.000001'))):
            value=amount(row,key)+delta;row[key]=float(value);row[key+'_decimal']=str(value)
        (self.root/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        report=analyze(self.root)
        self.assertFalse(report['cohort_eligible'])
        self.assertIn('ledger_native_accounting_mismatch',report['anomalies'])
        with self.assertRaises(ValueError):q.build_receipt(self.root)

    def test_coherently_truncated_turn_limit_is_not_a_completed_match(self):
        # Existing completed control-native fixture, coherently shortened to
        # zero turns while preserving own-origin identity, world and ledger.
        from parallax_relay.state import initial_world
        trial=self.reg['schedule'][0];path=self.root/'trials'/trial['trial_id']
        names=(*q.NATIVE_JSON,*q.NATIVE_JSONL)
        saved={name:(path/name).read_bytes() for name in names}
        try:
            result=q.load(path/'result.json');result.update(turns=0,energy=initial_world().energy)
            for key in ('calls_started','reported_input_tokens','reported_output_tokens','unknown_usage_calls',
                        'input_usage_calls','output_usage_calls','reported_cached_input_tokens',
                        'reported_reasoning_output_tokens','calls_reserved_total','calls_released','reserved_calls'):
                result['budget'][key]=0
            for key in ('estimated_cost_usd','known_usage_estimated_usd','retained_estimate_usd'):
                result['budget'][key]=0.0;result['budget'][key+'_decimal']='0'
            result.update(win=False,loss=False,completed=False,scores=None,stop_reason='turn_limit')
            atomic_json(path/'result.json',result);atomic_json(path/'final_state.json',initial_world().snapshot())
            manifest=q.load(path/'manifest.json')
            manifest['provenance']['lifecycle'].update(stop_reason='turn_limit',execution_stop_reason='turn_limit')
            atomic_json(path/'manifest.json',manifest)
            for name in q.NATIVE_JSONL:(path/name).write_text('')
            rows=[json.loads(line) for line in self.ledger.splitlines()]
            receipt=next(r for r in rows if r['event']=='trial_finished' and r['trial_id']==trial['trial_id'])
            old_calls=receipt['accounted_calls'];old_cost=amount(receipt,'accounted_estimated_usd')
            receipt.update(result=result,stop_reason='turn_limit',execution_stop_reason='turn_limit',recording_stop_reason='turn_limit',
                           accounted_calls=0,released_calls=receipt['released_calls']+old_calls)
            for row,key,value in ((receipt,'accounted_estimated_usd',Decimal(0)),
                                  (receipt,'released_estimated_usd',amount(receipt,'released_estimated_usd')+old_cost)):
                row[key]=float(value);row[key+'_decimal']=str(value)
            stop=next(r for r in rows if r['event']=='campaign_stopped');stop['accounted_calls']-=old_calls
            value=amount(stop,'accounted_estimated_usd')-old_cost
            stop.update(accounted_estimated_usd=float(value),accounted_estimated_usd_decimal=str(value))
            (self.root/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            report=analyze(self.root)
            self.assertFalse(report['cohort_eligible'])
            self.assertIn('premature_turn_limit',report['trials'][0]['artifact_issues'])
            with self.assertRaises(ValueError):q.build_receipt(self.root)
        finally:
            for name,data in saved.items():(path/name).write_bytes(data)

    def test_empty_or_truncated_viewer_blocks_supplement_receipt(self):
        trial=self.reg['schedule'][0];path=self.root/'trials'/trial['trial_id']
        viewer=path/'index.html';saved=viewer.read_bytes()
        turns=q.load(path/'result.json')['turns']
        try:
            for value in (b'',saved[:len(saved)//2],saved.replace(b'"calls":',b'"other":',1)):
                viewer.write_bytes(value)
                with self.subTest(size=len(value)),self.assertRaisesRegex(ValueError,'viewer'):
                    q.native_inventory(path,turns)
                with self.assertRaisesRegex(ValueError,'viewer'):q.build_receipt(self.root)
        finally:viewer.write_bytes(saved)

    def test_unknown_or_fatal_retry_blocks_receipt_despite_balanced_native_accounting(self):
        import copy
        trial=self.reg['schedule'][0];path=self.root/'trials'/trial['trial_id']
        names=(*q.NATIVE_JSON,*q.NATIVE_JSONL,'index.html')
        saved={name:(path/name).read_bytes() for name in names}
        try:
            calls=q.strict_jsonl(path/'calls.jsonl');first=calls[0];first['attempt']=2
            failed={**first,'attempt':1,'usage':None,'settlement_basis':'retained_estimate'}
            quote=amount(failed,'reservation_quote_usd')
            failed.update(settled_amount_usd=float(quote),settled_amount_usd_decimal=str(quote))
            calls.insert(0,failed)
            result=q.load(path/'result.json');budget=result['budget']
            budget['calls_started']+=1;budget['calls_released']-=1;budget['unknown_usage_calls']+=1
            for key in ('estimated_cost_usd','retained_estimate_usd'):
                value=amount(budget,key)+quote;budget[key]=float(value);budget[key+'_decimal']=str(value)
            atomic_json(path/'result.json',result)
            rows=[json.loads(line) for line in self.ledger.splitlines()]
            receipt=next(r for r in rows if r['event']=='trial_finished' and r['trial_id']==trial['trial_id'])
            receipt['result']=result;receipt['accounted_calls']+=1;receipt['released_calls']-=1
            stop=next(r for r in rows if r['event']=='campaign_stopped');stop['accounted_calls']+=1
            for row,key,delta in ((receipt,'accounted_estimated_usd',quote),(receipt,'released_estimated_usd',-quote),
                                  (stop,'accounted_estimated_usd',quote)):
                value=amount(row,key)+delta;row[key]=float(value);row[key+'_decimal']=str(value)
            (self.root/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            for status,http in [('timeout',None),('quota_exhausted',429),('nonsense',None),('http_error',401)]:
                failed.update(status=status,http_status=http)
                (path/'calls.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in calls))
                payload={'manifest':q.load(path/'manifest.json'),'result':result,'records':q.strict_jsonl(path/'replay.jsonl'),
                         'calls':calls,'phases':q.strict_jsonl(path/'phases.jsonl'),'final_state':q.load(path/'final_state.json')}
                encoded=json.dumps(payload,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
                template = Path('parallax_relay/replay_template.html').read_text(encoding='utf-8')
                viewer = template.replace('__REPLAY_DATA__', encoded)
                (path/'index.html').write_bytes(viewer.encode('utf-8'))
                report=analyze(self.root)
                self.assertTrue(report['cohort_eligible'],report['trials'][0]['artifact_issues'])
                if status=='timeout':
                    q._phase_integrity({'result':result,'calls':calls,'phases':payload['phases']},trial)
                else:
                    with self.subTest(status=status),self.assertRaisesRegex(ValueError,'retry|attempt'):
                        q.build_receipt(self.root)
        finally:
            for name,data in saved.items():(path/name).write_bytes(data)


if __name__=='__main__':unittest.main()
